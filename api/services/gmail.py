"""
HIPO — Gmail: enviar o e-mail comercial da caixa do vendedor e saber se o
cliente respondeu (entrega 050).

Mesma conta de serviço e mesma delegação em todo o domínio da agenda
(services/google_agenda.py) e do Meet (services/google_meet.py): o HIPO age
COMO o vendedor (`with_subject`), então o e-mail sai da caixa dele, fica na
pasta Enviados dele e a resposta do cliente cai na caixa de entrada dele.

═══ COMO LIGAR (uma vez, além do que a agenda já pediu) ═══════════════

  1. Cloud Console, projeto `hipo-agenda` → habilitar a **Gmail API**.
  2. Admin Console → Segurança → Controles de API → Delegação em todo o
     domínio → editar o Client ID da `hipo-calendar` e ACRESCENTAR aos
     escopos que já estão lá (separados por vírgula):
       https://www.googleapis.com/auth/gmail.send,
       https://www.googleapis.com/auth/gmail.settings.basic,
       https://www.googleapis.com/auth/gmail.metadata
     Editar substitui a lista inteira: os escopos do Calendar e do Meet
     precisam continuar nela.

Nada no .env: é o mesmo `GOOGLE_SA_ARQUIVO`. Nenhuma biblioteca nova: as
chamadas vão por `AuthorizedSession`, que já vem no `google-auth`.

═══ UM ESCOPO POR OPERAÇÃO ════════════════════════════════════════════

Mesmo motivo do Meet: com delegação, pedir um escopo que o Admin Console
ainda não autorizou faz o Google recusar o token INTEIRO. Pedindo por
operação:

  * `gmail.send` — envia. Sem ele, nada sai, e a tela diz por quê.
  * `gmail.settings.basic` — lê a assinatura. Sem ele o e-mail sai igual,
    sem assinatura, e o rascunho AVISA antes de o vendedor clicar.
  * `gmail.metadata` — lê só cabeçalhos e rótulos do fio, nunca o corpo da
    resposta do cliente. É o mínimo para saber SE respondeu.

═══ AS TRÊS REGRAS DE google_agenda.py VALEM AQUI ═════════════════════

Desligado é estado válido; nada aqui levanta até o router; e falha não é
silenciosa. Diferença: aqui quem chama é uma TELA, com o vendedor olhando.
O envio que falhou não é gravado — ele recebe o erro em português na hora
e tenta de novo. Gravar um "e-mail com erro" criaria um registro de algo
que o cliente nunca viu.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from services import google_agenda

log = logging.getLogger("hipo.gmail")

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
UPLOAD = "https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send"

ESCOPO_ENVIO = "https://www.googleapis.com/auth/gmail.send"
ESCOPO_ASSINATURA = "https://www.googleapis.com/auth/gmail.settings.basic"
ESCOPO_LEITURA = "https://www.googleapis.com/auth/gmail.metadata"

TIMEOUT_S = 60

# A assinatura muda raramente e é lida a cada rascunho. Dez minutos de
# cache por processo poupam uma ida ao Google por e-mail sem deixar o
# vendedor que acabou de trocar a assinatura esperando muito.
CACHE_ASSINATURA_S = 600
_cache_assinatura: dict[str, tuple[float, "Assinatura"]] = {}


@dataclass(frozen=True)
class Assinatura:
    html: str | None = None
    erro: str | None = None


@dataclass(frozen=True)
class ResultadoEnvio:
    ok: bool
    message_id: str | None = None
    thread_id: str | None = None
    erro: str | None = None


@dataclass(frozen=True)
class ResultadoFio:
    thread: dict | None = None
    erro: str | None = None


class ErroGmail(Exception):
    """Erro já traduzido para português."""


# ── Configuração ─────────────────────────────────────────────────────

def configurado() -> bool:
    return google_agenda.configurado()


def problemas() -> list[str]:
    return google_agenda.problemas()


def _sessao(email: str, escopo: str):  # pragma: no cover - exige credencial
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    from config import settings

    cred = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_ARQUIVO, scopes=[escopo]
    ).with_subject(email)
    return AuthorizedSession(cred)


def traduzir(status: int | None, corpo: str, escopo: str) -> str:
    """
    Resposta do Google em uma frase que diz O QUE fazer.

    >>> "Delegação" in traduzir(None, "unauthorized_client", ESCOPO_ENVIO)
    True
    >>> "Gmail API" in traduzir(403, "SERVICE_DISABLED", ESCOPO_ENVIO)
    True
    >>> "Workspace" in traduzir(None, "invalid_grant: Invalid email", ESCOPO_ENVIO)
    True
    """
    texto = (corpo or "")[:300]
    if "unauthorized_client" in texto or "access_denied" in texto:
        return (
            "O Google recusou o acesso ao Gmail. Confira a Delegação em todo "
            f"o domínio no Admin Console: falta o escopo {escopo}."
        )
    if "invalid_grant" in texto:
        return (
            "O seu e-mail do HIPO não é uma caixa do Google Workspace da "
            "empresa, então o Gmail não pode enviar por você. Peça para a "
            "gestão conferir o e-mail do seu usuário."
        )
    if status == 403 and ("SERVICE_DISABLED" in texto or "has not been used" in texto):
        return "A Gmail API não está habilitada no projeto hipo-agenda do Cloud Console."
    if status == 400:
        return f"O Gmail recusou a mensagem: {texto}"
    if status == 403:
        return f"O Gmail recusou a operação (403): {texto}"
    if status == 404:
        return "A conversa não existe mais na caixa do remetente."
    if status == 429:
        return "Limite de envios do Gmail atingido. Tente de novo em alguns minutos."
    return f"Não foi possível falar com o Gmail ({status}): {texto}"


def _pedir(sessao, metodo: str, url: str, escopo: str, **kw) -> dict:
    try:
        resp = sessao.request(metodo, url, timeout=TIMEOUT_S, **kw)
    except Exception as e:  # rede, DNS, credencial inválida no refresh
        raise ErroGmail(traduzir(None, f"{type(e).__name__}: {e}", escopo)) from e
    if resp.status_code >= 400:
        raise ErroGmail(traduzir(resp.status_code, resp.text, escopo))
    return resp.json() if resp.content else {}


# ── Assinatura ───────────────────────────────────────────────────────

def escolher_assinatura(lista_send_as: dict, email: str) -> str | None:
    """
    A assinatura do endereço que vai no From; senão a do principal.

    >>> escolher_assinatura({"sendAs": [
    ...     {"sendAsEmail": "outro@x.com", "isPrimary": True, "signature": "P"},
    ...     {"sendAsEmail": "Eu@x.com", "signature": "E"}]}, "eu@x.com")
    'E'
    >>> escolher_assinatura({"sendAs": [{"sendAsEmail": "a@x.com", "isPrimary": True,
    ...     "signature": ""}]}, "b@x.com") is None
    True
    """
    itens = lista_send_as.get("sendAs") or []
    alvo = (email or "").lower()
    escolhido = next(
        (s for s in itens if (s.get("sendAsEmail") or "").lower() == alvo), None
    ) or next((s for s in itens if s.get("isPrimary")), None)
    assinatura = (escolhido or {}).get("signature") or ""
    return assinatura.strip() or None


def _assinatura_sync(email: str) -> Assinatura:  # pragma: no cover - rede
    try:
        sessao = _sessao(email, ESCOPO_ASSINATURA)
        dados = _pedir(sessao, "GET", f"{BASE}/settings/sendAs", ESCOPO_ASSINATURA)
    except ErroGmail as e:
        return Assinatura(erro=str(e))
    except Exception as e:
        return Assinatura(erro=traduzir(None, f"{type(e).__name__}: {e}", ESCOPO_ASSINATURA))
    return Assinatura(html=escolher_assinatura(dados, email))


async def assinatura(email: str) -> Assinatura:
    """A assinatura do Gmail do vendedor. Nunca levanta."""
    if not configurado():
        return Assinatura(erro="Integração com o Google não configurada neste servidor.")
    chave = (email or "").lower()
    agora = time.monotonic()
    guardada = _cache_assinatura.get(chave)
    if guardada and agora - guardada[0] < CACHE_ASSINATURA_S:
        return guardada[1]
    resultado = await asyncio.to_thread(_assinatura_sync, email)
    # Só guarda o que deu certo: um erro de delegação corrigido no Admin
    # Console não pode continuar aparecendo por dez minutos.
    if resultado.erro is None:
        _cache_assinatura[chave] = (agora, resultado)
    else:
        log.warning("gmail: assinatura de %s: %s", email, resultado.erro)
    return resultado


# ── Envio ────────────────────────────────────────────────────────────

def _enviar_sync(email: str, mensagem: bytes) -> ResultadoEnvio:  # pragma: no cover
    try:
        sessao = _sessao(email, ESCOPO_ENVIO)
        # uploadType=media com o RFC 822 cru: aceita até 35 MB. O JSON com
        # `raw` em base64 tem teto bem menor e o PDF da proposta passa dele.
        dados = _pedir(
            sessao, "POST", UPLOAD, ESCOPO_ENVIO,
            params={"uploadType": "media"},
            data=mensagem,
            headers={"Content-Type": "message/rfc822"},
        )
    except ErroGmail as e:
        return ResultadoEnvio(ok=False, erro=str(e))
    except Exception as e:
        return ResultadoEnvio(ok=False, erro=traduzir(None, f"{type(e).__name__}: {e}", ESCOPO_ENVIO))
    if not dados.get("id"):
        return ResultadoEnvio(ok=False, erro="O Gmail não devolveu o id da mensagem enviada.")
    return ResultadoEnvio(ok=True, message_id=dados["id"], thread_id=dados.get("threadId"))


async def enviar(email: str, mensagem: bytes) -> ResultadoEnvio:
    """Envia da caixa de `email`. Nunca levanta."""
    if not configurado():
        return ResultadoEnvio(
            ok=False, erro="Integração com o Google não configurada neste servidor.",
        )
    faltando = problemas()
    if faltando:
        return ResultadoEnvio(ok=False, erro="; ".join(faltando))
    resultado = await asyncio.to_thread(_enviar_sync, email, mensagem)
    if resultado.ok:
        log.info("gmail: enviado (%s, msg=%s)", email, resultado.message_id)
    else:
        log.warning("gmail: envio falhou (%s): %s", email, resultado.erro)
    return resultado


# ── Fio da conversa ──────────────────────────────────────────────────

def _fio_sync(email: str, thread_id: str) -> ResultadoFio:  # pragma: no cover
    try:
        sessao = _sessao(email, ESCOPO_LEITURA)
        dados = _pedir(
            sessao, "GET", f"{BASE}/threads/{thread_id}", ESCOPO_LEITURA,
            params=[("format", "metadata"), ("metadataHeaders", "From"),
                    ("metadataHeaders", "Date")],
        )
    except ErroGmail as e:
        return ResultadoFio(erro=str(e))
    except Exception as e:
        return ResultadoFio(erro=traduzir(None, f"{type(e).__name__}: {e}", ESCOPO_LEITURA))
    return ResultadoFio(thread=dados)


async def fio(email: str, thread_id: str) -> ResultadoFio:
    """Cabeçalhos e rótulos do fio, sem corpo. Nunca levanta."""
    if not configurado():
        return ResultadoFio(erro="Integração com o Google não configurada neste servidor.")
    return await asyncio.to_thread(_fio_sync, email, thread_id)
