"""
Testes das funções de pontuação do PEX (manual v8.01/2026).
Valida cada faixa de cada indicador individualmente.
"""
import pytest
from services.pex_calc import (
    _pts_nmrr, _pts_sow, _pts_mapeamento_carteira,
    _pts_early_churn, _pts_utilizacao_desconto, _pts_crescimento_40,
    _pts_reunioes_ec_du, _pts_contadores_trabalhados, _pts_contadores_indicando,
    _pts_contadores_ativando, _pts_demos_outbound, _pts_reuniao_contador_inbound,
    _pts_conversao_inbound, _pts_conversao_total, _pts_conversao_m0,
    _pts_demo_du, _pts_uso_correto_cromie, _pts_big3,
    _classificar, _classificar_oficial, _safe_pct, _mes_bounds,
)


# ════════════════════════════════════════════════════════════════════════
# Pilar Resultado
# ════════════════════════════════════════════════════════════════════════

class TestNMRR:
    """Manual: 0-79,99% → 0pts | 80-84,99% → 5pts | 85-100% proporcional capado em 10pts"""
    def test_abaixo_80_zera(self):
        assert _pts_nmrr(0) == 0
        assert _pts_nmrr(50) == 0
        assert _pts_nmrr(79.99) == 0

    def test_entre_80_e_85_da_5(self):
        assert _pts_nmrr(80) == 5.0
        assert _pts_nmrr(82.5) == 5.0
        assert _pts_nmrr(84.99) == 5.0

    def test_entre_85_e_100_proporcional(self):
        assert _pts_nmrr(85) == 8.5
        assert _pts_nmrr(90) == 9.0
        assert _pts_nmrr(95) == 9.5
        assert _pts_nmrr(100) == 10.0

    def test_acima_de_100_capa_em_10(self):
        assert _pts_nmrr(105) == 10.0
        assert _pts_nmrr(150) == 10.0
        assert _pts_nmrr(999) == 10.0


class TestSoW:
    """Manual: 0-3,99% → 0 | 4-4,99% → 1,5 | 5-100% → 3"""
    def test_faixas(self):
        assert _pts_sow(0) == 0
        assert _pts_sow(3.99) == 0
        assert _pts_sow(4) == 1.5
        assert _pts_sow(4.99) == 1.5
        assert _pts_sow(5) == 3.0
        assert _pts_sow(50) == 3.0


class TestMapeamento:
    """Manual: 0-47,99% → 0 | 48-59,99% → 1 | 60-100% → 2"""
    def test_faixas(self):
        assert _pts_mapeamento_carteira(0) == 0
        assert _pts_mapeamento_carteira(47.99) == 0
        assert _pts_mapeamento_carteira(48) == 1.0
        assert _pts_mapeamento_carteira(60) == 2.0


class TestEarlyChurn:
    """Manual (lower better): 0-5,7% → 3 | 5,8-7,1% → 1,5 | 7,2+ → 0"""
    def test_zero_e_max_pontuacao(self):
        # 0% de churn = melhor caso, 3 pts
        assert _pts_early_churn(0) == 3.0

    def test_faixas(self):
        assert _pts_early_churn(5.7) == 3.0
        assert _pts_early_churn(5.71) == 1.5
        assert _pts_early_churn(7.1) == 1.5
        assert _pts_early_churn(7.11) == 0.0
        assert _pts_early_churn(50) == 0.0


class TestUtilizacaoDesconto:
    """Manual (lower better): 0-15% → 2 | 15,1-19% → 1 | 19,1+ → 0"""
    def test_faixas(self):
        assert _pts_utilizacao_desconto(0) == 2.0
        assert _pts_utilizacao_desconto(15) == 2.0
        assert _pts_utilizacao_desconto(15.01) == 1.0
        assert _pts_utilizacao_desconto(19) == 1.0
        assert _pts_utilizacao_desconto(19.01) == 0.0


class TestCrescimento40:
    """Manual: 0-31,99% → 0 | 32-39,99% → 2,5 | 40+ → 5"""
    def test_faixas(self):
        assert _pts_crescimento_40(0) == 0
        assert _pts_crescimento_40(32) == 2.5
        assert _pts_crescimento_40(40) == 5.0
        assert _pts_crescimento_40(50) == 5.0


class TestReunioesECDU:
    """Manual: <3,2 → 0 | 3,2-3,99 → 1,5 | 4+ → 3 (valor absoluto)"""
    def test_faixas(self):
        assert _pts_reunioes_ec_du(0) == 0
        assert _pts_reunioes_ec_du(3.1) == 0
        assert _pts_reunioes_ec_du(3.2) == 1.5
        assert _pts_reunioes_ec_du(3.99) == 1.5
        assert _pts_reunioes_ec_du(4) == 3.0
        assert _pts_reunioes_ec_du(10) == 3.0


