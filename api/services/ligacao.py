"""
HIPO — Regras das ligações gravadas pelo Vivo Voz Negócio (entrega 056).

Funções puras: sem banco, sem rede e sem relógio escondido (`agora` entra
sempre por parâmetro). Rodam no pytest local do Windows, que não tem
Postgres nem AWS. O I/O com a AWS mora em services/ligacao_aws.py; a
orquestração (banco + AWS + IA) em services/coleta_ligacao.py.

═══ COMO UMA LIGAÇÃO NASCE ════════════════════════════════════════════

O softphone da Vivo é um PABX em nuvem da Metaswitch, sem API. O HIPO não
consegue perguntar "quem ligou para quem" nem pedir a gravação. São duas
metades, juntadas aqui:

  CLIQUE    o "ligar" no telefone do contato, dentro do HIPO. Sabe QUEM,
            PARA QUEM e DE QUAL oportunidade — mas não sabe se a ligação
            aconteceu.
  GRAVAÇÃO  o gravador (agente Windows) percebe a chamada pelo áudio do
            softphone e grava. Sabe QUANDO e O QUE foi dito — mas não sabe
            para quem.

`casar` decide qual clique é dono de qual gravação: o clique mais recente
da MESMA pessoa dentro da janela em volta do início do áudio. Sem clique
na janela, a gravação entra sem vínculo e a pessoa vincula na tela.

═══ OS DOIS CANAIS ════════════════════════════════════════════════════

O gravador põe o microfone no canal 0 (quem ligou) e a saída de áudio no
canal 1 (o cliente). O AWS Transcribe transcreve cada canal separado, então
"quem falou" é exato — não depende de diarização adivinhar vozes — e o
tempo de fala de cada lado sai de graça.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.transcricao import Fala, entradas_json, juntar_falas, texto_corrido

# ── Janelas ──────────────────────────────────────────────────────────

# Clique → áudio. O gravador começa quando o softphone abre o áudio (o
# "chamando"), o que acontece segundos depois do clique — ou minutos, se a
# pessoa clicou, foi pegar um café e só então apertou "ligar". Três minutos
# antes cobre isso; o minuto DEPOIS cobre relógio de máquina adiantado que
# a correção de desvio não pegou inteiro.
JANELA_ANTES = timedelta(minutes=3)
JANELA_DEPOIS = timedelta(minutes=1)

# Clique que ficou sem gravação por mais que isto vira `sem_gravacao`:
# gravador desligado, ligou pelo celular, desistiu de ligar. Seis horas e
# não três minutos porque o agente guarda a gravação e reenvia quando a
# internet volta — o notebook que fechou a tampa no meio do upload manda
# na próxima vez que ligar.
EXPIRA_CLIQUE = timedelta(hours=6)

# O agente pediu o endereço de upload e não confirmou. Passado isto, o
# coletor confere no S3: se o arquivo chegou, segue; se não, erro.
EXPIRA_ENVIO = timedelta(hours=2)

# O AWS Transcribe leva de 30 s a alguns minutos. Passado isto sem
# resposta, alguma coisa travou e a tela precisa dizer.
EXPIRA_TRANSCRICAO = timedelta(hours=3)

# Quantas vezes o coletor tenta começar a transcrição antes de desistir.
MAX_TENTATIVAS = 3

# Abaixo disto não é ligação: é o softphone tocando um bipe, a pessoa
# discou errado e desligou. O agente já filtra; o servidor confere de novo
# porque o agente é código que roda na máquina de outra pessoa.
MIN_DURACAO_S = 5
# Ninguém fica 4 horas numa ligação de venda. Acima disto é o gravador que
# não percebeu o fim (o softphone deixou o áudio aberto).
MAX_DURACAO_S = 4 * 3600

# FLAC 8 kHz estéreo dá ~1 MB por minuto. 300 MB é folga para o caso
# extremo sem abrir a porta para um arquivo de vídeo arrastado por engano.
MAX_AUDIO_BYTES = 300 * 1024 * 1024

FORMATOS = {"flac": ("audio/flac", ".flac")}

# Gravador sem pulso há mais que isto aparece como desligado na tela. O
# agente pulsa a cada 2 minutos; cinco cobrem um pulso perdido.
GRAVADOR_ONLINE = timedelta(minutes=5)

# Desvio de relógio da máquina abaixo disto é ruído de rede e fica.
DESVIO_IGNORADO = timedelta(seconds=2)
# Acima disto o relógio da máquina está tão errado que a correção vira
# chute; o servidor usa a própria hora de chegada.
DESVIO_MAXIMO = timedelta(hours=12)

# Quebra de fala dentro do mesmo canal: pausa maior que isto começa outra.
PAUSA_NOVA_FALA_S = 1.2

PREFIXO_TOKEN = "hipograv_"

STATUS = (
    "discando", "enviando", "transcrevendo", "pronta",
    "sem_fala", "sem_gravacao", "erro",
)
EM_ANDAMENTO = ("discando", "enviando", "transcrevendo")

ROTULO_STATUS = {
    "discando": "Aguardando gravação",
    "enviando": "Recebendo gravação",
    "transcrevendo": "Transcrevendo",
    "pronta": "Transcrita",
    "sem_fala": "Sem conversa",
    "sem_gravacao": "Sem gravação",
    "erro": "Erro",
}

ORIGENS = ("clique", "gravador")


class LigacaoInvalida(ValueError):
    """Recusa com mensagem pronta para o usuário final."""


# ── Token do gravador ────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenGravador:
    token: str      # vai para a tela UMA vez
    hash: str       # vai para o banco
    prefixo: str    # vai para a lista, para reconhecer sem expor


def gerar_token() -> TokenGravador:
    """
    Token novo do gravador. 32 bytes de aleatoriedade: não é senha que
    alguém digita, é colado uma vez no instalador.
    """
    token = PREFIXO_TOKEN + secrets.token_urlsafe(32)
    return TokenGravador(token=token, hash=hash_token(token), prefixo=token[:16])


def hash_token(token: str) -> str:
    """
    SHA-256 em hex. Sem sal e sem bcrypt de propósito: o token tem 256 bits
    de entropia — não existe dicionário para ele — e o hash precisa ser
    buscável por igualdade (`WHERE token_hash = $1`) a cada pulso.

    >>> len(hash_token("x"))
    64
    """
    return hashlib.sha256((token or "").encode()).hexdigest()


def token_do_header(header: str | None) -> str | None:
    """
    O token do header Authorization, ou None se não for de gravador.

    >>> token_do_header("Bearer hipograv_abc")
    'hipograv_abc'
    >>> token_do_header("Bearer eyJhbGciOi") is None
    True
    >>> token_do_header(None) is None
    True
    """
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token if token.startswith(PREFIXO_TOKEN) else None


def validar_nome_gravador(nome: str | None) -> str:
    limpo = " ".join((nome or "").split())
    if not limpo:
        raise LigacaoInvalida("Dê um nome para o gravador (ex.: Notebook da Kethlleen).")
    return limpo[:80]


def gravador_online(ultimo_contato_em: datetime | None, agora: datetime) -> bool:
    if ultimo_contato_em is None:
        return False
    return _utc(agora) - _utc(ultimo_contato_em) <= GRAVADOR_ONLINE


# ── Clique ───────────────────────────────────────────────────────────


def normalizar_telefone(numero: str | None) -> str | None:
    """
    Só os dígitos (com o + do DDI, se veio). É o número que o softphone
    vai discar e o que aparece na lista — sem máscara, para casar com a
    busca por número no futuro.

    >>> normalizar_telefone("(11) 9 9571-3682")
    '11995713682'
    >>> normalizar_telefone("+55 11 2222-3333")
    '+551122223333'
    >>> normalizar_telefone("  ") is None
    True
    """
    bruto = (numero or "").strip()
    digitos = re.sub(r"\D", "", bruto)
    if not digitos:
        return None
    return ("+" if bruto.startswith("+") else "") + digitos[:20]


# ── Gravação ─────────────────────────────────────────────────────────


def validar_gravacao(duracao_s, tamanho_bytes, formato: str | None) -> tuple[int, int, str, str]:
    """
    (duração, tamanho, tipo MIME, extensão), ou LigacaoInvalida.
    """
    fmt = (formato or "").strip().lower()
    if fmt not in FORMATOS:
        raise LigacaoInvalida(f"Formato de gravação não aceito: {formato!r} (esperado flac).")
    try:
        dur = int(round(float(duracao_s)))
        tam = int(tamanho_bytes)
    except (TypeError, ValueError):
        raise LigacaoInvalida("Duração ou tamanho da gravação inválidos.") from None
    if dur < MIN_DURACAO_S:
        raise LigacaoInvalida(f"Gravação com menos de {MIN_DURACAO_S} s não é ligação.")
    if dur > MAX_DURACAO_S:
        raise LigacaoInvalida("Gravação acima de 4 horas: o gravador não percebeu o fim da chamada.")
    if tam <= 0:
        raise LigacaoInvalida("Gravação vazia.")
    if tam > MAX_AUDIO_BYTES:
        raise LigacaoInvalida(f"Gravação acima de {MAX_AUDIO_BYTES // (1024 * 1024)} MB.")
    tipo, ext = FORMATOS[fmt]
    return dur, tam, tipo, ext


def corrigir_relogio(
    inicio: datetime, fim: datetime, agora_agente: datetime | None, agora_servidor: datetime,
) -> tuple[datetime, datetime]:
    """
    Início e fim no relógio do SERVIDOR.

    O agente manda a hora dele junto com a gravação. A diferença entre essa
    hora e a do servidor no momento em que o pedido chega é o desvio do
    relógio da máquina (mais a latência, que é de milissegundos). Sem esta
    correção, um notebook com o relógio 4 minutos atrasado nunca casaria
    com o clique — e o clique foi registrado pelo relógio do servidor.

    >>> from datetime import datetime, timezone, timedelta
    >>> t = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
    >>> i, f = corrigir_relogio(t, t + timedelta(minutes=2), t + timedelta(minutes=3),
    ...                         t + timedelta(minutes=7))
    >>> i.minute, f.minute
    (4, 6)
    """
    inicio, fim, agora_servidor = _utc(inicio), _utc(fim), _utc(agora_servidor)
    if agora_agente is None:
        return inicio, fim
    desvio = agora_servidor - _utc(agora_agente)
    if abs(desvio) <= DESVIO_IGNORADO:
        return inicio, fim
    if abs(desvio) > DESVIO_MAXIMO:
        # Relógio absurdo: ancora o fim na chegada e preserva a duração.
        duracao = fim - inicio
        return agora_servidor - duracao, agora_servidor
    return inicio + desvio, fim + desvio


def casar(cliques: list[tuple[UUID | str, datetime]], inicio_audio: datetime) -> UUID | str | None:
    """
    O clique dono desta gravação, ou None.

    Entre os cliques da pessoa ainda sem gravação, os que caem na janela
    [início − 3 min, início + 1 min]. Dos que sobram, o MAIS RECENTE — quem
    clicou em dois números seguidos (o primeiro não atendeu) ligou de
    verdade no segundo.

    >>> from datetime import datetime, timezone, timedelta
    >>> t = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
    >>> casar([("a", t - timedelta(minutes=2)), ("b", t - timedelta(seconds=20))], t)
    'b'
    >>> casar([("a", t - timedelta(minutes=10))], t) is None
    True
    """
    ini = _utc(inicio_audio)
    dentro = [
        (cid, _utc(em)) for cid, em in cliques
        if ini - JANELA_ANTES <= _utc(em) <= ini + JANELA_DEPOIS
    ]
    if not dentro:
        return None
    return max(dentro, key=lambda x: x[1])[0]


def chave_audio(usuario_id: UUID | str, ligacao_id: UUID | str, extensao: str = ".flac") -> str:
    """Caminho no bucket, só de ids. Prefixo próprio para a regra de retenção."""
    return f"ligacoes/{usuario_id}/{ligacao_id}{extensao}"


def nome_job(ligacao_id: UUID | str, tentativa: int) -> str:
    """
    Nome do job no Transcribe. Único por conta e região, e o mesmo nome não
    pode ser reusado nem depois de o job acabar — por isso a tentativa vai
    no nome.

    >>> nome_job("1f2e", 2)
    'hipo-ligacao-1f2e-t2'
    """
    return f"hipo-ligacao-{ligacao_id}-t{tentativa}"


# ── Leitura do Transcribe ────────────────────────────────────────────


@dataclass(frozen=True)
class Trecho:
    """Um pedaço de fala contínua de UM canal."""
    canal: int
    inicio_s: float
    fim_s: float
    texto: str


def _canal(rotulo) -> int:
    """'ch_0' -> 0. Rótulo estranho vira canal 1 (cliente), o lado neutro."""
    m = re.search(r"(\d+)", str(rotulo or ""))
    return int(m.group(1)) if m else 1


def _trechos_dos_itens(canal: int, itens: list[dict]) -> list[Trecho]:
    """
    Palavras de um canal → trechos, quebrando nas pausas.

    Pontuação vem como item sem horário, colada na palavra anterior.
    """
    trechos: list[Trecho] = []
    atual: list[str] = []
    ini = fim = None
    for it in itens or []:
        alt = (it.get("alternatives") or [{}])[0]
        conteudo = (alt.get("content") or "").strip()
        if not conteudo:
            continue
        if it.get("type") == "punctuation":
            if atual:
                atual[-1] += conteudo
            continue
        try:
            s = float(it.get("start_time"))
            e = float(it.get("end_time"))
        except (TypeError, ValueError):
            continue
        if atual and fim is not None and s - fim > PAUSA_NOVA_FALA_S:
            trechos.append(Trecho(canal, ini, fim, " ".join(atual)))
            atual, ini = [], None
        if ini is None:
            ini = s
        atual.append(conteudo)
        fim = e
    if atual:
        trechos.append(Trecho(canal, ini, fim, " ".join(atual)))
    return trechos


def ler_transcribe(dados: dict) -> list[Trecho]:
    """
    O JSON do AWS Transcribe (com ChannelIdentification) → trechos de fala
    em ordem de tempo.

    Lê `results.channel_labels.channels[].items`, que é o formato estável
    da identificação de canal. JSON sem canais (job antigo, áudio mono)
    cai nos `results.items` como canal 1.
    """
    res = (dados or {}).get("results") or {}
    trechos: list[Trecho] = []
    canais = ((res.get("channel_labels") or {}).get("channels")) or []
    if canais:
        for ch in canais:
            trechos.extend(_trechos_dos_itens(_canal(ch.get("channel_label")), ch.get("items") or []))
    else:
        trechos.extend(_trechos_dos_itens(1, res.get("items") or []))
    return sorted(trechos, key=lambda t: (t.inicio_s, t.canal))


def fala_usuario_pct(trechos: list[Trecho]) -> int | None:
    """
    Quanto da conversa foi de quem ligou (canal 0), em % do tempo falado.

    Em ligação de prospecção, o SDR falando 80% do tempo é o sinal de que
    não perguntou nada — é o mesmo indicador do roleplay.

    >>> fala_usuario_pct([Trecho(0, 0, 3, "a"), Trecho(1, 3, 4, "b")])
    75
    >>> fala_usuario_pct([]) is None
    True
    """
    total = sum(max(0.0, t.fim_s - t.inicio_s) for t in trechos)
    if total <= 0:
        return None
    usuario = sum(max(0.0, t.fim_s - t.inicio_s) for t in trechos if t.canal == 0)
    return int(round(100 * usuario / total))


def falas(trechos: list[Trecho], inicio_audio: datetime, nome_usuario: str,
          nome_cliente: str = "Cliente") -> list[Fala]:
    """Trechos → falas com horário de verdade e nome de quem falou."""
    base = _utc(inicio_audio)
    saida = []
    for t in trechos:
        quem = nome_usuario if t.canal == 0 else nome_cliente
        saida.append(Fala(
            inicio=base + timedelta(seconds=t.inicio_s),
            fim=base + timedelta(seconds=t.fim_s),
            participante=quem,
            texto=t.texto,
        ))
    return juntar_falas(saida)


def entradas(trechos: list[Trecho], inicio_audio: datetime, nome_usuario: str,
             nome_cliente: str = "Cliente") -> list[dict]:
    """O que vai para a coluna `transcricao_entradas` (com o canal)."""
    lista = entradas_json(falas(trechos, inicio_audio, nome_usuario, nome_cliente))
    for e in lista:
        e["canal"] = 0 if e["participante"] == nome_usuario else 1
    return lista


def texto(trechos: list[Trecho], inicio_audio: datetime, nome_usuario: str,
          nome_cliente: str = "Cliente") -> str:
    return texto_corrido(falas(trechos, inicio_audio, nome_usuario, nome_cliente))


def primeiro_nome(nome: str | None) -> str:
    """
    >>> primeiro_nome("Kethlleen Gomes")
    'Kethlleen'
    >>> primeiro_nome("")
    'Executivo'
    """
    partes = (nome or "").split()
    return partes[0] if partes else "Executivo"


# ── Passada do coletor ───────────────────────────────────────────────


def clique_expirado(clicada_em: datetime, agora: datetime) -> bool:
    return _utc(agora) - _utc(clicada_em) > EXPIRA_CLIQUE


def envio_expirado(atualizado_em: datetime, agora: datetime) -> bool:
    return _utc(agora) - _utc(atualizado_em) > EXPIRA_ENVIO


def transcricao_expirada(iniciada_em: datetime | None, agora: datetime) -> bool:
    if iniciada_em is None:
        return False
    return _utc(agora) - _utc(iniciada_em) > EXPIRA_TRANSCRICAO


def audio_vencido(inicio_em: datetime | None, criado_em: datetime, agora: datetime,
                  retencao_dias: int) -> bool:
    """O áudio passou da retenção? 0 = guarda para sempre."""
    if retencao_dias <= 0:
        return False
    ref = _utc(inicio_em or criado_em)
    return _utc(agora) - ref > timedelta(days=retencao_dias)


# ── Visão ────────────────────────────────────────────────────────────


def vinculada(oportunidade_id, conta_id) -> bool:
    return oportunidade_id is not None or conta_id is not None


def pode_ver(dono_id, oportunidade_id, conta_id, usuario_id, gestao: bool) -> bool:
    """
    Ligação vinculada é da negociação: quem abre a oportunidade (ou o
    parceiro) ouve, como a transcrição das reuniões. Ligação SEM vínculo
    ainda é só de quem ligou — e da gestão. Pode ser qualquer coisa
    (retorno de cliente, engano), e não aparece para o time até alguém
    dizer de quem é.
    """
    if gestao or str(dono_id) == str(usuario_id):
        return True
    return vinculada(oportunidade_id, conta_id)


def pode_alterar(dono_id, usuario_id, gestao: bool) -> bool:
    """Vincular, descartar, refazer o resumo: quem ligou, ou a gestão."""
    return gestao or str(dono_id) == str(usuario_id)


def resumo_kpis(linhas: list[dict]) -> dict:
    """
    Os números do topo da aba, da MESMA lista que aparece embaixo.

    >>> resumo_kpis([{"status": "pronta", "duracao_s": 120, "fala_usuario_pct": 40},
    ...              {"status": "sem_gravacao", "duracao_s": None, "fala_usuario_pct": None}])
    {'total': 2, 'gravadas': 1, 'minutos': 2, 'transcritas': 1, 'fala_media_pct': 40}
    """
    gravadas = [l for l in linhas if l.get("duracao_s")]
    segundos = sum(l["duracao_s"] for l in gravadas)
    pcts = [l["fala_usuario_pct"] for l in linhas if l.get("fala_usuario_pct") is not None]
    return {
        "total": len(linhas),
        "gravadas": len(gravadas),
        "minutos": int(round(segundos / 60)),
        "transcritas": sum(1 for l in linhas if l.get("status") == "pronta"),
        "fala_media_pct": int(round(sum(pcts) / len(pcts))) if pcts else None,
    }


# ── Apoio ────────────────────────────────────────────────────────────


def _utc(d: datetime) -> datetime:
    if d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def ler_data(valor) -> datetime | None:
    """ISO 8601 do agente → datetime com fuso. Sem fuso = UTC."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return _utc(valor)
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        raise LigacaoInvalida(f"Data inválida: {valor!r}.") from None
    return _utc(d)
