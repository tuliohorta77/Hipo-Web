"""
HIPO — Envio de e-mail pelo Amazon SES.

Usa SES v2 via boto3. As credenciais saem da cadeia padrão do AWS SDK: se a
EC2 tiver IAM role, nada precisa ir para o .env — que é o arranjo preferido,
porque credencial que não existe em arquivo não vaza em backup. Sem role,
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY no ambiente também funcionam.

boto3 é síncrono. Não é problema: quem chama é o script de fechamento, um
processo de uma tarefa só. Este módulo não é importado pela API — se um dia
for, o envio precisa ir para uma thread.

SANDBOX DO SES: conta nova só entrega para endereços verificados. Se o
relatório "envia com sucesso" e não chega, é quase sempre isso, e não o
código aqui. `verificar_configuracao()` existe para dar esse diagnóstico
antes de agendar o timer.
"""
from __future__ import annotations

import logging

from config import settings

log = logging.getLogger("hipo.email")


class EnvioNaoConfigurado(RuntimeError):
    """Falta remetente ou destinatário. Erro de configuração, não de rede."""


def destinatarios() -> list[str]:
    """Lista do .env, separada por vírgula, sem vazios e sem espaços."""
    bruto = getattr(settings, "RELATORIO_DESTINATARIOS", "") or ""
    return [e.strip() for e in bruto.split(",") if e.strip()]


def verificar_configuracao() -> list[str]:
    """
    Devolve a lista de problemas encontrados. Vazia = pronto para enviar.

    Checagem local, sem chamar a AWS: serve para o script falhar cedo com
    mensagem clara em vez de estourar um ClientError críptico lá na frente.
    """
    problemas = []
    if not (getattr(settings, "SES_REMETENTE", "") or "").strip():
        problemas.append("SES_REMETENTE não definido no .env")
    if not destinatarios():
        problemas.append("RELATORIO_DESTINATARIOS não definido no .env")
    try:
        import boto3  # noqa: F401
    except ImportError:
        problemas.append("boto3 não instalado (pip install boto3)")
    return problemas


def enviar(assunto: str, html: str, texto: str, para: list[str] | None = None) -> str:
    """
    Envia e devolve o MessageId do SES.

    Levanta em caso de falha — aqui o erro SOBE, ao contrário da IA. Um
    relatório que não chega e não avisa é pior que um erro no log do cron:
    o silêncio seria lido como "está tudo funcionando".
    """
    problemas = verificar_configuracao()
    if problemas:
        raise EnvioNaoConfigurado("; ".join(problemas))

    import boto3

    para = para or destinatarios()
    cliente = boto3.client("sesv2", region_name=settings.AWS_REGION)
    resposta = cliente.send_email(
        FromEmailAddress=settings.SES_REMETENTE,
        Destination={"ToAddresses": para},
        Content={
            "Simple": {
                "Subject": {"Data": assunto, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": texto, "Charset": "UTF-8"},
                    "Html": {"Data": html, "Charset": "UTF-8"},
                },
            }
        },
    )
    message_id = resposta["MessageId"]
    log.info("email: enviado para %s (MessageId=%s)", ", ".join(para), message_id)
    return message_id
