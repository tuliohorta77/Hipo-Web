"""
Testes do cálculo de indicadores PEX.
Testa as fórmulas de pontuação e os thresholds de cada indicador.
"""
import pytest
from services.pex_calc import (
    _pts_reunioes_ec_du,
    _pts_contadores_trabalhados,
    _pts_contadores_indicando,
    _pts_contadores_ativando,
    _pts_conversao_total,
    _pts_conversao_m0,
    _pts_conversao_inbound,
    _pts_demo_du,
    _pts_demos_outbound,
    _pts_sow,
    _pts_mapeamento,
    _pts_reuniao_inbound,
    _pts_integracao,
    _pts_early_churn,
    _pts_crescimento,
    _pts_utilizacao_desconto,
    _classificar_risco,
)


class TestPontuacaoReunioesEC:
    def test_abaixo_do_minimo(self):   assert _pts_reunioes_ec_du(3.0) == 0
    def test_faixa_intermediaria(self): assert _pts_reunioes_ec_du(3.5) == 1.5
    def test_meta_atingida(self):       assert _pts_reunioes_ec_du(4.0) == 3.0
    def test_acima_da_meta(self):       assert _pts_reunioes_ec_du(5.0) == 3.0


class TestPontuacaoContadoresTrabalhados:
    def test_abaixo_do_minimo(self):    assert _pts_contadores_trabalhados(0.70) == 0
    def test_faixa_intermediaria(self): assert _pts_contadores_trabalhados(0.80) == 1.0
    def test_meta_atingida(self):       assert _pts_contadores_trabalhados(0.90) == 2.0
    def test_exatamente_no_limite(self):assert _pts_contadores_trabalhados(0.72) == 1.0


class TestPontuacaoContadoresIndicando:
    def test_zero(self):               assert _pts_contadores_indicando(0.0) == 0
    def test_faixa_intermediaria(self):assert _pts_contadores_indicando(0.22) == 1.5
    def test_meta_atingida(self):      assert _pts_contadores_indicando(0.25) == 3.0
    def test_acima_da_meta(self):      assert _pts_contadores_indicando(0.50) == 3.0


class TestPontuacaoContadoresAtivando:
    def test_zero(self):               assert _pts_contadores_ativando(0.0) == 0
    def test_faixa_intermediaria(self):assert _pts_contadores_ativando(0.07) == 2.0
    def test_meta_atingida(self):      assert _pts_contadores_ativando(0.08) == 4.0


class TestPontuacaoConversaoTotal:
    def test_abaixo_do_minimo(self):    assert _pts_conversao_total(0.20) == 0
    def test_faixa_intermediaria(self): assert _pts_conversao_total(0.30) == 2.0
    def test_meta_atingida(self):       assert _pts_conversao_total(0.35) == 4.0
    def test_resultado_real_marco(self):
        # Março estava em 39,51% — deve pontuar 4pts
        assert _pts_conversao_total(0.3951) == 4.0


class TestPontuacaoConversaoM0:
    def test_zero(self):               assert _pts_conversao_m0(0.0) == 0
    def test_faixa_intermediaria(self):assert _pts_conversao_m0(0.17) == 1.5
    def test_meta_atingida(self):      assert _pts_conversao_m0(0.20) == 3.0


class TestPontuacaoEarlyChurn:
    def test_dentro_da_meta(self):     assert _pts_early_churn(0.05) == 3.0
    def test_exatamente_na_meta(self): assert _pts_early_churn(0.057) == 3.0
    def test_faixa_intermediaria(self):assert _pts_early_churn(0.065) == 1.5
    def test_acima_do_limite(self):    assert _pts_early_churn(0.08) == 0
    def test_resultado_real_marco(self):
        # Março estava em 11,2% — deve pontuar 0
        assert _pts_early_churn(0.112) == 0


class TestPontuacaoCrescimento40:
    def test_abaixo_do_minimo(self):    assert _pts_crescimento(0.20) == 0
    def test_faixa_intermediaria(self): assert _pts_crescimento(0.35) == 2.5
    def test_meta_atingida(self):       assert _pts_crescimento(0.40) == 5.0
    def test_resultado_real_marco(self):
        # Março estava em 28,39% — deve pontuar 0
        assert _pts_crescimento(0.2839) == 0


class TestPontuacaoUtilizacaoDesconto:
    def test_abaixo_do_limite(self):    assert _pts_utilizacao_desconto(0.10) == 2.0
    def test_exatamente_no_limite(self):assert _pts_utilizacao_desconto(0.15) == 2.0
    def test_faixa_intermediaria(self): assert _pts_utilizacao_desconto(0.17) == 1.0
    def test_acima_do_limite(self):     assert _pts_utilizacao_desconto(0.20) == 0
    def test_resultado_real_marco(self):
        # Março estava em 0,78% — deve pontuar 2pts
        assert _pts_utilizacao_desconto(0.0078) == 2.0


class TestClassificarRisco:
    def test_verde(self):    assert _classificar_risco(80) == "VERDE"
    def test_amarelo(self):  assert _classificar_risco(45) == "AMARELO"
    def test_laranja(self):  assert _classificar_risco(65) == "LARANJA"
    def test_vermelho(self): assert _classificar_risco(30) == "VERMELHO"
    def test_limiar_36(self):
        # 36,5 (resultado de março) deve ser AMARELO — acima do limiar de descredenciamento
        assert _classificar_risco(36.5) == "AMARELO"
    def test_limiar_descredenciamento(self):
        assert _classificar_risco(35.9) == "VERMELHO"