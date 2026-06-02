"""Calculo de dias uteis e progresso do mes.

Este servico e a base do calculo de "meta esperada hoje" no painel gerencial.
A formula final (que vai morar no router em outra etapa):

    meta_esperada_hoje = meta_mensal * (dia_util_atual / total_dias_uteis_mes)

Aqui ficam apenas as funcoes auxiliares, sem dependencia de banco. Os
dias-nao-uteis sao injetados via parametro `dias_nao_uteis: Iterable[date]` para
que os testes nao precisem de fixtures de DB.

Tambem moram aqui:
  - `calcular_pascoa(ano)`: algoritmo de Gauss anonimo (necessario para seed
    dos feriados moveis brasileiros).
  - `feriados_nacionais_br(ano)`: lista os feriados nacionais brasileiros do
    ano (fixos + moveis baseados na Pascoa).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable


def calcular_pascoa(ano: int) -> date:
    """Domingo de Pascoa no ano, pelo algoritmo de Gauss anonimo."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mes = (h + L - 7 * m + 114) // 31
    dia = ((h + L - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais_br(ano: int) -> list[tuple[date, str]]:
    """Lista (data, motivo) dos feriados nacionais brasileiros do ano.

    Inclui fixos (Confraternizacao, Tiradentes, Trabalho, Independencia,
    N. Sra. Aparecida, Finados, Proclamacao, Natal) e moveis baseados na
    Pascoa (Carnaval, Sexta-feira Santa, Corpus Christi).

    Pontos facultativos (cinzas, vespera de natal, servidor publico) NAO
    sao incluidos: a gestao decide caso a caso via tabela `dia_nao_util`.
    """
    pascoa = calcular_pascoa(ano)
    return [
        (date(ano, 1, 1), "Confraternizacao Universal"),
        (pascoa - timedelta(days=48), "Segunda-feira de Carnaval"),
        (pascoa - timedelta(days=47), "Terca-feira de Carnaval"),
        (pascoa - timedelta(days=2), "Sexta-feira Santa"),
        (date(ano, 4, 21), "Tiradentes"),
        (date(ano, 5, 1), "Dia do Trabalho"),
        (pascoa + timedelta(days=60), "Corpus Christi"),
        (date(ano, 9, 7), "Independencia do Brasil"),
        (date(ano, 10, 12), "Nossa Senhora Aparecida"),
        (date(ano, 11, 2), "Finados"),
        (date(ano, 11, 15), "Proclamacao da Republica"),
        (date(ano, 12, 25), "Natal"),
    ]


def dias_uteis_no_mes(
    mes: date,
    dias_nao_uteis: Iterable[date] = (),
) -> list[date]:
    """Lista os dias uteis de um mes em ordem cronologica.

    Considera dias uteis = dias da semana que NAO sao sabado/domingo E que
    NAO estao em `dias_nao_uteis`.

    Args:
        mes: Qualquer data dentro do mes (sera normalizada para o dia 1).
        dias_nao_uteis: Iterable de datas que NAO contam. A gestao da unidade
            edita essa lista (feriados nacionais, estaduais, municipais,
            pontos facultativos, dias que a empresa folgou, etc).

    Returns:
        Lista de `date` representando os dias uteis no mes.
    """
    primeiro_dia = mes.replace(day=1)
    ultimo_dia = primeiro_dia.replace(
        day=monthrange(primeiro_dia.year, primeiro_dia.month)[1]
    )
    nao_uteis_set = set(dias_nao_uteis)

    uteis: list[date] = []
    dia = primeiro_dia
    while dia <= ultimo_dia:
        # weekday(): segunda=0, sabado=5, domingo=6
        if dia.weekday() < 5 and dia not in nao_uteis_set:
            uteis.append(dia)
        dia += timedelta(days=1)

    return uteis


def dia_util_atual_no_mes(
    mes: date,
    dias_nao_uteis: Iterable[date] = (),
    hoje: date | None = None,
) -> int:
    """Posicao 1-based de hoje na lista de dias uteis do mes.

    Comportamento por regiao do calendario:
      - Hoje antes do primeiro dia util do mes: retorna 0.
      - Hoje apos o ultimo dia do mes: retorna o total de dias uteis (mes ja
        passou inteiro).
      - Hoje dentro do mes mas em dia NAO util (sabado, domingo, feriado):
        retorna a posicao do ultimo dia util ja transcorrido. Isso significa
        que durante um sabado/feriado o painel mostra o ritmo da sexta/vespera.
      - Hoje em dia util: retorna a posicao desse dia, contando o proprio dia.

    Args:
        mes: Qualquer data dentro do mes de referencia.
        dias_nao_uteis: Iterable de datas nao-uteis.
        hoje: Data de "hoje" (parametrizavel para testes). Default = date.today().

    Returns:
        Inteiro >= 0.
    """
    if hoje is None:
        hoje = date.today()

    uteis = dias_uteis_no_mes(mes, dias_nao_uteis)
    if not uteis:
        return 0

    primeiro_dia_mes = uteis[0].replace(day=1)
    ultimo_dia_mes = primeiro_dia_mes.replace(
        day=monthrange(primeiro_dia_mes.year, primeiro_dia_mes.month)[1]
    )

    if hoje < primeiro_dia_mes:
        return 0
    if hoje > ultimo_dia_mes:
        return len(uteis)

    contagem = 0
    for d in uteis:
        if d <= hoje:
            contagem += 1
        else:
            break
    return contagem


def progresso_do_mes(
    mes: date,
    dias_nao_uteis: Iterable[date] = (),
    hoje: date | None = None,
) -> tuple[int, int, float]:
    """Retorna (dia_util_atual, total_dias_uteis_mes, fracao_decorrida).

    A fracao e um valor entre 0.0 e 1.0 (inclusive ambos os extremos) que
    representa quanto do mes em termos de dias uteis ja passou. E exatamente
    o multiplicador da meta esperada hoje:

        meta_esperada_hoje = meta_mensal * fracao_decorrida

    Se nao houver dia util no mes (improvavel mas possivel — ex.: dezembro
    com muitos feriados consecutivos), retorna (0, 0, 0.0).
    """
    uteis = dias_uteis_no_mes(mes, dias_nao_uteis)
    total = len(uteis)
    atual = dia_util_atual_no_mes(mes, dias_nao_uteis, hoje)
    fracao = (atual / total) if total > 0 else 0.0
    return atual, total, fracao
