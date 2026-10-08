"""
HIPO — Contrato para assinatura eletrônica (entrega 053): regras puras.

O contrato nasce de uma VERSÃO APROVADA da proposta. O HIPO preenche o
modelo .docx (services/contrato_render.py), converte em PDF e manda para a
Autentique (services/autentique.py) com os quatro signatários da minuta da
Controller: contratante, testemunha da contratante, contratada (o CEO) e
testemunha da contratada — nessa ordem, assinatura sequencial.

Este módulo não toca banco, rede nem arquivo: as regras rodam no pytest do
Windows, sem Postgres, e no CI.

DECISÕES

  * Só registra e avisa. Contrato assinado NÃO finaliza a oportunidade: o
    HIPO guarda o PDF assinado e abre uma tarefa para o executivo fazer o
    desfecho (decisão do Tulio, 08/10/2026). O desfecho exige o registro do
    fechamento, que é de quem viveu a negociação.

  * O estado do contrato vem da AUTENTIQUE, não do webhook. O webhook só diz
    "algo mudou no documento X"; quem decide o que mudou é a leitura do
    documento pela API (`aplicar_documento`). Evento fora de ordem, repetido
    ou perdido dá no mesmo resultado — a recomendação da própria Autentique.

  * Dados variáveis entram por CAMPO (`{{NOME}}`); o texto jurídico é do
    modelo, editado no Word. Nada de cláusula montada por código.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from services import cnpj as cnpj_svc
from services import proposta as proposta_regras

# ── Papéis ───────────────────────────────────────────────────────────

ACAO_ASSINAR = "SIGN"
ACAO_TESTEMUNHA = "SIGN_AS_A_WITNESS"


@dataclass(frozen=True)
class Papel:
    chave: str
    rotulo: str
    acao: str


# A ORDEM é a ordem de assinatura (documento `sortable` na Autentique) e a
# ordem do bloco de assinaturas do modelo.
PAPEIS: tuple[Papel, ...] = (
    Papel("contratante", "Contratante", ACAO_ASSINAR),
    Papel("testemunha_contratante", "Testemunha da contratante", ACAO_TESTEMUNHA),
    Papel("contratada", "Contratada", ACAO_ASSINAR),
    Papel("testemunha_contratada", "Testemunha da contratada", ACAO_TESTEMUNHA),
)
CHAVES_PAPEIS = tuple(p.chave for p in PAPEIS)
PAPEL_POR_CHAVE = {p.chave: p for p in PAPEIS}

# ── Estados ──────────────────────────────────────────────────────────

# O contrato só existe no banco depois que a Autentique aceitou o documento:
# não há "rascunho" nem "erro de envio" gravados. Falha no envio volta como
# erro na tela e nada fica para trás — a mesma regra do e-mail (050).
STATUS_ENVIADO = "enviado"
STATUS_ASSINADO = "assinado"
STATUS_RECUSADO = "recusado"
STATUS_CANCELADO = "cancelado"
STATUS = (STATUS_ENVIADO, STATUS_ASSINADO, STATUS_RECUSADO, STATUS_CANCELADO)
STATUS_FINAIS = (STATUS_ASSINADO, STATUS_RECUSADO, STATUS_CANCELADO)

SIG_PENDENTE = "pendente"
SIG_VISUALIZADO = "visualizado"
SIG_ASSINADO = "assinado"
SIG_RECUSADO = "recusado"
SIG_FALHA = "falha_entrega"

DIA_VENCIMENTO_PADRAO = 10
# Até 28: todo mês tem o dia. "Dia 31" em fevereiro vira discussão de
# cobrança, e o contrato não é o lugar de resolver isso.
DIA_VENCIMENTO_MAX = 28

MAX_MOTIVO = 500


class ContratoInvalido(ValueError):
    """Recusa com mensagem pronta para a tela."""


# ── Signatários ──────────────────────────────────────────────────────

_EMAIL = re.compile(r"^[^@\s,;<>()\"']+@[^@\s,;<>()\"']+\.[^@\s,;<>()\"']{2,}$")


def email_valido(endereco: str | None) -> bool:
    return bool(endereco) and bool(_EMAIL.match(endereco.strip()))


def limpar_signatario(chave: str, nome: str | None, email: str | None) -> dict:
    """Nome e e-mail obrigatórios, aparados. E-mail sempre em minúsculas."""
    papel = PAPEL_POR_CHAVE.get(chave)
    if papel is None:
        raise ContratoInvalido(f"Papel de signatário desconhecido: {chave}.")
    nome = " ".join((nome or "").split())
    email = (email or "").strip().lower()
    if not nome:
        raise ContratoInvalido(f"Informe o nome de quem assina como {papel.rotulo.lower()}.")
    if not email_valido(email):
        raise ContratoInvalido(
            f"O e-mail de quem assina como {papel.rotulo.lower()} não é válido."
        )
    return {"papel": chave, "nome": nome[:150], "email": email[:150], "acao": papel.acao}


def validar_signatarios(signatarios: list[dict]) -> list[dict]:
    """
    Exatamente um signatário por papel, na ordem de PAPEIS.

    E-mail repetido entre papéis é recusado: testemunha que é a própria parte
    não testemunha nada, e a Autentique trataria os dois como a mesma pessoa
    — o documento ficaria com uma assinatura a menos do que a minuta exige.
    """
    por_papel: dict[str, dict] = {}
    for s in signatarios:
        chave = s.get("papel")
        if chave in por_papel:
            raise ContratoInvalido(
                f"Há mais de uma pessoa como {PAPEL_POR_CHAVE[chave].rotulo.lower()}."
            )
        por_papel[chave] = limpar_signatario(chave, s.get("nome"), s.get("email"))

    faltando = [p.rotulo.lower() for p in PAPEIS if p.chave not in por_papel]
    if faltando:
        raise ContratoInvalido("Falta quem assina como: " + ", ".join(faltando) + ".")

    ordenados = [dict(por_papel[p.chave], ordem=i + 1) for i, p in enumerate(PAPEIS)]
    vistos: dict[str, str] = {}
    for s in ordenados:
        if s["email"] in vistos:
            raise ContratoInvalido(
                f"O mesmo e-mail ({s['email']}) está como "
                f"{PAPEL_POR_CHAVE[vistos[s['email']]].rotulo.lower()} e como "
                f"{PAPEL_POR_CHAVE[s['papel']].rotulo.lower()}. Cada assinatura "
                "precisa ser de uma pessoa diferente."
            )
        vistos[s["email"]] = s["papel"]
    return ordenados


# ── Campos do modelo ─────────────────────────────────────────────────

CAMPOS_SIMPLES = (
    "CONTRATANTE_RAZAO_SOCIAL",
    "CONTRATANTE_ENDERECO",
    "CONTRATANTE_CNPJ",
    "DIA_VENCIMENTO",
    "INICIO_VIGENCIA",
    "CIDADE",
    "DATA_EXTENSO",
)
CAMPOS_LISTA = ("CNPJ_ADICIONAL", "PRECO_LINHA")


def _cep(cep: str | None) -> str:
    d = re.sub(r"\D", "", cep or "")
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (cep or "").strip()


def pendencias_endereco(conta: dict) -> list[str]:
    """O que falta no cadastro da conta para qualificar a contratante."""
    faltam = []
    for campo, rotulo in (("logradouro", "logradouro"), ("numero", "número"),
                          ("cidade", "cidade"), ("uf", "UF"), ("cep", "CEP")):
        if not (conta.get(campo) or "").strip():
            faltam.append(rotulo)
    return faltam


def endereco_formatado(conta: dict) -> str:
    """
    'Rua Maria Isabel Rezende, 206, Vila Isabel – Guarulhos - SP, CEP: 07111-000'

    Mesma ordem da minuta. Complemento entra depois do número quando existe.
    """
    partes = [(conta.get("logradouro") or "").strip()]
    if (conta.get("numero") or "").strip():
        partes.append(conta["numero"].strip())
    if (conta.get("complemento") or "").strip():
        partes.append(conta["complemento"].strip())
    texto = ", ".join(p for p in partes if p)
    bairro = (conta.get("bairro") or "").strip()
    if bairro:
        texto += f", {bairro}"
    cidade = (conta.get("cidade") or "").strip()
    uf = (conta.get("uf") or "").strip().upper()
    if cidade:
        texto += f" – {cidade}" + (f" - {uf}" if uf else "")
    cep = _cep(conta.get("cep"))
    if cep:
        texto += f", CEP: {cep}"
    return texto


def data_extenso(d: date) -> str:
    """'08 de outubro de 2026' — com dois dígitos no dia, como na minuta."""
    return f"{d.day:02d} de {proposta_regras.MESES[d.month - 1]} de {d.year}"


def inicio_vigencia_padrao(data_contrato: date) -> date:
    """O dia seguinte ao da assinatura, como na minuta da Porto Pisos."""
    return data_contrato + timedelta(days=1)


def validar_datas(data_contrato: date, inicio: date, dia_vencimento: int) -> None:
    if inicio < data_contrato:
        raise ContratoInvalido("O início da vigência não pode ser antes da data do contrato.")
    if inicio > data_contrato + timedelta(days=180):
        raise ContratoInvalido("O início da vigência está a mais de 6 meses da data do contrato.")
    if not (1 <= dia_vencimento <= DIA_VENCIMENTO_MAX):
        raise ContratoInvalido(
            f"O dia de vencimento precisa estar entre 1 e {DIA_VENCIMENTO_MAX}."
        )


def linhas_preco(proposta: dict) -> list[str]:
    """
    As linhas da Cláusula 5, a partir da proposta aprovada.

    Tabela: as faixas da cópia da tabela que a proposta guardou, como na
    minuta; a faixa aberta usa o excedente escolhido pelo EV. CNPJ com
    mensalidade abaixo da tabela ganha uma linha própria com o valor
    negociado — é o número que vale, e a tabela sozinha cobraria a mais.

    Por vida: uma linha só, valor por funcionário/mês.

    Treinamentos e laudos (valores da proposta fora da mensalidade) entram
    como linhas próprias quando existem.
    """
    linhas: list[str] = []
    if proposta["modalidade"] == "tabela":
        faixas = proposta.get("tabela_preco") or proposta_regras.TABELA_PADRAO
        faixas = proposta_regras.normalizar_tabela(faixas)
        excedente = proposta.get("valor_vida_excedente")
        if excedente:
            faixas = [
                dict(f, valor=Decimal(str(excedente)))
                if f["vidas_ate"] is None and f["tipo"] == "por_vida" else f
                for f in faixas
            ]
        for linha in proposta_regras.linhas_tabela(faixas):
            # "por funcionário/mês" da faixa aberta é cobrado sobre o que
            # passa da última faixa: a minuta diz "Excedente".
            if linha.endswith("por funcionário/mês"):
                linha += " excedente"
            linhas.append(linha + ";")
        for item in proposta.get("itens") or []:
            mensal = Decimal(str(item["mensalidade"]))
            tabela = item.get("valor_tabela")
            if tabela is not None and mensal < Decimal(str(tabela)):
                linhas.append(
                    f"Valor negociado para {item['razao_social']} "
                    f"(CNPJ {cnpj_svc.formatar(item['cnpj'])}), com até "
                    f"{item['vidas']:02d} funcionários registrados – "
                    f"{proposta_regras.moeda(mensal)} mensais;"
                )
    else:
        valor = proposta.get("valor_por_vida")
        linhas.append(
            f"{proposta_regras.moeda(valor)} por funcionário registrado/mês;"
        )

    for campo, rotulo in (("treinamentos", "Treinamentos"), ("laudos", "Laudos")):
        v = proposta.get(campo)
        if v and Decimal(str(v)) > 0:
            linhas.append(f"{rotulo}: {proposta_regras.moeda(v)} (valor único, "
                          "conforme proposta comercial);")

    if linhas:
        linhas[-1] = linhas[-1].rstrip(";") + "."
    return linhas


def linhas_cnpjs_adicionais(proposta: dict, cnpj_principal: str) -> list[str]:
    """
    Proposta de vários CNPJs: a contratante é o principal, e os demais entram
    num parágrafo próprio logo após a qualificação. Um CNPJ só: lista vazia,
    e o parágrafo some do contrato.
    """
    principal = cnpj_svc.normalizar(cnpj_principal)
    outros = [i for i in (proposta.get("itens") or [])
              if cnpj_svc.normalizar(i["cnpj"]) != principal]
    if not outros:
        return []
    linhas = ["Integram também o presente contrato, como CONTRATANTES, com os "
              "mesmos direitos e obrigações, as seguintes empresas:"]
    for i, item in enumerate(outros):
        fim = "." if i == len(outros) - 1 else ";"
        linhas.append(
            f"{item['razao_social']}, inscrita no C.N.P.J. do M.F. sob o nº "
            f"{cnpj_svc.formatar(item['cnpj'])}{fim}"
        )
    return linhas


def campos(
    *,
    proposta: dict,
    conta: dict,
    data_contrato: date,
    inicio_vigencia: date,
    dia_vencimento: int,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """(campos simples, campos de lista) para o modelo."""
    simples = {
        "CONTRATANTE_RAZAO_SOCIAL": conta["razao_social"],
        "CONTRATANTE_ENDERECO": endereco_formatado(conta),
        "CONTRATANTE_CNPJ": cnpj_svc.formatar(conta["cnpj"]),
        "DIA_VENCIMENTO": f"{dia_vencimento:02d}",
        "INICIO_VIGENCIA": data_extenso(inicio_vigencia),
        "CIDADE": (proposta.get("cidade") or proposta_regras.CIDADE_PADRAO).strip(),
        "DATA_EXTENSO": data_extenso(data_contrato),
    }
    listas = {
        "CNPJ_ADICIONAL": linhas_cnpjs_adicionais(proposta, conta["cnpj"]),
        "PRECO_LINHA": linhas_preco(proposta),
    }
    return simples, listas


def nome_documento(numero_oportunidade: str | None, razao_social: str, versao: int) -> str:
    """O nome que aparece na Autentique e no e-mail que o signatário recebe."""
    base = f"Contrato Controller MedSeg - {razao_social.strip()}"
    if numero_oportunidade:
        base += f" ({numero_oportunidade})"
    if versao > 1:
        base += f" v{versao}"
    return base[:200]


def nome_arquivo(numero_oportunidade: str | None, razao_social: str, versao: int,
                 assinado: bool) -> str:
    """'CONTRATO_OPP-0042_PORTO_PISOS_ELEVADOS_LTDA_v1_assinado.pdf'"""
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", _sem_acento(razao_social)).strip("_").upper()
    partes = ["CONTRATO"]
    if numero_oportunidade:
        partes.append(re.sub(r"[^A-Za-z0-9-]+", "", numero_oportunidade))
    partes += [limpo[:60] or "CLIENTE", f"v{versao}"]
    if assinado:
        partes.append("assinado")
    return "_".join(partes) + ".pdf"


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c))


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def mensagem_para_signatarios(razao_social: str) -> str:
    return (f"Contrato de prestação de serviços de medicina e segurança do "
            f"trabalho entre {razao_social.strip()} e a Controller Medicina e "
            "Segurança do Trabalho Ltda.")[:500]


# ── Leitura do documento da Autentique ───────────────────────────────

def _quando(evento) -> datetime | None:
    """`{created_at: '...'}` ou None -> datetime com fuso."""
    if not evento:
        return None
    bruto = evento.get("created_at") if isinstance(evento, dict) else None
    if not bruto:
        return None
    return parse_data(bruto)


def parse_data(bruto: str | None) -> datetime | None:
    """A Autentique devolve '2026-10-08 12:56:01' (sem fuso) ou ISO 8601."""
    if not bruto:
        return None
    texto = str(bruto).strip().replace("Z", "+00:00")
    for formato in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            d = datetime.fromisoformat(texto) if formato is None else datetime.strptime(texto, formato)
        except ValueError:
            continue
        # Sem fuso: a Autentique grava em UTC (o horário do carimbo do PDF
        # é o de Brasília, mas o da API é UTC — conferido no sandbox).
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def situacao_signatario(assinatura: dict) -> dict:
    """
    Uma assinatura da API -> o que gravamos dela.

    Recusa vence assinatura (não deveria haver as duas); assinatura vence
    visualização. Falha de entrega só conta enquanto nada mais aconteceu:
    depois que a pessoa abriu, o e-mail chegou de algum jeito.
    """
    assinado = _quando(assinatura.get("signed"))
    recusado = _quando(assinatura.get("rejected"))
    visto = _quando(assinatura.get("viewed"))
    eventos_email = assinatura.get("email_events") or {}
    falha = bool(eventos_email.get("refused")) if isinstance(eventos_email, dict) else False
    motivo = None
    if isinstance(assinatura.get("rejected"), dict):
        motivo = (assinatura["rejected"].get("reason") or "").strip() or None

    if recusado:
        situacao = SIG_RECUSADO
    elif assinado:
        situacao = SIG_ASSINADO
    elif visto:
        situacao = SIG_VISUALIZADO
    elif falha:
        situacao = SIG_FALHA
    else:
        situacao = SIG_PENDENTE
    return {
        "situacao": situacao,
        "visualizado_em": visto,
        "assinado_em": assinado,
        "recusado_em": recusado,
        "motivo_recusa": motivo,
        "falha_entrega": falha and situacao == SIG_FALHA,
    }


def casar_assinaturas(signatarios: list[dict], assinaturas: list[dict]) -> dict:
    """
    {id do signatário no HIPO: assinatura da API}.

    Pelo public_id gravado no envio; quem não tiver (gravação antiga, falha
    parcial) casa pelo e-mail. Assinatura da API sem par é ignorada — alguém
    acrescentou signatário pelo painel da Autentique, fora do HIPO.
    """
    por_public = {a.get("public_id"): a for a in assinaturas if a.get("public_id")}
    por_email: dict[str, dict] = {}
    for a in assinaturas:
        email = ((a.get("email") or (a.get("user") or {}).get("email")) or "").strip().lower()
        if email:
            por_email.setdefault(email, a)
    casados = {}
    for s in signatarios:
        a = por_public.get(s.get("autentique_public_id")) or por_email.get(
            (s.get("email") or "").lower()
        )
        if a is not None:
            casados[s["id"]] = a
    return casados


def status_do_contrato(situacoes: list[str], status_atual: str) -> str:
    """
    Cancelado é decisão do HIPO e não volta. Qualquer recusa recusa o
    contrato (stop_on_rejected). Todos assinados: assinado.
    """
    if status_atual == STATUS_CANCELADO:
        return STATUS_CANCELADO
    if any(s == SIG_RECUSADO for s in situacoes):
        return STATUS_RECUSADO
    if situacoes and all(s == SIG_ASSINADO for s in situacoes):
        return STATUS_ASSINADO
    return STATUS_ENVIADO


def proximo_a_assinar(signatarios: list[dict]) -> dict | None:
    """Assinatura sequencial: o primeiro, na ordem, que ainda não assinou."""
    for s in sorted(signatarios, key=lambda x: x["ordem"]):
        if s["situacao"] != SIG_ASSINADO:
            return s
    return None


# ── Webhook ──────────────────────────────────────────────────────────

def assinatura_webhook_valida(segredo: str, corpo: bytes, recebida: str | None) -> bool:
    """
    HMAC-SHA256 do CORPO CRU com o segredo do endpoint, em hex, contra o
    header X-Autentique-Signature. Sobre os bytes recebidos, nunca sobre o
    JSON reserializado: a ordem das chaves e os espaços mudariam o hash.
    """
    if not segredo or not recebida:
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, recebida.strip().lower())


def ler_evento(payload: dict) -> dict:
    """
    {'id', 'tipo', 'documento_id'} de uma entrega do webhook.

    O corpo é {"id": <entrega>, "event": {"id", "type", "data": {...}}}.
    Em evento de documento, o id está em data.id; em evento de assinatura,
    data.document (string, ou objeto com id). Algumas versões embrulham em
    data.object — as duas formas são aceitas.
    """
    evento = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    tipo = str(evento.get("type") or "")
    dados = evento.get("data") or {}
    if isinstance(dados.get("object"), dict):
        dados = dados["object"]

    documento_id = None
    if tipo.startswith("document."):
        documento_id = dados.get("id")
    else:
        doc = dados.get("document")
        documento_id = doc.get("id") if isinstance(doc, dict) else doc
    return {
        "id": str(evento.get("id") or payload.get("id") or "") or None,
        "tipo": tipo,
        "documento_id": str(documento_id) if documento_id else None,
    }


# ── Tarefas ──────────────────────────────────────────────────────────

def titulo_tarefa_envio(versao: int) -> str:
    return f"Contrato v{versao} enviado para assinatura"


def resultado_tarefa_envio(signatarios: list[dict]) -> str:
    nomes = "; ".join(
        f"{PAPEL_POR_CHAVE[s['papel']].rotulo}: {s['nome']} <{s['email']}>"
        for s in signatarios
    )
    return f"Enviado pela Autentique. {nomes}"[:2000]


def titulo_tarefa_assinado(razao_social: str) -> str:
    return f"Contrato assinado por todos — finalizar a oportunidade ({razao_social})"[:200]


def titulo_tarefa_recusado(nome: str) -> str:
    return f"Contrato recusado por {nome} — entender o motivo"[:200]
