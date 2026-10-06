"""
HIPO — Identidade da instância (entrega 046).

O mesmo código atende mais de uma base: hipogestao.com.br (Controller MedSeg)
e mos.hipogestao.com.br (MOS). Cada uma tem banco, `.env` e serviço
próprios; o que muda no texto que cliente e equipe leem vem daqui:

  * `empresa_nome()`   -> convite do Google Calendar, nome do arquivo do RPeR
  * `empresa_sigla()`  -> rótulo ao lado do logo, título da aba, assunto do
                          fechamento diário
  * `modelo_proposta()`-> PPTX usado na proposta comercial

Leitura PREGUIÇOSA do `settings`, dentro de cada função, e não no import:
os módulos que chamam isto (agenda, rper_render, relatorio_render) têm testes
de regra pura que rodam sem `.env` no Windows. Um `from config import
settings` no topo derrubaria esses testes no import, por falta de
DATABASE_URL — que não tem nada a ver com o que eles testam.

Sem `.env` legível, vale o padrão: a base principal, exatamente como era
antes da 046.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

EMPRESA_PADRAO = "Controller MedSeg"

# api/services/instancia.py -> api/templates/proposta_modelo.pptx
MODELO_PROPOSTA_PADRAO = (
    Path(__file__).resolve().parent.parent / "templates" / "proposta_modelo.pptx"
)


def _settings():
    try:
        from config import settings
    except Exception:  # sem .env / sem DATABASE_URL: teste de regra pura
        return None
    return settings


def empresa_nome() -> str:
    s = _settings()
    nome = (getattr(s, "EMPRESA_NOME", "") or "").strip() if s else ""
    return nome or EMPRESA_PADRAO


def empresa_sigla() -> str:
    """Vazio na base principal; 'MOS' na instância da MOS."""
    s = _settings()
    return (getattr(s, "EMPRESA_SIGLA", "") or "").strip() if s else ""


def slug_arquivo(nome: str) -> str:
    """
    'Controller MedSeg' -> 'CONTROLLER_MEDSEG'.

    Nome de arquivo que vai para o Windows de quem baixa: sem acento, sem
    espaço, sem caractere que o Explorer recusa. Separadores repetidos viram
    um só e não sobram nas pontas.
    """
    sem_acento = (
        unicodedata.normalize("NFKD", nome or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^A-Za-z0-9]+", "_", sem_acento).strip("_").upper()
    return slug or "HIPO"


def prefixo_assunto() -> str:
    """'HIPO' na base principal; 'HIPO MOS' na instância da MOS."""
    sigla = empresa_sigla()
    return f"HIPO {sigla}" if sigla else "HIPO"


def modelo_proposta() -> Path:
    """
    Caminho do PPTX da proposta. `PROPOSTA_MODELO_ARQUIVO` no `.env` troca o
    modelo sem deploy (o arquivo fica fora de api/, que o rsync do CI
    sobrescreve); vazio = o modelo versionado.
    """
    s = _settings()
    custom = (getattr(s, "PROPOSTA_MODELO_ARQUIVO", "") or "").strip() if s else ""
    return Path(custom) if custom else MODELO_PROPOSTA_PADRAO
