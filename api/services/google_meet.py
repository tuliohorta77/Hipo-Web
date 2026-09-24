"""
HIPO — Google Meet: ligar a transcrição e buscar as falas.

Mesma conta de serviço e mesma delegação em todo o domínio da agenda
(services/google_agenda.py): o HIPO age COMO o anfitrião, porque a sala do
Meet é dele — foi criada pelo evento que mora no calendário dele.

═══ COMO LIGAR (uma vez, além do que a agenda já pediu) ═══════════════

  1. Cloud Console, projeto `hipo-agenda` → habilitar a **Google Meet
     REST API**.
  2. Admin Console → Segurança → Controles de API → Delegação em todo o
     domínio → editar o Client ID da `hipo-calendar` e deixar os escopos
     assim (separados por vírgula):
       https://www.googleapis.com/auth/calendar.events,
       https://www.googleapis.com/auth/meetings.space.readonly,
       https://www.googleapis.com/auth/meetings.space.settings
  3. Admin Console → Apps → Google Workspace → Google Meet → Configurações
     de vídeo do Meet → **Transcrições**: ativado.

Nada no .env: é o mesmo `GOOGLE_SA_ARQUIVO`.

═══ ESCOPOS SEPARADOS DE PROPÓSITO ══════════════════════════════════════

Cada operação pede SÓ o escopo de que precisa, e não o conjunto. Com
delegação em todo o domínio, pedir um escopo que o Admin Console ainda não
autorizou faz o Google recusar o token INTEIRO (`unauthorized_client`).
Pedindo por operação:

  * a agenda (calendar.events) nunca é afetada por nada daqui;
  * sem `meetings.space.settings`, a transcrição automática não é ligada,
    mas a COLETA segue funcionando para quem ligou à mão na call;
  * sem `meetings.space.readonly`, a coleta falha e diz por quê.

═══ REST DIRETO, E NÃO O CLIENTE GERADO ═════════════════════════════════

O `googleapiclient` usa um documento de discovery EMBUTIDO no pacote, e o
da versão instalada (2.149.0) é anterior ao `artifactConfig` — o campo que
liga a transcrição automática não existe para ele. Em vez de trocar a
versão da biblioteca em produção (o deploy não roda pip), as chamadas vão
por `AuthorizedSession`, que já vem no `google-auth`: é um `requests` com o
token injetado, e a URL é a da documentação.

As três regras de google_agenda.py valem aqui igual: desligado é estado
válido, falha não derruba nada, e falha não é silenciosa (vira coluna).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import quote

from config import settings
from services import google_agenda
from services import transcricao as regras
from services.transcricao import Conferencia, Fala, Transcricao

log = logging.getLogger("hipo.google_meet")

BASE = "https://meet.googleapis.com/v2"
ESCOPO_LEITURA = "https://www.googleapis.com/auth/meetings.space.readonly"
ESCOPO_CONFIG = "https://www.googleapis.com/auth/meetings.space.settings"
TIMEOUT_S = 30
TAMANHO_PAGINA = 100
# Teto de páginas por listagem. Uma reunião de 2h tem algumas centenas de
# entradas; mil páginas de cem só existiriam num laço de paginação quebrado
# do outro lado — e aí é melhor parar do que girar para sempre.
MAX_PAGINAS = 1000


@dataclass(frozen=True)
class ResultadoMeet:
    ok: bool
    erro: str | None = None


@dataclass(frozen=True)
class Levantamento:
    """O que existe no Google para a sala. `erro` preenchido = não deu para saber."""
    conferencias: tuple[Conferencia, ...] = ()
    erro: str | None = None


@dataclass(frozen=True)
class Download:
    falas: tuple[Fala, ...] = ()
    idioma: str | None = None
    documento_url: str | None = None
    erro: str | None = None
    conferencias: tuple[str, ...] = field(default_factory=tuple)


class ErroMeet(Exception):
    """Erro já traduzido para português, pronto para ir para a coluna."""


# ── Configuração ─────────────────────────────────────────────────────


def configurado() -> bool:
    """Mesma chave da agenda. Sem ela, não há transcrição."""
    return google_agenda.configurado()


def problemas() -> list[str]:
    return google_agenda.problemas()


# ── Sessão ───────────────────────────────────────────────────────────


def _sessao(email: str, escopo: str):  # pragma: no cover - exige credencial
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    cred = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_ARQUIVO, scopes=[escopo]
    ).with_subject(email)
    return AuthorizedSession(cred)


def _traduzir(status: int | None, corpo: str, escopo: str) -> str:
    """
    Resposta do Google em uma frase que diz O QUE fazer.

    >>> "Delegação" in _traduzir(None, "unauthorized_client", ESCOPO_LEITURA)
    True
    >>> "Meet REST API" in _traduzir(403, "SERVICE_DISABLED", ESCOPO_LEITURA)
    True
    >>> "não existe" in _traduzir(404, "", ESCOPO_LEITURA)
    True
    """
    texto = (corpo or "")[:300]
    if "unauthorized_client" in texto or "access_denied" in texto:
        return (
            "O Google recusou o acesso ao Meet. Confira a Delegação em todo "
            f"o domínio no Admin Console: falta o escopo {escopo}."
        )
    if status == 403 and ("SERVICE_DISABLED" in texto or "has not been used" in texto):
        return (
            "A Google Meet REST API não está habilitada no projeto "
            "hipo-agenda do Cloud Console."
        )
    if status == 403:
        return f"O Google recusou a operação no Meet (403): {texto}"
    if status == 404:
        return "A sala do Meet não existe ou não pertence ao anfitrião."
    if status == 429:
        return "Limite de chamadas do Google atingido; tenta de novo na próxima passada."
    return f"Não foi possível falar com o Google Meet ({status}): {texto}"


def _pedir(sessao, metodo: str, url: str, escopo: str, **kw) -> dict:
    try:
        resp = sessao.request(metodo, url, timeout=TIMEOUT_S, **kw)
    except Exception as e:  # rede, DNS, credencial inválida no refresh
        raise ErroMeet(_traduzir(None, f"{type(e).__name__}: {e}", escopo)) from e
    if resp.status_code >= 400:
        raise ErroMeet(_traduzir(resp.status_code, resp.text, escopo))
    return resp.json() if resp.content else {}


def _listar(sessao, url: str, chave: str, escopo: str, params: dict | None = None) -> list[dict]:
    itens: list[dict] = []
    token = None
    for _ in range(MAX_PAGINAS):
        p = dict(params or {}, pageSize=TAMANHO_PAGINA)
        if token:
            p["pageToken"] = token
        corpo = _pedir(sessao, "GET", url, escopo, params=p)
        itens.extend(corpo.get(chave) or [])
        token = corpo.get("nextPageToken")
        if not token:
            break
    return itens


# ── Ligar a transcrição automática ───────────────────────────────────


def _ligar_sync(email: str, codigo: str) -> ResultadoMeet:
    try:
        sessao = _sessao(email, ESCOPO_CONFIG)
        # O PATCH exige o id do recurso (`spaces/jQCF...`), e o que o evento
        # do Calendar entrega é o código da sala. O GET aceita o código como
        # alias e devolve o id.
        espaco = _pedir(sessao, "GET", f"{BASE}/spaces/{quote(codigo)}", ESCOPO_CONFIG)
        nome = espaco.get("name")
        if not nome:
            return ResultadoMeet(False, "O Google não devolveu o id da sala do Meet.")
        _pedir(
            sessao, "PATCH", f"{BASE}/{nome}", ESCOPO_CONFIG,
            params={"updateMask": "config.artifactConfig.transcriptionConfig"},
            json={"config": {"artifactConfig": {
                "transcriptionConfig": {"autoTranscriptionGeneration": "ON"},
            }}},
        )
    except ErroMeet as e:
        return ResultadoMeet(False, str(e))
    except Exception as e:  # blindagem: arquivo da chave, import
        return ResultadoMeet(False, f"Falha ao ligar a transcrição: {e}")
    return ResultadoMeet(True)


async def ligar_transcricao(email_anfitriao: str, codigo: str) -> ResultadoMeet:
    """Liga a transcrição automática da sala. Nunca levanta."""
    if not configurado():
        return ResultadoMeet(False, "Integração com o Google não configurada neste servidor.")
    faltando = problemas()
    if faltando:
        return ResultadoMeet(False, "; ".join(faltando))
    r = await asyncio.to_thread(_ligar_sync, email_anfitriao, codigo)
    _registrar("ligar", email_anfitriao, codigo, r.erro)
    return r


# ── Levantar o que existe ────────────────────────────────────────────


def _conferencia(bruta: dict, transcricoes: list[dict]) -> Conferencia:
    return Conferencia(
        nome=bruta.get("name") or "",
        inicio=regras.data_do_google(bruta.get("startTime")),
        fim=regras.data_do_google(bruta.get("endTime")),
        transcricoes=tuple(
            Transcricao(
                nome=t.get("name") or "",
                estado=t.get("state") or "STATE_UNSPECIFIED",
                documento_url=(t.get("docsDestination") or {}).get("exportUri"),
            )
            for t in transcricoes if t.get("name")
        ),
    )


def _levantar_sync(email: str, codigo: str) -> Levantamento:
    try:
        sessao = _sessao(email, ESCOPO_LEITURA)
        brutas = _listar(
            sessao, f"{BASE}/conferenceRecords", "conferenceRecords", ESCOPO_LEITURA,
            params={"filter": f'space.meeting_code = "{codigo}"'},
        )
        confs = []
        for c in brutas:
            if not c.get("name") or not c.get("startTime"):
                continue
            ts = _listar(
                sessao, f"{BASE}/{c['name']}/transcripts", "transcripts", ESCOPO_LEITURA,
            )
            confs.append(_conferencia(c, ts))
    except ErroMeet as e:
        return Levantamento(erro=str(e))
    except Exception as e:
        return Levantamento(erro=f"Falha ao consultar o Meet: {e}")
    return Levantamento(conferencias=tuple(confs))


async def levantar(email_anfitriao: str, codigo: str) -> Levantamento:
    """As conferências da sala e as transcrições de cada uma. Nunca levanta."""
    if not configurado():
        return Levantamento(erro="Integração com o Google não configurada neste servidor.")
    faltando = problemas()
    if faltando:
        return Levantamento(erro="; ".join(faltando))
    r = await asyncio.to_thread(_levantar_sync, email_anfitriao, codigo)
    _registrar("levantar", email_anfitriao, codigo, r.erro)
    return r


# ── Baixar as falas ──────────────────────────────────────────────────


def _baixar_sync(email: str, conferencias: tuple[Conferencia, ...]) -> Download:
    try:
        sessao = _sessao(email, ESCOPO_LEITURA)
        falas: list[Fala] = []
        idiomas: dict[str, int] = {}
        documento = None
        for conf in conferencias:
            participantes = _listar(
                sessao, f"{BASE}/{conf.nome}/participants", "participants", ESCOPO_LEITURA,
            )
            nomes = {p.get("name"): regras.nome_do_participante(p) for p in participantes}
            for t in conf.transcricoes:
                documento = documento or t.documento_url
                entradas = _listar(
                    sessao, f"{BASE}/{t.nome}/entries", "transcriptEntries", ESCOPO_LEITURA,
                )
                for e in entradas:
                    inicio = regras.data_do_google(e.get("startTime"))
                    if inicio is None:
                        continue
                    idioma = e.get("languageCode")
                    if idioma:
                        idiomas[idioma] = idiomas.get(idioma, 0) + 1
                    falas.append(Fala(
                        inicio=inicio,
                        fim=regras.data_do_google(e.get("endTime")),
                        participante=nomes.get(e.get("participant"), "Participante"),
                        texto=e.get("text") or "",
                    ))
    except ErroMeet as e:
        return Download(erro=str(e))
    except Exception as e:
        return Download(erro=f"Falha ao baixar a transcrição: {e}")
    idioma = max(idiomas, key=idiomas.get) if idiomas else None
    return Download(
        falas=tuple(falas), idioma=idioma, documento_url=documento,
        conferencias=tuple(c.nome for c in conferencias),
    )


async def baixar(email_anfitriao: str, conferencias: tuple[Conferencia, ...]) -> Download:
    """As falas de todas as transcrições das conferências. Nunca levanta."""
    if not configurado():
        return Download(erro="Integração com o Google não configurada neste servidor.")
    r = await asyncio.to_thread(_baixar_sync, email_anfitriao, conferencias)
    _registrar("baixar", email_anfitriao, ",".join(c.nome for c in conferencias), r.erro)
    return r


def _registrar(op: str, email: str, alvo: str, erro: str | None) -> None:
    if erro:
        log.warning("google_meet: %s falhou (%s, %s): %s", op, email, alvo, erro)
    else:
        log.info("google_meet: %s ok (%s, %s)", op, email, alvo)
