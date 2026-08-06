"""
HIPO — Normalização e validação de CNPJ.

Funções puras, sem banco e sem I/O: rodam no pytest local do Windows sem
Postgres. O banco guarda o CNPJ como CHAR(14) só com dígitos; a formatação
com pontuação existe apenas para exibição.
"""
from __future__ import annotations

import re

_SO_DIGITOS = re.compile(r"\D")

# CNPJs de dígitos repetidos (00000000000000, 11111111111111, ...) passam no
# cálculo do dígito verificador mas não existem. São rejeitados na mão.
_REPETIDOS = {str(d) * 14 for d in range(10)}

_PESOS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def normalizar(cnpj: str | None) -> str:
    """
    Remove tudo que não é dígito. Não valida.

    >>> normalizar("12.345.678/0001-95")
    '12345678000195'
    >>> normalizar(None)
    ''
    """
    if not cnpj:
        return ""
    return _SO_DIGITOS.sub("", cnpj)


def _digito(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def valido(cnpj: str | None) -> bool:
    """
    True se o CNPJ for válido: 14 dígitos, não repetidos, DV correto.

    Aceita entrada formatada ou não — normaliza antes de checar.

    >>> valido("11.222.333/0001-81")
    True
    >>> valido("11222333000182")
    False
    >>> valido("00000000000000")
    False
    """
    num = normalizar(cnpj)
    if len(num) != 14 or num in _REPETIDOS:
        return False

    dv1 = _digito(num[:12], _PESOS_1)
    if num[12] != dv1:
        return False

    dv2 = _digito(num[:13], _PESOS_2)
    return num[13] == dv2


def formatar(cnpj: str | None) -> str:
    """
    Devolve o CNPJ pontuado para exibição. Entrada inválida volta como veio
    (normalizada) — formatar não é lugar de levantar erro.

    >>> formatar("11222333000181")
    '11.222.333/0001-81'
    """
    num = normalizar(cnpj)
    if len(num) != 14:
        return num
    return f"{num[:2]}.{num[2:5]}.{num[5:8]}/{num[8:12]}-{num[12:]}"
