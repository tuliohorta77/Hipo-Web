"""Testes do service de calculo de dias uteis.

Cobre todas as funcoes de `api/services/dias_uteis.py`:
  - calcular_pascoa
  - feriados_nacionais_br
  - dias_uteis_no_mes
  - dia_util_atual_no_mes
  - progresso_do_mes

Estes testes sao 100% logica pura — nao tocam o banco. Rodam local no
Windows sem Postgres instalado.
"""

from __future__ import annotations

from datetime import date

import pytest

from services.dias_uteis import (
    calcular_pascoa,
    dia_util_atual_no_mes,
    dias_uteis_no_mes,
    feriados_nacionais_br,
    progresso_do_mes,
)


class TestCalcularPascoa:
    """Algoritmo de Gauss para Pascoa em datas conhecidas."""

    @pytest.mark.parametrize(
        "ano, esperado",
        [
            (2024, date(2024, 3, 31)),
            (2025, date(2025, 4, 20)),
            (2026, date(2026, 4, 5)),
            (2027, date(2027, 3, 28)),
            (2028, date(2028, 4, 16)),
            (2029, date(2029, 4, 1)),
            (2030, date(2030, 4, 21)),
        ],
    )
    def test_pascoa_em_anos_conhecidos(self, ano, esperado):
        assert calcular_pascoa(ano) == esperado


class TestFeriadosNacionaisBr:
    def test_2026_contem_doze_feriados(self):
        assert len(feriados_nacionais_br(2026)) == 12

    def test_2026_contem_natal_e_confraternizacao(self):
        feriados = dict(feriados_nacionais_br(2026))
        assert date(2026, 12, 25) in feriados
        assert date(2026, 1, 1) in feriados

    def test_2026_inclui_carnaval_baseado_em_pascoa(self):
        # Pascoa 2026 = 5/4. Carnaval terca = 5/4 - 47 = 17/2.
        feriados = dict(feriados_nacionais_br(2026))
        assert date(2026, 2, 17) in feriados
        assert "Carnaval" in feriados[date(2026, 2, 17)]

    def test_2026_inclui_corpus_christi(self):
        # Pascoa 2026 = 5/4. Corpus Christi = 5/4 + 60 = 4/6.
        feriados = dict(feriados_nacionais_br(2026))
        assert date(2026, 6, 4) in feriados
        assert "Corpus" in feriados[date(2026, 6, 4)]

    def test_motivos_sao_strings_nao_vazias(self):
        for _, motivo in feriados_nacionais_br(2026):
            assert isinstance(motivo, str)
            assert len(motivo) > 0


class TestDiasUteisNoMes:
    def test_mes_sem_feriados_so_descarta_sabados_e_domingos(self):
        # Marco de 2026: 31 dias, sem nenhum feriado nacional.
        uteis = dias_uteis_no_mes(date(2026, 3, 15))
        # Marco 2026 comeca num domingo. 1=dom, 2=seg, 7=sab, 8=dom, ...
        # Dias uteis: 2,3,4,5,6, 9,10,11,12,13, 16,17,18,19,20, 23,24,25,26,27, 30,31
        assert len(uteis) == 22
        assert all(d.weekday() < 5 for d in uteis)

    def test_mes_com_feriado_no_meio_da_semana(self):
        # Setembro de 2026: dia 7 (segunda) = Independencia.
        feriados_set = [date(2026, 9, 7)]
        uteis = dias_uteis_no_mes(date(2026, 9, 1), feriados_set)
        # Setembro 2026 tem 30 dias. Sem o feriado seriam 22 dias uteis.
        assert len(uteis) == 21
        assert date(2026, 9, 7) not in uteis

    def test_resultado_em_ordem_cronologica(self):
        uteis = dias_uteis_no_mes(date(2026, 6, 1))
        for i in range(len(uteis) - 1):
            assert uteis[i] < uteis[i + 1]

    def test_normaliza_para_primeiro_dia_do_mes(self):
        # Passa data no meio do mes: deve normalizar e contar o mes todo.
        uteis_meio = dias_uteis_no_mes(date(2026, 6, 15))
        uteis_inicio = dias_uteis_no_mes(date(2026, 6, 1))
        assert uteis_meio == uteis_inicio

    def test_aceita_iterable_qualquer_para_nao_uteis(self):
        # Passa um gerador ao inves de lista.
        feriados_gen = (date(2026, 9, 7),)
        uteis = dias_uteis_no_mes(date(2026, 9, 1), feriados_gen)
        assert date(2026, 9, 7) not in uteis