class TestContadoresTrabalhados:
    """Manual: 0-71,99% → 0 | 72-89,99% → 1 | 90+ → 2"""
    def test_faixas(self):
        assert _pts_contadores_trabalhados(0) == 0
        assert _pts_contadores_trabalhados(72) == 1.0
        assert _pts_contadores_trabalhados(90) == 2.0

    def test_overflow_extreme_nao_quebra(self):
        # Antes da correção, valores como 54500% causavam pontuação errada
        # Agora devem cair na faixa de 90+ = 2 pts (ainda assim 2 pts é o cap)
        assert _pts_contadores_trabalhados(54500) == 2.0


class TestContadoresIndicando:
    """Manual: 0-19,99% → 0 | 20-24,99% → 1,5 | 25+ → 3"""
    def test_faixas(self):
        assert _pts_contadores_indicando(0) == 0
        assert _pts_contadores_indicando(20) == 1.5
        assert _pts_contadores_indicando(25) == 3.0


class TestContadoresAtivando:
    """Manual: 0-6,3% → 0 | 6,4-7,99% → 2 | 8+ → 4"""
    def test_faixas(self):
        assert _pts_contadores_ativando(0) == 0
        assert _pts_contadores_ativando(6.3) == 0
        assert _pts_contadores_ativando(6.4) == 2.0
        assert _pts_contadores_ativando(8) == 4.0


class TestDemosOutbound:
    """Manual: 0-79,99% → 0 | 80-99,99% → 1,5 | 100% → 3"""
    def test_faixas(self):
        assert _pts_demos_outbound(0) == 0
        assert _pts_demos_outbound(80) == 1.5
        assert _pts_demos_outbound(99.99) == 1.5
        assert _pts_demos_outbound(100) == 3.0


class TestReuniaoContadorInbound:
    """Manual: 0-63,99% → 0 | 64-79,99% → 2 | 80+ → 4"""
    def test_faixas(self):
        assert _pts_reuniao_contador_inbound(0) == 0
        assert _pts_reuniao_contador_inbound(64) == 2.0
        assert _pts_reuniao_contador_inbound(80) == 4.0


class TestConversaoInbound:
    """Manual: 0-35,99% → 0 | 36-44,99% → 1 | 45+ → 2"""
    def test_faixas(self):
        assert _pts_conversao_inbound(0) == 0
        assert _pts_conversao_inbound(36) == 1.0
        assert _pts_conversao_inbound(45) == 2.0


class TestConversaoTotal:
    """Manual: 0-27,99% → 0 | 28-34,99% → 2 | 35+ → 4"""
    def test_faixas(self):
        assert _pts_conversao_total(0) == 0
        assert _pts_conversao_total(28) == 2.0
        assert _pts_conversao_total(35) == 4.0


class TestConversaoM0:
    """Manual: 0-15,99% → 0 | 16-19,99% → 1,5 | 20+ → 3"""
    def test_faixas(self):
        assert _pts_conversao_m0(0) == 0
        assert _pts_conversao_m0(16) == 1.5
        assert _pts_conversao_m0(20) == 3.0


class TestDemoDU:
    """Manual: <3,2 → 0 | 3,2-3,99 → 2 | 4+ → 4 (valor absoluto)"""
    def test_faixas(self):
        assert _pts_demo_du(0) == 0
        assert _pts_demo_du(3.2) == 2.0
        assert _pts_demo_du(4) == 4.0


# ════════════════════════════════════════════════════════════════════════
# Pilar Gestão
# ════════════════════════════════════════════════════════════════════════

class TestUsoCorretoCromie:
    """Manual: 0-79,99% → 0 | 80-99,99% → 1 | 100% → 2"""
    def test_faixas(self):
        assert _pts_uso_correto_cromie(0) == 0
        assert _pts_uso_correto_cromie(80) == 1.0
        assert _pts_uso_correto_cromie(100) == 2.0


# ════════════════════════════════════════════════════════════════════════
# Pilar Engajamento
# ════════════════════════════════════════════════════════════════════════

class TestBig3:
    """Manual: 0 ações → 0 | 1 → 2 | 2 → 4 | 3 → 6"""
    def test_faixas(self):
        assert _pts_big3(0) == 0
        assert _pts_big3(1) == 2.0
        assert _pts_big3(2) == 4.0
        assert _pts_big3(3) == 6.0

    def test_negativo_nao_quebra(self):
        assert _pts_big3(-1) == 0


# ════════════════════════════════════════════════════════════════════════
# Classificação
# ════════════════════════════════════════════════════════════════════════

