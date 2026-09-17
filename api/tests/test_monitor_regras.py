"""
HIPO — Regras puras do Monitor: meta MTD, atingimento e carinha.

Sem banco: roda no pytest local do Windows. O que estes testes seguram e a
regua que o Tulio definiu, e as tres armadilhas de divisao que um painel de
parede tem (meta zero, denominador zero e indicador invertido).
"""
import pytest

from services import monitor as regras


class TestMetaMtd:
    def test_proporcional_aos_dias_uteis_corridos(self):
        """A conta do painel: 276 no mes, cinco de vinte dias uteis -> 69."""
        assert regras.meta_mtd(276, 5, 20) == 69.0

    def test_no_ultimo_dia_util_cobra_o_mes_inteiro(self):
        assert regras.meta_mtd(276, 20, 20) == 276.0

    def test_antes_do_primeiro_dia_util_nao_cobra_nada(self):
        assert regras.meta_mtd(276, 0, 20) == 0.0

    def test_nao_passa_do_mes_inteiro(self):
        """Dia util fora da faixa (dado torto) nao vira meta maior que a do mes."""
        assert regras.meta_mtd(276, 40, 20) == 276.0

    def test_taxa_nao_se_proporcionaliza(self):
        """
        11% de no-show no dia 5 vale o mesmo que no dia 25. Proporcionalizar
        daria "meta de 7,5% de no-show" no comeco do mes — numero sem
        significado.
        """
        assert regras.meta_mtd(30, 5, 20, regras.TAXA_INVERSA) == 30.0
        assert regras.meta_mtd(450, 5, 20, regras.TAXA) == 450.0

    def test_sem_meta_continua_sem_meta(self):
        assert regras.meta_mtd(None, 5, 20) is None

    def test_mes_sem_dia_util_nao_estoura(self):
        assert regras.meta_mtd(276, 3, 0) == 0.0


class TestAtingimento:
    def test_acumulativo(self):
        assert regras.atingimento(69, 69) == 1.0
        assert regras.atingimento(35, 70) == 0.5

    def test_meta_zero_nao_da_divisao_por_zero(self):
        assert regras.atingimento(5, 0) is None

    def test_sem_resultado_ou_sem_meta(self):
        assert regras.atingimento(None, 10) is None
        assert regras.atingimento(10, None) is None

    def test_indicador_aberto_nao_tem_atingimento(self):
        """O treinamento: existe o quadro, nao existe a fonte."""
        assert regras.atingimento(10, 10, regras.ABERTO) is None

    def test_taxa_inversa_bate_a_meta_ficando_abaixo(self):
        """No-show de 11% contra meta de 30% e mais que 100% de atingimento."""
        assert regras.atingimento(11, 30, regras.TAXA_INVERSA) > 1
        assert regras.atingimento(40, 30, regras.TAXA_INVERSA) == 0.75

    def test_taxa_inversa_zerada_e_o_melhor_resultado(self):
        assert regras.atingimento(0, 30, regras.TAXA_INVERSA) == 2.0


class TestCarinha:
    @pytest.mark.parametrize("valor,esperada", [
        (1.5, "muito_feliz"),
        (1.10, "muito_feliz"),
        (1.09, "feliz"),
        (1.0, "feliz"),
        (0.99, "neutro"),
        (0.70, "neutro"),
        (0.69, "triste"),
        (0.50, "triste"),
        (0.49, "bravo"),
        (0.0, "bravo"),
    ])
    def test_a_regua_do_tulio(self, valor, esperada):
        assert regras.carinha(valor) == esperada

    def test_sem_atingimento_nao_tem_carinha(self):
        """Carinha sobre denominador inventado e pior que quadro vazio."""
        assert regras.carinha(None) is None


class TestDivisoes:
    def test_ticket_medio(self):
        assert regras.media(4500, 10) == 450.0

    def test_ticket_medio_sem_contrato_e_indefinido(self):
        assert regras.media(4500, 0) is None
        assert regras.media(0, 0) is None

    def test_taxa_percentual(self):
        assert regras.taxa_percentual(3, 27) == 11.1

    def test_taxa_sem_denominador_e_indefinida(self):
        """Mes sem reuniao fechada tem no-show indefinido, nao 0%."""
        assert regras.taxa_percentual(0, 0) is None


class TestCatalogo:
    def test_dez_quadros_na_ordem_do_painel(self):
        chaves = [i.chave for i in sorted(regras.INDICADORES, key=lambda x: x.ordem)]
        assert chaves == [
            "lead", "agen", "apre", "nmrr", "ticket_medio",
            "reunioes_parceria", "agendamentos_mes", "noshow",
            "contratos", "treinamento",
        ]

    def test_natureza_de_cada_um_e_valida(self):
        for ind in regras.INDICADORES:
            assert ind.natureza in regras.NATUREZAS
            assert ind.formato in ("inteiro", "moeda", "percentual")

    def test_indicador_desconhecido_e_recusado(self):
        with pytest.raises(regras.MonitorInvalido):
            regras.validar_indicador("faturamento")