class TestDiaUtilAtual:
    """Posicao do dia atual no mes."""

    def test_meio_de_mes_em_dia_util(self):
        # Junho 2026, dia 15 (segunda). Sem feriados.
        # Dias uteis ate 15/6: 1,2,3,4,5, 8,9,10,11,12, 15 = 11
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 6, 15))
        assert atual == 11

    def test_primeiro_dia_util_do_mes(self):
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 6, 1))
        assert atual == 1

    def test_ultimo_dia_do_mes(self):
        # 30 de junho de 2026 e uma terca. Junho 2026 tem 22 dias uteis.
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 6, 30))
        assert atual == 22

    def test_em_um_sabado_retorna_posicao_da_sexta_anterior(self):
        # 13/6/2026 e sabado. Sexta anterior = 12/6 que e a 10a util de junho.
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 6, 13))
        assert atual == 10

    def test_em_um_domingo_idem_sabado(self):
        # 14/6/2026 domingo. Mesmo resultado que sabado: 10 dias uteis ate la.
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 6, 14))
        assert atual == 10

    def test_em_um_feriado_retorna_ultimo_util_anterior(self):
        # 7/9/2026 (segunda) e Independencia. Util anterior: 4/9 (sexta).
        # Setembro 2026 ate 4/9: 1, 2, 3, 4 = 4 dias uteis.
        feriados = [date(2026, 9, 7)]
        atual = dia_util_atual_no_mes(date(2026, 9, 1), feriados, date(2026, 9, 7))
        assert atual == 4

    def test_antes_do_mes_retorna_zero(self):
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 5, 31))
        assert atual == 0

    def test_depois_do_mes_retorna_total(self):
        # Em 1/7/2026 olhando o mes de junho: ja passou inteiro.
        atual = dia_util_atual_no_mes(date(2026, 6, 1), [], date(2026, 7, 1))
        assert atual == 22

    def test_hoje_default_usa_date_today(self):
        # So verifica que nao explode quando hoje=None.
        resultado = dia_util_atual_no_mes(date(2026, 6, 1), [])
        assert isinstance(resultado, int)
        assert resultado >= 0


class TestProgressoDoMes:
    def test_meio_do_mes_retorna_fracao_correta(self):
        # 15/6/2026: 11 dias uteis ja passaram de 22 do mes = 50%.
        atual, total, fracao = progresso_do_mes(
            date(2026, 6, 1), [], date(2026, 6, 15)
        )
        assert atual == 11
        assert total == 22
        assert fracao == 0.5

    def test_inicio_do_mes_fracao_pequena(self):
        atual, total, fracao = progresso_do_mes(
            date(2026, 6, 1), [], date(2026, 6, 1)
        )
        assert atual == 1
        assert total == 22
        assert fracao == pytest.approx(1 / 22)

    def test_fim_do_mes_fracao_um(self):
        atual, total, fracao = progresso_do_mes(
            date(2026, 6, 1), [], date(2026, 6, 30)
        )
        assert atual == 22
        assert total == 22
        assert fracao == 1.0

    def test_antes_do_mes_fracao_zero(self):
        atual, total, fracao = progresso_do_mes(
            date(2026, 6, 1), [], date(2026, 5, 1)
        )
        assert atual == 0
        assert total == 22
        assert fracao == 0.0

    def test_com_feriados_diminui_total_e_ajusta_fracao(self):
        # Setembro 2026 com Independencia (7/9) descontada: 21 dias uteis.
        feriados = [date(2026, 9, 7)]
        # No dia 4/9 (sexta), 4 uteis ja passaram, fracao = 4/21.
        atual, total, fracao = progresso_do_mes(
            date(2026, 9, 1), feriados, date(2026, 9, 4)
        )
        assert atual == 4
        assert total == 21
        assert fracao == pytest.approx(4 / 21)


class TestExemploCalculoMetaEsperada:
    """Demonstra como o calculo de meta esperada vai usar progresso_do_mes.

    Esses testes nao testam codigo novo — sao 'documentacao executavel' do
    comportamento esperado para uso a jusante (no endpoint /painel/kpis que
    vira em uma proxima etapa).
    """

    def test_kpi_cumulativo_meio_do_mes(self):
        # Meta mensal de LEAD = 200. Estamos no dia util 11 de 22 = 50%.
        # Meta esperada hoje = 200 * 0.5 = 100. Resultado atual = 116.
        # %_no_ritmo = 116 / 100 = 116% (a frente).
        _, _, fracao = progresso_do_mes(date(2026, 6, 1), [], date(2026, 6, 15))
        meta_mensal = 200
        meta_esperada = meta_mensal * fracao
        resultado = 116
        pct_no_ritmo = resultado / meta_esperada
        assert meta_esperada == 100
        assert pct_no_ritmo == pytest.approx(1.16)

    def test_kpi_taxa_invertida_noshow(self):
        # NOSHOW: meta = 20% (limite maximo). Resultado atual = 18%.
        # Polaridade invertida: queremos resultado < meta.
        # %_no_ritmo invertido = meta / resultado = 20 / 18 = 111% (a frente).
        meta = 20
        resultado = 18
        pct_no_ritmo_invertido = meta / resultado
        assert pct_no_ritmo_invertido == pytest.approx(20 / 18)
        assert pct_no_ritmo_invertido > 1.0  # estamos melhor que a meta

    def test_kpi_sem_meta_eh_indeterminado(self):
        # Meta 0 ou None nao da pra calcular % atingido.
        # O codigo do endpoint vai detectar isso e mostrar fantasma.
        # Aqui so demonstramos que dividir por zero nao e opcao.
        meta = 0
        resultado = 6400
        # Nao tentar: pct = resultado / meta  -> ZeroDivisionError
        # O tratamento sera: se meta == 0 -> status = "sem_meta".
        assert meta == 0
        assert resultado > 0  # operacao acontece, so falta meta
