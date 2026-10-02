"""
HIPO — UC: material de apoio da aula (PDF, imagem, documento) no S3.

Mesmo bucket, mesma credencial e mesmo acesso dos anexos de tarefa
(services/anexo.py). O que muda são as REGRAS: material de aula é
apostila, norma, planilha de exemplo — maior que um print, e pode ser
documento do Office. O prefixo `uc/` separa os dois mundos num
`aws s3 ls`.

A política IAM `hipo-anexos-s3` libera o bucket inteiro (não só
`tarefas/`), então o prefixo novo não pede mudança de permissão.
"""
from __future__ import annotations

from uuid import UUID

from services import anexo
from services.anexo import AnexoInvalido

TIPOS_ACEITOS: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

# 25 MB: uma NR inteira em PDF tem 1 MB; uma apresentação com fotos chega
# a 15. O limite é para o acidente (vídeo arrastado por engano — vídeo
# entra como LINK, nunca como arquivo).
LIMITE_MB = 25
LIMITE_BYTES = LIMITE_MB * 1024 * 1024
MAX_POR_AULA = 10


def validar_tipo(tipo_mime: str | None) -> str:
    tipo = (tipo_mime or "").split(";")[0].strip().lower()
    if tipo in TIPOS_ACEITOS:
        return TIPOS_ACEITOS[tipo]
    if tipo.startswith("video/"):
        raise AnexoInvalido(
            "Vídeo não sobe como arquivo. Publique no YouTube (não listado), "
            "Vimeo, Loom ou Google Drive e cole o link no campo de vídeo da aula."
        )
    aceitos = ", ".join(sorted(e.lstrip(".").upper() for e in set(TIPOS_ACEITOS.values())))
    raise AnexoInvalido(f"Tipo de arquivo não aceito. Aceitos: {aceitos}.")


def validar_tamanho(bytes_: int) -> None:
    if bytes_ <= 0:
        raise AnexoInvalido("Arquivo vazio.")
    if bytes_ > LIMITE_BYTES:
        raise AnexoInvalido(
            f"Arquivo de {bytes_ / (1024 * 1024):.1f} MB excede o limite de {LIMITE_MB} MB."
        )


def validar_quantidade(ja_existentes: int) -> None:
    if ja_existentes >= MAX_POR_AULA:
        raise AnexoInvalido(
            f"A aula já tem {MAX_POR_AULA} materiais, que é o limite. "
            "Remova um antes de enviar outro."
        )


def chave_do_objeto(aula_id: UUID | str, material_id: UUID | str, extensao: str) -> str:
    """Derivada só de ids: nome de arquivo na chave seria travessia de caminho."""
    return f"uc/aulas/{aula_id}/{material_id}{extensao}"


# Reaproveitados do anexo, sem cópia: higiene de nome e acesso ao S3.
nome_seguro = anexo.nome_seguro
problemas = anexo.problemas
subir = anexo.subir
url_temporaria = anexo.url_temporaria
remover = anexo.remover
URL_VALIDA_SEGUNDOS = anexo.URL_VALIDA_SEGUNDOS
