"""
HIPO - Guarda contra numero inventado pela IA.

Funcoes puras, sem I/O e sem dependencia de config: da para testar sem banco,
sem AWS e sem chamar a Anthropic.

POR QUE EXISTE

`services/ia.py` ja pede ao modelo, na instrucao, que nao invente numero. Isso
e um pedido, nao uma garantia. Este modulo transforma o pedido em verificacao:
extrai todo numero escrito na narrativa e confere contra os numeros que
existem, de fato, nas metricas apuradas pelo Postgres.

E o unico ponto do fechamento em que um defeito produz saida PLAUSIVEL E
ERRADA em vez de erro. Se a IA escrever "queda de 30% no uso" e ninguem tiver
como rastrear esse 30 ate uma coluna, o relatorio inteiro passa a precisar de
conferencia - e relatorio que precisa ser conferido nao economiza tempo de
ninguem, que e exatamente o argumento do cabecalho do ia.py.

A REGRA E ESTRITA DE PROPOSITO

Percentual calculado, soma feita de cabeca e arredondamento espontaneo sao
todos rejeitados. Nao porque estariam necessariamente errados, mas porque nao
da para saber. Falso positivo custa a narrativa daquele dia - o e-mail sai com
todos os numeros, que e o comportamento que o ia.py ja adota quando a API
falha. Falso negativo custaria a confianca em todos os outros numeros,
inclusive nos certos.

Se `narrativa descartada` aparecer com frequencia no journal, o ajuste e na
INSTRUCAO do ia.py, nao aqui.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Casa um numero e o que vier grudado nele: '1.234,50', '12', '30'. A barra
# nao entra, entao '17/08/2026' chega como tres tokens - o que e desejado,
# porque dia, mes e ano sao validados separadamente.
_TOKEN = re.compile(r"\d[\d.,]*")


def canonizar(bruto: str) -> str:
    """
    Normaliza um token numerico para comparacao, entendendo notacao pt-BR.

    '.' e separador de milhar e ',' e decimal. Sem virgula, um ponto seguido de
    exatamente tres digitos e milhar ('1.234'); qualquer outra coisa e decimal
    ('1.5'). Sem isso, a IA escrevendo 'R$ 1.234' seria acusada de inventar um
    numero que esta na metrica como 1234.
    """
    t = bruto.strip().strip(".,")
    if not t:
        return bruto
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        partes = t.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            t = "".join(partes)
    try:
        d = Decimal(t)
    except InvalidOperation:
        return t
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def _coletar(valor: Any, acumulador: set[str]) -> None:
    if valor is None or isinstance(valor, bool):
        return
    if isinstance(valor, (int, float, Decimal)):
        acumulador.add(canonizar(str(valor)))
        return
    if isinstance(valor, datetime):
        _coletar(valor.date(), acumulador)
        return
    if isinstance(valor, date):
        acumulador.update({
            str(valor.day), f"{valor.day:02d}",
            str(valor.month), f"{valor.month:02d}",
            str(valor.year),
        })
        return
    if isinstance(valor, str):
        # Numero dentro de texto que NOS montamos veio do banco: e fato.
        # 'OPP-2026-00001' e 'Aline Martins (3 tarefas)' liberam 2026, 1 e 3.
        for achado in _TOKEN.findall(valor):
            acumulador.add(canonizar(achado))
        return
    if isinstance(valor, dict):
        for chave, v in valor.items():
            # A CHAVE tambem conta: metricas costumam ter nomes como
            # 'erros_5xx' ou 'p95_ms', e a IA cita esses rotulos.
            _coletar(chave, acumulador)
            _coletar(v, acumulador)
        return
    if isinstance(valor, (list, tuple, set)):
        for v in valor:
            _coletar(v, acumulador)


def numeros_permitidos(metricas: Any) -> set[str]:
    """Conjunto canonico de tudo que pode legitimamente aparecer na narrativa."""
    achados: set[str] = set()
    _coletar(metricas, achados)
    achados.discard("")
    return achados


def contexto(texto: str, token: str, janela: int = 70) -> str:
    """
    O trecho da narrativa em volta da primeira ocorrencia de `token`.

    POR QUE ISTO PRECISA EXISTIR

    O cabecalho deste modulo manda ajustar a INSTRUCAO quando a narrativa for
    descartada com frequencia. Sem ver a FRASE, isso e impossivel: o log dizia
    apenas `numeros fora da telemetria (30)`, e '30' pode ser '30%', 'ha 30
    dias', 'R$ 30' ou 'temperatura 30' -- cada um pede um ajuste diferente, e
    um deles ('temperatura 30') seria falso positivo da guarda, nao erro do
    modelo.

    A narrativa descartada e jogada fora; se ela nao deixar rastro, o defeito
    fica invisivel exatamente quando esta acontecendo.

    >>> contexto("houve queda de 30% no uso do sistema", "30", janela=10)
    '...queda de 30% no uso d...'
    >>> contexto("nada aqui", "99")
    ''
    """
    if not texto or not token:
        return ""
    i = texto.find(token)
    if i < 0:
        return ""
    ini = max(0, i - janela)
    fim = min(len(texto), i + len(token) + janela)
    trecho = " ".join(texto[ini:fim].split())
    return ("..." if ini > 0 else "") + trecho + ("..." if fim < len(texto) else "")


def numeros_invalidos(texto: str, permitidos: set[str]) -> list[str]:
    """
    Numeros escritos no texto que nao existem nas metricas.

    Devolve os tokens como foram escritos, na ordem de aparicao e sem repetir,
    para o log dizer exatamente o que foi inventado.
    """
    fora: list[str] = []
    vistos: set[str] = set()
    for achado in _TOKEN.findall(texto or ""):
        canon = canonizar(achado)
        if canon in permitidos or canon in vistos:
            continue
        vistos.add(canon)
        fora.append(achado)
    return fora
