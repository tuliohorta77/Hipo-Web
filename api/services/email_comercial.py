"""
HIPO — Regras do e-mail comercial (entrega 050).

Funções puras: sem banco, sem rede, sem relógio escondido. Rodam no pytest
local do Windows. O que fala com o Google está em services/gmail.py; o que
lê e grava, em routers/crm_emails.py.

Dois e-mails nascem aqui, e são os dois que a operação já mandava à mão:

  * PRIMEIRO CONTATO — o SDR (ou o EC) apresenta a Controller e pergunta
    como a empresa faz a gestão de SST hoje.
  * PROPOSTA — o EV manda a proposta comercial em PDF depois da reunião.

O e-mail sai DA CAIXA DO VENDEDOR, pela Gmail API, com a assinatura que ele
já usa no Gmail. É o ponto: e-mail comercial que chega como "HIPO
<noreply@...>" não é respondido, e a resposta do cliente precisa cair na
caixa de quem conversa com ele.

═══ MODELO → RASCUNHO → ENVIO ═════════════════════════════════════════

O modelo tem variáveis (`{{contato_primeiro_nome}}`). O rascunho é o modelo
com as variáveis preenchidas para UMA oportunidade e UM contato — e é ele
que o vendedor vê e edita antes de mandar. O envio manda o texto que o
vendedor aprovou, e não remonta o modelo: o que sai é o que estava na tela.

Por isso o envio recusa texto com `{{...}}` sobrando. Variável que não foi
preenchida (contato sem nome, oportunidade sem proposta) vira aviso no
rascunho, e não um "Olá, {{contato_primeiro_nome}}" na caixa do cliente.

═══ TEXTO, NÃO HTML ═══════════════════════════════════════════════════

O corpo é texto simples: linha em branco separa parágrafo, quebra de linha
é quebra de linha. Quem converte para HTML é `corpo_html`, escapando tudo.
Editor rico no navegador seria uma porta para colar HTML de qualquer lugar
— com estilo quebrado no Outlook do cliente — e o e-mail comercial aqui é
texto corrido, como nos modelos que já existiam.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from zoneinfo import ZoneInfo

FUSO_OPERACAO = ZoneInfo("America/Sao_Paulo")

MAX_ASSUNTO = 250
MAX_CORPO = 20_000
MAX_DESTINATARIOS = 10
# Teto da Gmail API para a mensagem inteira (upload com uploadType=media).
# O PDF da proposta passa de 5 MB com as imagens do modelo, e o base64 da
# mensagem cresce um terço — por isso o envio vai pelo endpoint de upload,
# e não pelo JSON com `raw`.
MAX_MENSAGEM_BYTES = 35 * 1024 * 1024

SLUGS = ("primeiro_contato", "proposta")


class EmailInvalido(ValueError):
    """Recusado pelas regras do e-mail. A mensagem vai para a tela."""


# ── Variáveis ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Variavel:
    nome: str
    rotulo: str
    exemplo: str


VARIAVEIS: tuple[Variavel, ...] = (
    Variavel("saudacao", "Bom dia / Boa tarde / Boa noite, pela hora do envio", "Boa tarde"),
    Variavel("contato_primeiro_nome", "Primeiro nome do contato", "Nivaldo"),
    Variavel("contato_nome", "Nome completo do contato", "Nivaldo Pereira"),
    Variavel("empresa", "Nome fantasia do cliente (ou a razão social, se não houver)", "NN Redutores"),
    Variavel("razao_social", "Razão social do CNPJ principal", "NN MANUTENCAO EM REDUTORES LTDA"),
    Variavel("cnpj", "CNPJ principal, formatado", "06.335.181/0001-93"),
    Variavel("remetente_primeiro_nome", "Seu primeiro nome", "Gabriel"),
    Variavel("remetente_nome", "Seu nome completo", "Gabriel Lira"),
    Variavel("remetente_telefone", "Seu telefone do cadastro", "(11) 91100-5646"),
    Variavel("nossa_empresa", "Nome da nossa empresa", "Controller MedSeg"),
    Variavel("proposta_mensalidade", "Mensalidade da proposta anexada", "R$ 1.270,00"),
    Variavel("proposta_vidas", "Vidas da proposta anexada", "70"),
    Variavel("proposta_validade", "Validade da proposta anexada", "16/10/2026"),
)

NOMES_VARIAVEIS = frozenset(v.nome for v in VARIAVEIS)

# Só as variáveis da proposta dependem de haver proposta escolhida. As
# outras saem do cadastro e sempre têm de onde vir.
VARIAVEIS_PROPOSTA = frozenset(
    {"proposta_mensalidade", "proposta_vidas", "proposta_validade"}
)

_PADRAO_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_SOBRA = re.compile(r"\{\{|\}\}")


def variaveis_usadas(texto: str) -> list[str]:
    """
    >>> variaveis_usadas("Olá {{ contato_primeiro_nome }}, {{saudacao}}!")
    ['contato_primeiro_nome', 'saudacao']
    """
    vistos: list[str] = []
    for nome in _PADRAO_VAR.findall(texto or ""):
        if nome not in vistos:
            vistos.append(nome)
    return vistos


def validar_modelo(nome: str, assunto: str, corpo: str) -> tuple[str, str, str]:
    """
    Modelo que a gestão salva. Variável desconhecida é recusada AQUI, na
    hora de salvar — descobrir no rascunho do vendedor seria descobrir
    tarde, na frente do cliente.
    """
    nome = (nome or "").strip()
    assunto = (assunto or "").strip()
    corpo = (corpo or "").strip()
    if not nome:
        raise EmailInvalido("Dê um nome ao modelo.")
    if len(nome) > 80:
        raise EmailInvalido("O nome do modelo passa de 80 caracteres.")
    if not assunto:
        raise EmailInvalido("O modelo precisa de assunto.")
    if len(assunto) > MAX_ASSUNTO:
        raise EmailInvalido(f"O assunto passa de {MAX_ASSUNTO} caracteres.")
    if not corpo:
        raise EmailInvalido("O modelo precisa de texto.")
    if len(corpo) > MAX_CORPO:
        raise EmailInvalido(f"O texto passa de {MAX_CORPO} caracteres.")
    desconhecidas = [
        v for v in variaveis_usadas(assunto + "\n" + corpo) if v not in NOMES_VARIAVEIS
    ]
    if desconhecidas:
        raise EmailInvalido(
            "Variável desconhecida no modelo: "
            + ", ".join("{{" + v + "}}" for v in desconhecidas)
            + ". Use as da lista ao lado."
        )
    # Chave aberta sem fechar ({{nome}) passaria pelo regex e iria crua.
    resto = _PADRAO_VAR.sub("", assunto + "\n" + corpo)
    if _SOBRA.search(resto):
        raise EmailInvalido("Há uma variável mal escrita: use {{nome_da_variavel}}.")
    return nome, assunto, corpo


# ── Modelos padrão ───────────────────────────────────────────────────
#
# Os dois textos que a equipe já mandava, com nome e empresa virando
# variável. São a semente da migration 030 e também o que vale quando a
# tabela está vazia (banco de teste depois do TRUNCATE, base nova): mesma
# escolha da TABELA_PADRAO da proposta.

MODELOS_PADRAO: dict[str, dict] = {
    "primeiro_contato": {
        "slug": "primeiro_contato",
        "nome": "Primeiro contato",
        "assunto": "Medicina Ocupacional e Segurança do Trabalho",
        "corpo": (
            "Olá, {{contato_primeiro_nome}}, tudo bem?\n"
            "\n"
            "Meu nome é {{remetente_primeiro_nome}} e faço parte da equipe "
            "comercial da Controller Medicina e Segurança do Trabalho.\n"
            "\n"
            "Atendemos empresas em todas as regiões do Brasil, oferecendo uma "
            "solução completa para Medicina Ocupacional e Segurança do "
            "Trabalho, desde os exames ocupacionais até a gestão das "
            "obrigações de SST.\n"
            "\n"
            "Além dos exames, nossa contratação já contempla ASO, PCMSO, PGR e "
            "LTCAT, proporcionando mais praticidade e centralização para a "
            "empresa.\n"
            "\n"
            "Queria entender como vocês fazem essa gestão atualmente e se "
            "existe algum ponto que podemos ajudar a melhorar — seja em prazo, "
            "atendimento, custo ou centralização dos serviços.\n"
            "\n"
            "Atenciosamente,"
        ),
        "anexa_proposta": False,
        "ordem": 1,
    },
    "proposta": {
        "slug": "proposta",
        "nome": "Envio de proposta",
        "assunto": "Proposta comercial {{nossa_empresa}} — {{empresa}}",
        "corpo": (
            "{{saudacao}}, {{contato_primeiro_nome}}, tudo bem?\n"
            "\n"
            "Conforme alinhamos em nossa reunião, envio em anexo a proposta "
            "comercial para a {{razao_social}}.\n"
            "O documento detalha o escopo completo dos serviços apresentados "
            "e seus valores.\n"
            "\n"
            "Fico à disposição para maiores esclarecimentos.\n"
            "\n"
            "At.te"
        ),
        "anexa_proposta": True,
        "ordem": 2,
    },
}


# ── Preenchimento ────────────────────────────────────────────────────

def saudacao(agora: datetime) -> str:
    """
    Pela hora de Brasília, não a do servidor.

    >>> saudacao(datetime(2026, 10, 6, 11, 59, tzinfo=FUSO_OPERACAO))
    'Bom dia'
    >>> saudacao(datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc))  # 12h BRT
    'Boa tarde'
    >>> saudacao(datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc))  # 18h BRT
    'Boa noite'
    """
    hora = agora.astimezone(FUSO_OPERACAO).hour if agora.tzinfo else agora.hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


def primeiro_nome(nome: str | None) -> str:
    """
    O primeiro nome, com caixa de gente.

    Cadastro vindo de planilha chega em CAIXA ALTA, e "Olá, NIVALDO" num
    e-mail parece cobrança. Nome digitado com caixa mista é respeitado
    (o "McDonald" de alguém fica como está).

    >>> primeiro_nome("NIVALDO PEREIRA")
    'Nivaldo'
    >>> primeiro_nome("  ana maria ")
    'Ana'
    >>> primeiro_nome("JoAna")
    'JoAna'
    >>> primeiro_nome(None)
    ''
    """
    partes = (nome or "").split()
    if not partes:
        return ""
    p = partes[0]
    if p.isupper() or p.islower():
        return p[:1].upper() + p[1:].lower()
    return p


def _moeda(v) -> str:
    n = Decimal(str(v)).quantize(Decimal("0.01"))
    inteiro, centavos = f"{n:.2f}".split(".")
    sinal = "-" if inteiro.startswith("-") else ""
    inteiro = inteiro.lstrip("-")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sinal}R$ {'.'.join(grupos) or '0'},{centavos}"


def valores(
    *,
    agora: datetime,
    contato_nome: str | None,
    razao_social: str | None,
    nome_fantasia: str | None,
    cnpj_formatado: str | None,
    remetente_nome: str | None,
    remetente_telefone: str | None,
    nossa_empresa: str,
    proposta: dict | None = None,
) -> dict[str, str]:
    """
    O dicionário variável → texto para um envio. Valor ausente é "" — quem
    transforma ausência em aviso é `preencher`.

    `proposta` é o dict da proposta (ou do item, na proposta de um CNPJ):
    precisa de `mensalidade`, `vidas` e `validade`.
    """
    v = {
        "saudacao": saudacao(agora),
        "contato_primeiro_nome": primeiro_nome(contato_nome),
        "contato_nome": " ".join((contato_nome or "").split()),
        "empresa": (nome_fantasia or "").strip() or (razao_social or "").strip(),
        "razao_social": (razao_social or "").strip(),
        "cnpj": cnpj_formatado or "",
        "remetente_primeiro_nome": primeiro_nome(remetente_nome),
        "remetente_nome": " ".join((remetente_nome or "").split()),
        "remetente_telefone": (remetente_telefone or "").strip(),
        "nossa_empresa": nossa_empresa,
        "proposta_mensalidade": "",
        "proposta_vidas": "",
        "proposta_validade": "",
    }
    if proposta:
        if proposta.get("mensalidade") is not None:
            v["proposta_mensalidade"] = _moeda(proposta["mensalidade"])
        if proposta.get("vidas") is not None:
            v["proposta_vidas"] = str(proposta["vidas"])
        validade = proposta.get("validade")
        if isinstance(validade, (date, datetime)):
            v["proposta_validade"] = validade.strftime("%d/%m/%Y")
        elif validade:
            v["proposta_validade"] = str(validade)
    return v


ROTULO_AUSENTE = {
    "contato_primeiro_nome": "o contato não tem nome no cadastro",
    "contato_nome": "o contato não tem nome no cadastro",
    "empresa": "a conta não tem razão social",
    "razao_social": "a conta não tem razão social",
    "cnpj": "a conta não tem CNPJ",
    "remetente_primeiro_nome": "seu nome não está no cadastro",
    "remetente_nome": "seu nome não está no cadastro",
    "remetente_telefone": "seu telefone não está no cadastro (preencha em Perfil)",
    "proposta_mensalidade": "nenhuma proposta foi escolhida",
    "proposta_vidas": "nenhuma proposta foi escolhida",
    "proposta_validade": "nenhuma proposta foi escolhida",
}


@dataclass
class Preenchido:
    texto: str
    ausentes: list[str] = field(default_factory=list)


def preencher(texto: str, vals: dict[str, str]) -> Preenchido:
    """
    Troca cada `{{var}}` pelo valor. Variável sem valor vira "" e entra em
    `ausentes`; variável que não existe levanta (modelo salvo já passou
    pela validação, então isso é bug, não entrada do usuário).

    >>> p = preencher("Olá, {{contato_primeiro_nome}}!", {"contato_primeiro_nome": "Ana"})
    >>> p.texto, p.ausentes
    ('Olá, Ana!', [])
    >>> preencher("Olá, {{contato_primeiro_nome}}!", {"contato_primeiro_nome": ""}).ausentes
    ['contato_primeiro_nome']
    """
    ausentes: list[str] = []

    def troca(m: re.Match) -> str:
        nome = m.group(1)
        if nome not in vals:
            raise EmailInvalido(f"Variável desconhecida: {{{{{nome}}}}}")
        valor = vals[nome]
        if not valor and nome not in ausentes:
            ausentes.append(nome)
        return valor

    saida = _PADRAO_VAR.sub(troca, texto or "")
    # "Olá, , tudo bem?" quando o nome falta: tira a vírgula órfã para o
    # rascunho já nascer legível. O aviso continua — o vendedor decide.
    saida = re.sub(r",\s*,", ",", saida)
    saida = re.sub(r"[ \t]+,", ",", saida)
    return Preenchido(saida, ausentes)


def avisos_de_ausencia(ausentes: list[str]) -> list[str]:
    """Uma frase por motivo, sem repetir."""
    vistos: list[str] = []
    for nome in ausentes:
        frase = ROTULO_AUSENTE.get(nome, f"falta o valor de {{{{{nome}}}}}")
        frase = frase[:1].upper() + frase[1:] + "."
        if frase not in vistos:
            vistos.append(frase)
    return vistos


# ── Validação do envio ───────────────────────────────────────────────

_EMAIL = re.compile(r"^[^@\s,;<>()\"']+@[^@\s,;<>()\"']+\.[^@\s,;<>()\"']{2,}$")


def email_valido(endereco: str | None) -> bool:
    """
    >>> email_valido("ana@empresa.com.br")
    True
    >>> email_valido("ana@empresa")
    False
    >>> email_valido("Ana <ana@x.com>")
    False
    """
    return bool(_EMAIL.match((endereco or "").strip()))


def limpar_enderecos(enderecos: list[str] | None, campo: str) -> list[str]:
    """
    Sem vazio, sem repetido (por minúscula), cada um válido.

    Repetido é o mesmo tropeço dos convidados da agenda: o mesmo endereço
    digitado com caixa diferente ao lado do que veio do cadastro.
    """
    saida: list[str] = []
    vistos: set[str] = set()
    for e in enderecos or []:
        limpo = (e or "").strip()
        if not limpo:
            continue
        if not email_valido(limpo):
            raise EmailInvalido(f"Endereço inválido em {campo}: {limpo}")
        if limpo.lower() not in vistos:
            vistos.add(limpo.lower())
            saida.append(limpo)
    return saida


@dataclass(frozen=True)
class Envio:
    para: list[str]
    cc: list[str]
    assunto: str
    corpo: str


def validar_envio(
    *, para: list[str], cc: list[str] | None, assunto: str, corpo: str,
    remetente_email: str,
) -> Envio:
    para_l = limpar_enderecos(para, "Para")
    cc_l = [e for e in limpar_enderecos(cc, "Cc")
            if e.lower() not in {p.lower() for p in para_l}]
    if not para_l:
        raise EmailInvalido("Informe pelo menos um destinatário.")
    if len(para_l) + len(cc_l) > MAX_DESTINATARIOS:
        raise EmailInvalido(
            f"No máximo {MAX_DESTINATARIOS} destinatários por e-mail comercial."
        )
    if any(e.lower() == (remetente_email or "").lower() for e in para_l):
        raise EmailInvalido("O destinatário não pode ser você mesmo.")
    assunto = " ".join((assunto or "").split())
    corpo = (corpo or "").replace("\r\n", "\n").strip()
    if not assunto:
        raise EmailInvalido("O e-mail precisa de assunto.")
    if len(assunto) > MAX_ASSUNTO:
        raise EmailInvalido(f"O assunto passa de {MAX_ASSUNTO} caracteres.")
    if not corpo:
        raise EmailInvalido("O e-mail está sem texto.")
    if len(corpo) > MAX_CORPO:
        raise EmailInvalido(f"O texto passa de {MAX_CORPO} caracteres.")
    if _SOBRA.search(assunto) or _SOBRA.search(corpo):
        raise EmailInvalido(
            "Ainda há uma variável {{...}} no texto. Troque pelo valor antes "
            "de enviar — o cliente veria as chaves."
        )
    return Envio(para_l, cc_l, assunto, corpo)


# ── Montagem da mensagem ─────────────────────────────────────────────

def corpo_html(corpo: str, assinatura_html: str | None = None) -> str:
    """
    Texto → HTML escapado. Linha em branco separa parágrafo; quebra simples
    vira <br>. A assinatura do Gmail entra no fim, como o próprio Gmail a
    coloca (prefixo "-- ").

    >>> corpo_html("Olá <b>\\n\\nTchau")
    '<div dir="ltr"><p style="margin:0 0 1em 0">Olá &lt;b&gt;</p><p style="margin:0 0 1em 0">Tchau</p></div>'
    """
    paragrafos = [p for p in re.split(r"\n\s*\n", (corpo or "").strip()) if p.strip()]
    partes = [
        '<p style="margin:0 0 1em 0">'
        + "<br>".join(html.escape(linha) for linha in p.split("\n"))
        + "</p>"
        for p in paragrafos
    ]
    saida = '<div dir="ltr">' + "".join(partes)
    if assinatura_html:
        saida += (
            '<span class="gmail_signature_prefix">-- </span><br>'
            '<div dir="ltr" class="gmail_signature" data-smartmail="gmail_signature">'
            + assinatura_html
            + "</div>"
        )
    return saida + "</div>"


def html_para_texto(fragmento: str | None) -> str:
    """
    A assinatura em texto, para a parte text/plain. Grosseiro de propósito:
    é o que aparece em cliente de e-mail que não mostra HTML.

    >>> html_para_texto("<div>Gabriel<br>Executivo</div><div>(11) 9</div>")
    'Gabriel\\nExecutivo\\n(11) 9'
    """
    t = re.sub(r"(?i)<br\s*/?>", "\n", fragmento or "")
    t = re.sub(r"(?i)</(div|p|tr|li|h\d)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    linhas = [" ".join(l.split()) for l in t.split("\n")]
    return "\n".join(l for l in linhas if l)


@dataclass(frozen=True)
class Anexo:
    nome: str
    conteudo: bytes
    tipo: str = "application/pdf"


def montar_mensagem(
    *,
    remetente_nome: str,
    remetente_email: str,
    envio: Envio,
    assinatura_html: str | None = None,
    anexo: Anexo | None = None,
) -> bytes:
    """
    A mensagem RFC 822 pronta para o Gmail. Texto e HTML como alternativas,
    anexo (se houver) por fora.

    O From precisa ser o próprio remetente: com delegação, a conta de
    serviço age como ele, e o Gmail recusa From de outra caixa que não
    esteja configurada como "enviar como".
    """
    msg = EmailMessage()
    msg["From"] = formataddr((remetente_nome or "", remetente_email))
    msg["To"] = ", ".join(envio.para)
    if envio.cc:
        msg["Cc"] = ", ".join(envio.cc)
    msg["Subject"] = envio.assunto

    texto = envio.corpo
    assinatura_texto = html_para_texto(assinatura_html)
    if assinatura_texto:
        texto += "\n\n-- \n" + assinatura_texto
    msg.set_content(texto)
    msg.add_alternative(corpo_html(envio.corpo, assinatura_html), subtype="html")

    if anexo is not None:
        principal, _, sub = anexo.tipo.partition("/")
        msg.add_attachment(
            anexo.conteudo, maintype=principal, subtype=sub or "octet-stream",
            filename=anexo.nome,
        )

    bruto = msg.as_bytes()
    if len(bruto) > MAX_MENSAGEM_BYTES:
        raise EmailInvalido(
            "A mensagem passa de 35 MB, o limite do Gmail. Envie a proposta "
            "de cada CNPJ separada."
        )
    return bruto


# ── Resposta do cliente ──────────────────────────────────────────────

@dataclass(frozen=True)
class Resposta:
    em: datetime
    de: str


def _cabecalho(mensagem: dict, nome: str) -> str:
    for h in (mensagem.get("payload") or {}).get("headers") or []:
        if (h.get("name") or "").lower() == nome.lower():
            return h.get("value") or ""
    return ""


def _endereco(cabecalho_from: str) -> str:
    """
    >>> _endereco('"Ana Souza" <Ana@Cliente.com>')
    'ana@cliente.com'
    """
    pares = getaddresses([cabecalho_from or ""])
    return (pares[0][1] if pares else "").strip().lower()


def detectar_resposta(
    thread: dict, enviado_id: str, remetente_email: str,
) -> Resposta | None:
    """
    A primeira mensagem do fio que veio DEPOIS da nossa e NÃO saiu da
    caixa do vendedor.

    Duas condições, e não uma: o rótulo SENT tira o que o próprio vendedor
    mandou depois (um follow-up não é resposta), e a comparação do From tira
    a cópia que o Gmail às vezes rotula diferente quando o vendedor se põe
    em cópia. Rascunho não conta.

    `thread` é o `users.threads.get` com format=metadata.
    """
    mensagens = thread.get("messages") or []
    nossa = next((m for m in mensagens if m.get("id") == enviado_id), None)
    if nossa is None:
        return None
    base = int(nossa.get("internalDate") or 0)
    eu = (remetente_email or "").strip().lower()
    candidatas = []
    for m in mensagens:
        if m.get("id") == enviado_id:
            continue
        rotulos = set(m.get("labelIds") or [])
        if "SENT" in rotulos or "DRAFT" in rotulos:
            continue
        quando = int(m.get("internalDate") or 0)
        if quando <= base:
            continue
        de = _cabecalho(m, "From")
        if _endereco(de) == eu:
            continue
        candidatas.append((quando, de))
    if not candidatas:
        return None
    quando, de = min(candidatas)
    return Resposta(datetime.fromtimestamp(quando / 1000, tz=timezone.utc), de[:200])
