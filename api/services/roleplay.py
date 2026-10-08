"""
HIPO — Roleplay com IA: regras e acesso ao Gemini.

Duas metades, como em services/anexo.py:

  * REGRAS puras (quem pode treinar, limites, custo, validação do que o
    navegador manda no encerramento) — testáveis sem banco, sem rede e sem
    chave. Rodam no pytest local do Windows.
  * ACESSO AO GEMINI no fim do arquivo: um POST para emitir o token
    efêmero. É o único pedaço que os testes dublam.

COMO A CONVERSA ACONTECE. O navegador fala direto com o Gemini Live por
WebSocket (o áudio nunca passa pela EC2). O backend só emite o TOKEN
EFÊMERO, com modelo, persona, voz, transcrição, compressão de contexto e
retomada de sessão TRAVADOS dentro dele (bidiGenerateContentSetup): o
executivo não consegue trocar o prompt do "cliente" pelo DevTools.

O token aceita abrir conexão só nos primeiros 2 minutos
(newSessionExpireTime), e a conexão do Live dura ~10 min. Na troca
(goAway) o navegador pede um token NOVO ao HIPO e retoma pelo handle — o
contexto da conversa vem junto. Foi o que quebrou no PoC (laço de 1011
"new_session_expire_time deadline exceeded") e o que este desenho evita.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from config import settings

# ── Quem treina ──────────────────────────────────────────────────────

# Cargo → trilha de roteiro cujo QUIZ FINAL aprovado libera o roleplay.
# Id fixo da carga de conteúdo (scripts/uc_conteudo.py, "02 · Roteiro do
# EV"). SDR e EC entram quando tiverem cenário e rubrica próprios.
TRILHA_ROTEIRO_POR_CARGO: dict[str, UUID] = {
    "EV": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0100"),
}

CARGOS_GESTAO = frozenset({"Franqueado", "ADM"})

# Versão do termo de ciência da gravação. Mudou o texto → sobe a versão, e
# todo mundo aceita de novo no próximo treino.
TERMO_VERSAO = "2026-10-07"
TERMO_TEXTO = (
    "Este treino grava a sua voz e a voz da IA, e guarda a transcrição. "
    "A gravação serve só para a sua avaliação e o seu desenvolvimento: fica "
    "visível para você e para a gestão (Franqueado e ADM), é apagada em até "
    "180 dias e não entra no Monitor nem na nota das reuniões reais. A voz é "
    "processada pelo Google (Gemini) durante a conversa."
)

# ── Limites ──────────────────────────────────────────────────────────

# Sessão aberta há mais que isso (duração máxima + folga) vira abandonada:
# o navegador fechou sem encerrar.
FOLGA_ABANDONO_MIN = 30
# Teto de tokens efêmeros por sessão: 1 inicial + reconexões. 55 min com
# troca a cada ~10 min dá ~6; 15 cobre quedas de rede sem permitir laço.
MAX_TOKENS_POR_SESSAO = 15

MAX_TURNOS = 3000
MAX_TEXTO_TURNO = 4000
# Abaixo do client_max_body_size 50M do nginx. A 32 kbps, 55 min dão ~13 MB.
MAX_AUDIO_MB = 45
MAX_AUDIO_BYTES = MAX_AUDIO_MB * 1024 * 1024
TIPOS_AUDIO = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}
MOTIVOS_FIM = ("encerrou", "tempo", "queda", "saldo")

# Preço de referência (US$ por 1M de tokens). O Google não publicou tabela
# própria do 3.8-live até 07/10/2026; vale a do 3.1-flash-live como
# referência. O custo da tela é ESTIMATIVA: a verdade é o AI Studio
# (Dashboard > Usage). Corrigir aqui quando a tabela sair.
PRECO_REFERENCIA = {"audio_in": 0.75, "texto_in": 0.75, "audio_out": 4.50, "texto_out": 4.50}
PRECO_POR_MODELO: dict[str, dict[str, float]] = {
    "gemini-3.8-live": PRECO_REFERENCIA,
    "gemini-3.1-flash-live-preview": PRECO_REFERENCIA,
}
CHAVES_TOKENS = ("audio_in", "texto_in", "audio_out", "texto_out", "total")


class RoleplayInvalido(ValueError):
    """Recusa com mensagem pronta para a tela e o status HTTP da recusa."""

    def __init__(self, mensagem: str, status: int = 422, codigo: str = "invalido"):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


@dataclass(frozen=True)
class Liberacao:
    liberado: bool
    motivo: str | None
    trilha_id: UUID | None
    conta_media: bool


def liberacao(cargo: str | None, quiz_aprovado: bool) -> Liberacao:
    """
    Quem pode abrir uma sessão.

    Gestão: sempre, sem trilha, e fora das médias (testa cenário).
    Cargo com trilha de roteiro: só com o quiz final APROVADO — concluir as
    aulas não basta.
    Cargo sem roleplay ainda (SDR, EC, EP...): não libera, e diz por quê.
    """
    if cargo in CARGOS_GESTAO:
        return Liberacao(True, None, None, False)
    trilha = TRILHA_ROTEIRO_POR_CARGO.get(cargo or "")
    if trilha is None:
        return Liberacao(False, "O roleplay ainda não tem cenários para o seu cargo.", None, True)
    if not quiz_aprovado:
        return Liberacao(
            False,
            "Libera quando você for aprovado no quiz final da trilha 02 · Roteiro do EV.",
            trilha, True,
        )
    return Liberacao(True, None, trilha, True)


def checar_limites(*, sessoes_hoje: int, limite_dia: int, gasto_mes_usd: float,
                   orcamento_mes_usd: float, gestao: bool) -> None:
    """Levanta RoleplayInvalido (429/402) se não dá para abrir mais uma sessão hoje."""
    if not gestao and limite_dia > 0 and sessoes_hoje >= limite_dia:
        raise RoleplayInvalido(
            f"Você já fez {sessoes_hoje} roleplay(s) hoje, que é o limite diário. Volte amanhã.",
            429, "limite_dia",
        )
    if orcamento_mes_usd > 0 and gasto_mes_usd >= orcamento_mes_usd:
        raise RoleplayInvalido(
            "O orçamento de IA do roleplay deste mês acabou. Avise a gestão.",
            402, "orcamento",
        )


def limite_abandono(agora: datetime, duracao_max_min: int) -> datetime:
    """Sessão iniciada antes disto e não encerrada é abandonada."""
    return agora - timedelta(minutes=duracao_max_min + FOLGA_ABANDONO_MIN)


# ── Encerramento: o que o navegador manda ────────────────────────────

def normalizar_tokens(bruto) -> dict[str, int]:
    """usageMetadata somado pelo navegador → inteiros >= 0, só as chaves conhecidas."""
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except ValueError:
            bruto = {}
    if not isinstance(bruto, dict):
        bruto = {}
    saida = {}
    for k in CHAVES_TOKENS:
        try:
            v = int(bruto.get(k) or 0)
        except (TypeError, ValueError):
            v = 0
        saida[k] = max(0, min(v, 10**9))
    return saida


def custo_estimado(modelo: str, tokens: dict[str, int]) -> Decimal:
    """US$ estimado da sessão, 4 casas. Modelo desconhecido usa a referência."""
    preco = PRECO_POR_MODELO.get(modelo, PRECO_REFERENCIA)
    total = sum(Decimal(str(tokens.get(k, 0))) * Decimal(str(p)) for k, p in preco.items())
    return (total / Decimal(1_000_000)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def validar_transcricao(bruta) -> list[dict]:
    """
    Turnos [{quem, texto, t_ms}] vindos do navegador. Turno vazio some;
    `quem` fora de executivo/cliente é recusado; texto longo é cortado.
    """
    if bruta is None:
        return []
    if not isinstance(bruta, list):
        raise RoleplayInvalido("Transcrição em formato inválido.")
    if len(bruta) > MAX_TURNOS:
        raise RoleplayInvalido(f"Transcrição acima de {MAX_TURNOS} falas.")
    saida = []
    for t in bruta:
        if not isinstance(t, dict):
            raise RoleplayInvalido("Transcrição em formato inválido.")
        quem = t.get("quem")
        if quem not in ("executivo", "cliente"):
            raise RoleplayInvalido("Cada fala precisa ser do executivo ou do cliente.")
        texto = re.sub(r"\s+", " ", str(t.get("texto") or "")).strip()
        if not texto:
            continue
        try:
            t_ms = max(0, int(t.get("t_ms") or 0))
        except (TypeError, ValueError):
            t_ms = 0
        saida.append({"quem": quem, "texto": texto[:MAX_TEXTO_TURNO], "t_ms": t_ms})
    return saida


def fala_executivo_pct(transcricao: list[dict]) -> int | None:
    """% das palavras ditas pelo executivo. Sem fala nenhuma → None."""
    pal = {"executivo": 0, "cliente": 0}
    for t in transcricao:
        pal[t["quem"]] += len(t["texto"].split())
    total = pal["executivo"] + pal["cliente"]
    if total == 0:
        return None
    return round(100 * pal["executivo"] / total)


def validar_motivo(motivo: str | None) -> str:
    m = (motivo or "encerrou").strip().lower()
    if m not in MOTIVOS_FIM:
        raise RoleplayInvalido(f"Motivo de fim inválido. Aceitos: {', '.join(MOTIVOS_FIM)}.")
    return m


def validar_inteiro(valor, nome: str, minimo: int = 0, maximo: int = 10**7) -> int | None:
    if valor is None or valor == "":
        return None
    try:
        v = int(round(float(valor)))
    except (TypeError, ValueError):
        raise RoleplayInvalido(f"{nome} inválido.") from None
    return max(minimo, min(v, maximo))


def validar_audio(tipo_mime: str | None, tamanho: int) -> str:
    """Extensão do arquivo, ou RoleplayInvalido."""
    tipo = (tipo_mime or "").split(";")[0].strip().lower()
    if tipo not in TIPOS_AUDIO:
        raise RoleplayInvalido("Gravação em formato não aceito (esperado WebM/Opus).")
    if tamanho <= 0:
        raise RoleplayInvalido("Gravação vazia.")
    if tamanho > MAX_AUDIO_BYTES:
        raise RoleplayInvalido(f"Gravação acima de {MAX_AUDIO_MB} MB.")
    return TIPOS_AUDIO[tipo]


def chave_audio(usuario_id: UUID | str, sessao_id: UUID | str, extensao: str) -> str:
    """Caminho no bucket, só de ids. Prefixo próprio para a regra de retenção de 180 dias."""
    return f"roleplay/{usuario_id}/{sessao_id}{extensao}"


def duracao_s(iniciada_em: datetime, agora: datetime, informada: int | None,
              duracao_max_min: int) -> int:
    """
    Duração gravada. Vale a que o navegador mediu, mas nunca acima do tempo
    real desde a abertura (relógio do servidor) nem do teto da sessão.
    """
    real = max(0, int((agora - iniciada_em).total_seconds()))
    teto = min(real, duracao_max_min * 60 + 120)
    if informada is None:
        return teto
    return max(0, min(informada, teto))


# ── Próximo roleplay ─────────────────────────────────────────────────

def proximo_cenario(cenarios: list[tuple[str, dict]], feitos: set[str]) -> str | None:
    """
    O cartão "Seu próximo roleplay" (RP-1): o primeiro bloco ainda não
    feito, na ordem de dificuldade; feitos os blocos, a reunião completa;
    tudo feito, o primeiro bloco de novo. A RP-3 troca isto pelo item mais
    fraco das avaliações.
    """
    if not cenarios:
        return None
    blocos = [k for k, c in cenarios if c["formato"] == "bloco"]
    completas = [k for k, c in cenarios if c["formato"] == "completa"]
    for k in blocos + completas:
        if k not in feitos:
            return k
    return (blocos or completas)[0]


# ── Gemini: configuração travada no token ────────────────────────────

URL_TOKENS = "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
URL_WS = ("wss://generativelanguage.googleapis.com/ws/"
          "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained")

# Janela deslizante: dispara em 25k tokens e volta para 12k. Sem isso, 45
# min de áudio (25 tokens/s) chegam perto dos 128k e o custo por minuto
# cresce a cada turno.
COMPRESSAO_GATILHO = 25_000
COMPRESSAO_ALVO = 12_000


def setup_live(modelo: str, instrucao: str, voz: str) -> dict:
    """bidiGenerateContentSetup que vai travado no token (JSON da API REST)."""
    return {
        "model": f"models/{modelo}",
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "languageCode": "pt-BR",
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}},
            },
        },
        "systemInstruction": {"parts": [{"text": instrucao}], "role": "user"},
        "sessionResumption": {},
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "contextWindowCompression": {
            "triggerTokens": COMPRESSAO_GATILHO,
            "slidingWindow": {"targetTokens": COMPRESSAO_ALVO},
        },
    }


def corpo_token(setup: dict, agora: datetime) -> dict:
    """
    Token de uso único: 2 min para abrir a conexão, 30 min de vida. A
    conexão troca a cada ~10 min, e cada troca pede um token novo.
    """
    return {
        "uses": 1,
        "expireTime": (agora + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        "newSessionExpireTime": (agora + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "bidiGenerateContentSetup": setup,
    }


class GeminiIndisponivel(RuntimeError):
    """O Google recusou ou não respondeu. `sem_saldo` = cobrança/cota."""

    def __init__(self, mensagem: str, sem_saldo: bool = False):
        super().__init__(mensagem)
        self.sem_saldo = sem_saldo


def problemas() -> list[str]:
    """O que impede o roleplay de funcionar, para a tela e o diagnóstico."""
    return [] if settings.GEMINI_API_KEY else [
        "GEMINI_API_KEY não configurada no .env (e o serviço precisa ser reiniciado)."
    ]


def disponivel() -> bool:
    return not problemas()


_SEM_SALDO = re.compile(r"billing|quota|credit|exhaust|prepay|RESOURCE_EXHAUSTED", re.I)


async def emitir_token(setup: dict, agora: datetime | None = None) -> str:
    """POST auth_tokens. Devolve o `name` do token (o que o navegador usa)."""
    import httpx

    if not settings.GEMINI_API_KEY:
        raise GeminiIndisponivel("Roleplay desligado: falta a chave do Gemini no servidor.")
    agora = agora or datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.post(
                URL_TOKENS,
                headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                json=corpo_token(setup, agora),
            )
    except httpx.HTTPError as e:
        raise GeminiIndisponivel(f"Gemini não respondeu ({type(e).__name__}).") from e
    if r.status_code >= 400:
        texto = r.text[:500]
        try:
            detalhe = str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
        except ValueError:
            detalhe = ""
        raise GeminiIndisponivel(
            f"Gemini recusou o token ({r.status_code}){': ' + detalhe if detalhe else ''}.",
            sem_saldo=r.status_code in (402, 429) or bool(_SEM_SALDO.search(texto)),
        )
    nome = (r.json() or {}).get("name")
    if not nome:
        raise GeminiIndisponivel("Gemini respondeu sem token.")
    return nome
