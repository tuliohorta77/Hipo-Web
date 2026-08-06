"""
HIPO — Normalização de texto para as listas de domínio.

As listas (verticais, origens, concorrentes, motivos de desfecho) são criadas
livremente por qualquer usuário, direto do combobox. Sem normalização, o banco
acumularia "Metalúrgica", "metalurgica" e "Metalurgica " como três entradas
distintas.

O slug é a chave de deduplicação: coluna UNIQUE no banco, e um POST cujo slug
já existe devolve o registro existente em vez de 409.

Funções puras — testáveis sem banco.
"""
from __future__ import annotations

import re
import unicodedata

_NAO_ALFANUM = re.compile(r"[^a-z0-9]+")
_ESPACOS = re.compile(r"\s+")


def slugify(texto: str | None) -> str:
    """
    Minúsculas, sem acento, sem pontuação, palavras unidas por hífen.

    >>> slugify("  Metalúrgica   Pesada ")
    'metalurgica-pesada'
    >>> slugify("Construção Civil / Obras")
    'construcao-civil-obras'
    >>> slugify("")
    ''
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    slug = _NAO_ALFANUM.sub("-", sem_acento.lower())
    return slug.strip("-")


def limpar_nome(texto: str | None) -> str:
    """
    Versão de exibição: colapsa espaços repetidos e tira as pontas, mas
    preserva acentuação e caixa como o usuário digitou.

    >>> limpar_nome("  Metalúrgica   Pesada ")
    'Metalúrgica Pesada'
    """
    if not texto:
        return ""
    return _ESPACOS.sub(" ", texto).strip()
