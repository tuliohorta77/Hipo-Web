"""
HIPO — Contratos (043): regras puras do repasse Controller -> Spectre.

Sem banco: roda no pytest local do Windows. Os números conferem com a
planilha "SPECTRE MED - CONTROLE CONTRATOS" (aba 202609).
"""
from datetime import date
from decimal import Decimal

import pytest

from services import repasse as r


class TestCompetencia:
    def test_texto_vira_dia_1(self):
        assert r.competencia_de_texto("2026-10") == date(2026, 10, 1)

    @pytest.mark.parametrize("ruim", ["2026-13", "26-10", "2026/10", "", "abc", "1999-01"])
    def test_texto_ruim(self, ruim):
        with pytest.raises(r.RepasseInvalido):
            r.competencia_de_texto(ruim)

    def test_rotulo(self):
        assert r.rotulo_competencia(date(2026, 2, 1)) == "fev/2026"

    def test_somar_meses_vira_o_ano(self):
        assert r.somar_meses(date(2026, 11, 1), 3) == date(2027, 2, 1)
        assert r.somar_meses(date(2026, 1, 1), -1) == date(2025, 12, 1)

    def test_competencia_de_data(self):
        assert r.competencia_de_data(date(2026, 9, 20)) == date(2026, 9, 1)


class TestValorDoContrato:
    def test_por_vida(self):
        assert r.valor_do_contrato(267, valor_por_vida="11.5") == Decimal("3070.50")

    def test_valor_fixo(self):
        assert r.valor_do_contrato(5, valor_fixo="180") == Decimal("180.00")

    def test_por_vida_tem_prioridade(self):
        assert r.valor_do_contrato(2, valor_por_vida=10, valor_fixo=999) == Decimal("20.00")

    def test_zero_vidas_por_vida_da_zero(self):
        assert r.valor_do_contrato(0, valor_por_vida="25") == Decimal("0.00")

    def test_sem_valor(self):
        with pytest.raises(r.RepasseInvalido):
            r.valor_do_contrato(3)

    def test_negativos(self):
        with pytest.raises(r.RepasseInvalido):
            r.valor_do_contrato(-1, valor_fixo=10)
        with pytest.raises(r.RepasseInvalido):
            r.valor_do_contrato(1, valor_por_vida=-1)
        with pytest.raises(r.RepasseInvalido):
            r.valor_do_contrato(1, valor_fixo=-1)


class TestCalcular:
    @pytest.mark.parametrize("k,l,n,o", [
        # set/2026 -- SERVCON PRIME, FAT, FX, TONBOO (30%)
        ("3070.50", "921.15", "132.00", "789.15"),
        ("575.00", "172.50", "24.72", "147.78"),
        ("3092.98", "927.89", "132.97", "794.92"),
        ("180.00", "54.00", "7.74", "46.26"),
    ])
    def test_confere_com_a_planilha_30(self, k, l, n, o):
        c = r.calcular(k, 30, "14.33")
        assert (c.valor_repasse, c.valor_imposto, c.valor_liquido) == (
            Decimal(l), Decimal(n), Decimal(o),
        )

    def test_primeiro_mes_100(self):
        # ago/2026 -- MESTRE CAFE: 130 a 100%
        c = r.calcular("130", 100, "14.33")
        assert (c.valor_repasse, c.valor_imposto, c.valor_liquido) == (
            Decimal("130.00"), Decimal("18.63"), Decimal("111.37"),
        )

    def test_liquido_e_sempre_repasse_menos_imposto(self):
        for k in ("0.01", "1.99", "12345.67", "0"):
            c = r.calcular(k, "33.33", "14.33")
            assert c.valor_liquido == c.valor_repasse - c.valor_imposto

    @pytest.mark.parametrize("pct", [-1, "100.01", 250])
    def test_percentual_fora(self, pct):
        with pytest.raises(r.RepasseInvalido):
            r.calcular(100, pct, 10)
        with pytest.raises(r.RepasseInvalido):
            r.calcular(100, 30, pct)