class TestClassificarOficial:
    """Manual: 6 faixas (Excelente/Certificada/Qualificada/Aderente/Em Desenv./Não Aderente)"""
    def test_excelente(self):
        assert _classificar_oficial(95) == "EXCELENTE"
        assert _classificar_oficial(100) == "EXCELENTE"

    def test_certificada(self):
        assert _classificar_oficial(76) == "CERTIFICADA"
        assert _classificar_oficial(94.99) == "CERTIFICADA"

    def test_qualificada(self):
        assert _classificar_oficial(60) == "QUALIFICADA"
        assert _classificar_oficial(75.99) == "QUALIFICADA"

    def test_aderente(self):
        assert _classificar_oficial(50) == "ADERENTE"
        assert _classificar_oficial(59.99) == "ADERENTE"

    def test_em_desenvolvimento(self):
        assert _classificar_oficial(36) == "EM_DESENVOLVIMENTO"
        assert _classificar_oficial(49.99) == "EM_DESENVOLVIMENTO"

    def test_nao_aderente(self):
        assert _classificar_oficial(0) == "NAO_ADERENTE"
        assert _classificar_oficial(35.99) == "NAO_ADERENTE"


class TestClassificarCor:
    """Cor pra UI (compatível com risco_enum). Mapeia 6 oficiais → 4 cores."""
    def test_verde_acima_76(self):
        # EXCELENTE e CERTIFICADA viram VERDE
        assert _classificar(76) == "VERDE"
        assert _classificar(95) == "VERDE"
        assert _classificar(100) == "VERDE"

    def test_laranja_50_a_75(self):
        # QUALIFICADA e ADERENTE viram LARANJA
        assert _classificar(50) == "LARANJA"
        assert _classificar(60) == "LARANJA"
        assert _classificar(75.99) == "LARANJA"

    def test_amarelo_36_a_49(self):
        # EM_DESENVOLVIMENTO vira AMARELO
        assert _classificar(36) == "AMARELO"
        assert _classificar(49.99) == "AMARELO"

    def test_vermelho_abaixo_36(self):
        # NAO_ADERENTE vira VERMELHO (descredenciamento)
        assert _classificar(0) == "VERMELHO"
        assert _classificar(35.99) == "VERMELHO"


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

class TestSafePct:
    def test_denominador_zero_retorna_zero(self):
        # Antes do fix, isso virava 5450% (numerador * 100 / 1)
        assert _safe_pct(27, 0) == 0
        assert _safe_pct(100, 0) == 0

    def test_denominador_negativo_retorna_zero(self):
        assert _safe_pct(50, -1) == 0

    def test_denominador_none_retorna_zero(self):
        assert _safe_pct(50, None) == 0

    def test_calculo_normal(self):
        assert _safe_pct(50, 100) == 50.0
        assert _safe_pct(27, 30) == 90.0


class TestMesBounds:
    def test_abril_2026(self):
        from datetime import date
        primeiro, prox = _mes_bounds("2026-04")
        assert primeiro == date(2026, 4, 1)
        assert prox == date(2026, 5, 1)

    def test_dezembro_vira_janeiro(self):
        from datetime import date
        primeiro, prox = _mes_bounds("2026-12")
        assert primeiro == date(2026, 12, 1)
        assert prox == date(2027, 1, 1)


# ════════════════════════════════════════════════════════════════════════
# Cenários reais herdados (test_pex_calc.py original)
# Convertidos: percentuais decimais → percentuais inteiros (0.72 → 72)
# ════════════════════════════════════════════════════════════════════════

class TestCenariosReais:
    def test_marco_conversao_total_39_51_pct_pontua_4(self):
        # Março/2025 estava em 39,51% → 4 pts
        assert _pts_conversao_total(39.51) == 4.0

    def test_marco_early_churn_11_2_pct_pontua_0(self):
        # Março/2025 estava em 11,2% (acima de 7,1%) → 0 pts
        assert _pts_early_churn(11.2) == 0

    def test_marco_crescimento_28_39_pct_pontua_0(self):
        # Março/2025 estava em 28,39% (abaixo de 32%) → 0 pts
        assert _pts_crescimento_40(28.39) == 0

    def test_marco_util_desconto_0_78_pct_pontua_2(self):
        # Março/2025 estava em 0,78% (muito abaixo de 15%) → 2 pts
        assert _pts_utilizacao_desconto(0.78) == 2.0

    def test_total_minimo_descredenciamento(self):
        # Manual: <36 → Não Aderente (descredenciamento)
        assert _classificar_oficial(35.99) == "NAO_ADERENTE"
        assert _classificar(35.99) == "VERMELHO"
        # 36 já entra em "Em Desenvolvimento" — limiar oficial
        assert _classificar_oficial(36) == "EM_DESENVOLVIMENTO"
        assert _classificar(36) == "AMARELO"
