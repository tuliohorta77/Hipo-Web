"""
HIPO -- observabilidade: erros de producao no Sentry.

Antes disto, erro 500 chegava por reclamacao de usuario. Com o DSN no
.env, toda excecao nao tratada da API e todo `log.error(...)` viram um
"issue" no Sentry, com stack trace, rota, cargo de quem chamou e as linhas
de log que vieram antes (breadcrumbs). O alerta por e-mail e regra do
proprio Sentry -- ver claude/observabilidade-sentry.md.

O QUE NAO SAI DAQUI, DE PROPOSITO (LGPD)

Um erro no meio de GET /crm/contatos carregaria telefone, e-mail e
aniversario de cliente para um servidor de terceiro. Por isso:

  * send_default_pii=False -- sem IP do usuario, cookie ou header de
    autorizacao.
  * max_request_body_size="never" -- corpo de request nunca vai (o do
    login tem a senha; o do contato tem o dado pessoal).
  * include_local_variables=False -- variavel local de frame e onde mora
    a linha do banco que estava sendo processada. Perde-se um pouco de
    contexto no debug; e o preco de o stack trace nao virar copia da base.
  * querystring cortada no before_send -- `?q=` da busca de contato e o
    nome ou telefone de alguem.
  * usuario identificado por ID e cargo, nunca por e-mail.

O mesmo cuidado da telemetria (migrations/007): o log nao herda o
controle de acesso da tabela de origem, entao o dado pessoal nao vai para
o log.

SEM DSN, NADA. Mesma regra do SES, do S3 e da chave da IA: recurso
acessorio desligado nao impede a API de subir. Sem o pacote instalado
tambem nao: o deploy faz rsync e reinicia, nao roda pip install
(requirements.txt), e um import quebrado aqui derrubaria a API inteira por
causa de um recurso de diagnostico.
"""
from __future__ import annotations

import logging

log = logging.getLogger("hipo.observabilidade")

# Estado do processo. `ativo()` e o que o /health mostra.
_ATIVO = False


def ativo() -> bool:
    return _ATIVO


def ambiente_padrao(environment: str, sigla: str) -> str:
    """
    'production' na base principal, 'production-mos' na MOS.

    >>> ambiente_padrao("production", "")
    'production'
    >>> ambiente_padrao("production", "MOS")
    'production-mos'
    """
    base = (environment or "production").strip() or "production"
    sigla = (sigla or "").strip().lower()
    return f"{base}-{sigla}" if sigla else base


def limpar_evento(evento: dict, _hint: dict | None = None) -> dict:
    """
    before_send: tira do evento o que pode carregar dado pessoal.

    Pura sobre o dict do evento, para ser testada sem Sentry instalado.
    Devolve o proprio evento (o SDK descarta se devolver None -- aqui nunca
    descartamos, so podamos).
    """
    req = evento.get("request")
    if isinstance(req, dict):
        if req.get("query_string"):
            req["query_string"] = "[cortado]"
        req.pop("data", None)
        req.pop("cookies", None)
        cabecalhos = req.get("headers")
        if isinstance(cabecalhos, dict):
            for nome in list(cabecalhos):
                if nome.lower() in ("authorization", "cookie", "x-real-ip", "x-forwarded-for"):
                    cabecalhos[nome] = "[cortado]"
        url = req.get("url")
        if isinstance(url, str) and "?" in url:
            req["url"] = url.split("?", 1)[0]

    usuario = evento.get("user")
    if isinstance(usuario, dict):
        for campo in ("email", "ip_address", "username"):
            usuario.pop(campo, None)

    return evento


def iniciar(
    dsn: str,
    *,
    ambiente: str,
    release: str,
    traces_sample_rate: float = 0.0,
    instancia: str = "",
) -> bool:
    """
    Liga o Sentry neste processo. Devolve True se ligou.

    Chamado UMA vez, no import de main.py (antes de `FastAPI(...)`, que e
    quando as integracoes de Starlette/FastAPI precisam estar presentes) e
    no inicio dos scripts de timer.
    """
    global _ATIVO
    if not (dsn or "").strip():
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        log.warning(
            "SENTRY_DSN configurado mas o pacote sentry-sdk nao esta instalado "
            "neste python -- rodar infra/instalar-sentry.sh. Seguindo sem Sentry."
        )
        return False

    try:
        sentry_sdk.init(
            dsn=dsn.strip(),
            environment=ambiente,
            release=release,
            traces_sample_rate=max(0.0, min(1.0, float(traces_sample_rate or 0.0))),
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=limpar_evento,
            integrations=[
                # INFO e acima vira breadcrumb (o "o que aconteceu antes");
                # ERROR e acima vira issue -- e o alerta.
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        if instancia:
            sentry_sdk.set_tag("instancia", instancia)
    except Exception as e:  # pragma: no cover - blindagem
        log.warning("Sentry nao inicializou (%s); seguindo sem ele", e)
        return False

    _ATIVO = True
    log.info("Sentry ligado: ambiente=%s release=%s", ambiente, release)
    return True


def marcar_usuario(user: dict | None) -> None:
    """
    Identifica quem estava na request -- por ID e cargo, sem e-mail.

    No-op sem Sentry. Chamado de `usuario_atual`, que roda em toda rota
    protegida; o escopo e isolado por request pela integracao de ASGI.
    """
    if not _ATIVO or not user:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_user({"id": str(user.get("id"))})
        cargo = user.get("cargo")
        if cargo:
            sentry_sdk.set_tag("cargo", cargo)
    except Exception:  # pragma: no cover - blindagem
        pass