class TestPrimeiroMes:
    def test_sem_lancamento_nenhum_e_o_primeiro(self):
        assert r.eh_primeiro_mes(date(2026, 10, 1), None, False) is True

    def test_sem_primeira_mas_com_anterior_nao_e(self):
        assert r.eh_primeiro_mes(date(2026, 10, 1), None, True) is False

    def test_com_primeira_gravada_so_ela(self):
        assert r.eh_primeiro_mes(date(2026, 8, 1), date(2026, 8, 1), True) is True
        assert r.eh_primeiro_mes(date(2026, 9, 1), date(2026, 8, 1), True) is False

    def test_percentual_do_mes(self):
        assert r.percentual_do_mes(True, 30, 100) == Decimal("100.00")
        assert r.percentual_do_mes(False, 30, 100) == Decimal("30.00")


class TestTotais:
    def test_nf_e_soma_dos_liquidos_menos_descontos(self):
        lancs = [
            {"valor_contrato": "575", "valor_repasse": "172.50", "valor_imposto": "24.72",
             "valor_liquido": "147.78", "pago": True, "vidas": 23},
            {"valor_contrato": "180", "valor_repasse": "54", "valor_imposto": "7.74",
             "valor_liquido": "46.26", "pago": False, "vidas": 5},
        ]
        t = r.totais(lancs, [{"valor": "10.04"}])
        assert t["valor_liquido"] == Decimal("194.04")
        assert t["liquido_pago"] == Decimal("147.78")
        assert t["descontos"] == Decimal("10.04")
        assert t["valor_nf"] == Decimal("184.00")
        assert t["vidas"] == 28

    def test_vazio(self):
        t = r.totais([])
        assert t["valor_nf"] == Decimal("0.00")


class TestVigencia:
    def test_antes_da_venda_nao_entra(self):
        assert not r.contrato_vale_na_competencia(date(2026, 1, 1), date(2026, 2, 2), "ativo", None)

    def test_mes_da_venda_entra(self):
        assert r.contrato_vale_na_competencia(date(2026, 2, 1), date(2026, 2, 2), "ativo", None)

    def test_encerrado_vale_ate_o_mes_do_encerramento(self):
        assert r.contrato_vale_na_competencia(date(2026, 9, 1), date(2026, 2, 2), "encerrado", date(2026, 9, 15))
        assert not r.contrato_vale_na_competencia(date(2026, 10, 1), date(2026, 2, 2), "encerrado", date(2026, 9, 15))


class TestProximoPasso:
    def test_lancar(self):
        p = r.proximo_passo(date(2026, 10, 1), 3, Decimal("0"), None, None)
        assert p["acao"] == "lancar"
        assert "3 contratos" in p["texto"] and "out/2026" in p["texto"]

    def test_um_contrato_no_singular(self):
        assert "1 contrato de" in r.proximo_passo(date(2026, 10, 1), 1, Decimal("0"), None, None)["texto"]

    def test_emitir_nf_com_valor_brasileiro(self):
        p = r.proximo_passo(date(2026, 9, 1), 0, Decimal("5923.18"), None, None)
        assert p["acao"] == "emitir_nf"
        assert "R$ 5.923,18" in p["texto"]

    def test_receber(self):
        assert r.proximo_passo(date(2026, 9, 1), 0, Decimal("1"), "123", None)["acao"] == "receber"

    def test_fechado(self):
        assert r.proximo_passo(date(2026, 9, 1), 0, Decimal("1"), "123", date(2026, 9, 25))["acao"] == "fechado"


class TestValidarContrato:
    def test_ok(self):
        r.validar_contrato("por_vida", "11.5", None, 30, 100, "14.33")
        r.validar_contrato("valor_fixo", None, "180", 30, 100, "14.33")

    @pytest.mark.parametrize("args", [
        ("mensal", "1", None, 30, 100, 10),
        ("por_vida", None, "10", 30, 100, 10),
        ("valor_fixo", "10", None, 30, 100, 10),
        ("por_vida", "-1", None, 30, 100, 10),
        ("por_vida", "1", None, 130, 100, 10),
        ("por_vida", "1", None, 30, -5, 10),
        ("por_vida", "1", None, 30, 100, 101),
    ])
    def test_invalidos(self, args):
        with pytest.raises(r.RepasseInvalido):
            r.validar_contrato(*args)
