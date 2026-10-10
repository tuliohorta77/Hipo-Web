"""
HIPO — Acesso à AWS das ligações (entrega 056): S3 e AWS Transcribe.

Funções pequenas, as ÚNICAS que os testes precisam dublar. As regras
moram em services/ligacao.py; a orquestração em services/coleta_ligacao.py.

O `import boto3` mora DENTRO das funções, pelo mesmo motivo de
services/anexo.py: faltando a lib, cai só a feature, e não a API inteira.

CREDENCIAL: a mesma cadeia padrão do SDK do anexo e do SES — em produção,
a role da instância. Não há chave no .env e não deve haver. A role precisa,
além do que já tem para os anexos:

    transcribe:StartTranscriptionJob
    transcribe:GetTranscriptionJob
    transcribe:DeleteTranscriptionJob

O Transcribe lê o áudio do bucket COM A CREDENCIAL DE QUEM PEDIU o job
(a role), que já tem s3:GetObject no bucket dos anexos. A saída vai para o
bucket gerenciado pelo próprio Transcribe (sem OutputBucketName): o JSON
volta por uma URL assinada, o HIPO copia o texto para o banco e apaga o
job. Nada fica morando na AWS além do áudio, que tem retenção própria.

UPLOAD DIRETO PARA O S3. O gravador não manda o áudio para a API: pede uma
URL assinada de PUT e sobe direto no bucket. Uma ligação de 40 minutos dá
~40 MB, e passar isso pelo nginx (limite de 50 MB) e pelo uvicorn só
trocaria um PUT para o S3 por dois saltos e um teto.
"""
from __future__ import annotations

import httpx

from config import settings

# A URL de upload vale uma hora: o agente pede e sobe em seguida, mas a
# internet de quem está em campo pode ser lenta.
URL_UPLOAD_SEGUNDOS = 3600
# A de leitura vale cinco minutos, como a dos anexos: é um segredo portátil.
URL_LEITURA_SEGUNDOS = 300

IDIOMA = "pt-BR"


class AwsIndisponivel(RuntimeError):
    """Configuração faltando (bucket, boto3). Mensagem pronta para a tela."""


def problemas() -> list[str]:
    """O que impede a gravação de funcionar, em linguagem de quem resolve."""
    achados: list[str] = []
    if not settings.S3_BUCKET_ANEXOS:
        achados.append(
            "S3_BUCKET_ANEXOS não configurado no .env "
            "(é o mesmo bucket dos anexos; reinicie o serviço depois)"
        )
    try:
        import boto3  # noqa: F401
    except ImportError:
        achados.append("boto3 não instalado (pip install boto3)")
    return achados


def disponivel() -> bool:
    return not problemas()


def _s3():
    import boto3
    from botocore.config import Config

    # Endpoint REGIONAL e assinatura v4: a URL assinada vai para fora (o
    # agente na máquina do vendedor). Com o endpoint global, o S3 pode
    # responder 307 para a região do bucket, e um PUT assinado não segue
    # redirecionamento.
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url=f"https://s3.{settings.AWS_REGION}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _transcribe():
    import boto3

    return boto3.client("transcribe", region_name=settings.AWS_REGION)


# ── S3 ───────────────────────────────────────────────────────────────


def url_upload(chave: str, tipo_mime: str) -> str:
    """URL assinada de PUT. O agente precisa mandar o MESMO Content-Type."""
    return _s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.S3_BUCKET_ANEXOS, "Key": chave, "ContentType": tipo_mime},
        ExpiresIn=URL_UPLOAD_SEGUNDOS,
    )


def tamanho_no_s3(chave: str) -> int | None:
    """Bytes do objeto, ou None se ele não existe."""
    from botocore.exceptions import ClientError

    try:
        r = _s3().head_object(Bucket=settings.S3_BUCKET_ANEXOS, Key=chave)
    except ClientError as e:
        codigo = str((e.response.get("Error") or {}).get("Code", ""))
        if codigo in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return int(r.get("ContentLength") or 0)


def url_leitura(chave: str) -> str:
    return _s3().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.S3_BUCKET_ANEXOS,
            "Key": chave,
            "ResponseContentType": "audio/flac",
        },
        ExpiresIn=URL_LEITURA_SEGUNDOS,
    )


def remover(chave: str) -> None:
    _s3().delete_object(Bucket=settings.S3_BUCKET_ANEXOS, Key=chave)


# ── Transcribe ───────────────────────────────────────────────────────


def iniciar_transcricao(nome_job: str, chave: str, formato: str = "flac") -> None:
    """
    Começa o job. Dois canais com ChannelIdentification: cada lado da
    ligação é transcrito separado, e "quem falou" sai exato.
    """
    _transcribe().start_transcription_job(
        TranscriptionJobName=nome_job,
        LanguageCode=IDIOMA,
        MediaFormat=formato,
        Media={"MediaFileUri": f"s3://{settings.S3_BUCKET_ANEXOS}/{chave}"},
        Settings={"ChannelIdentification": True},
    )


def estado_transcricao(nome_job: str) -> tuple[str, str | None, str | None]:
    """
    (estado, url do JSON, motivo da falha).

    estado: QUEUED | IN_PROGRESS | COMPLETED | FAILED | NOT_FOUND
    """
    from botocore.exceptions import ClientError

    try:
        r = _transcribe().get_transcription_job(TranscriptionJobName=nome_job)
    except ClientError as e:
        codigo = str((e.response.get("Error") or {}).get("Code", ""))
        if codigo in ("NotFoundException", "BadRequestException"):
            return "NOT_FOUND", None, "O job de transcrição não existe mais na AWS."
        raise
    job = r.get("TranscriptionJob") or {}
    estado = job.get("TranscriptionJobStatus") or "IN_PROGRESS"
    url = (job.get("Transcript") or {}).get("TranscriptFileUri")
    return estado, url, job.get("FailureReason")


def baixar_transcricao(url: str) -> dict:
    """O JSON do resultado, pela URL assinada que o Transcribe devolveu."""
    with httpx.Client(timeout=60.0) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def apagar_job(nome_job: str) -> None:
    """Apaga o job (e o JSON que o Transcribe guarda). Falha não importa."""
    try:
        _transcribe().delete_transcription_job(TranscriptionJobName=nome_job)
    except Exception:  # noqa: BLE001 - limpeza; o texto já está no banco
        pass
