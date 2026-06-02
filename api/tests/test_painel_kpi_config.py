"""Testes do seed estatico dos 10 KPIs.

Valida a lista KPIS em api/scripts/seed_painel.py: ordem, tipo, polaridade,
fonte, unicidade. Nao toca banco.
"""

from __future__ import annotations

import pytest

from scripts.seed_painel import KPIS


CODIGOS_ESPERADOS = {
    "LEAD",
    "AGEN",
    "APRE",
    "NMRR",
    "TICK_MED",
    "RN_PARC",
    "AGEND_MES",
    "NOSHOW",
    "APPS",
    "TREIN",
}


class TestSeedKpis:
    def test_tem_exatamente_dez_kpis(self):
        assert len(KPIS) == 10

    def test_codigos_unicos(self):
        codigos = [k["codigo"] for k in KPIS]
        assert len(codigos) == len(set(codigos)), "codigos duplicados"

    def test_codigos_baterem_com_esperado(self):
        codigos = {k["codigo"] for k in KPIS}
        assert codigos == CODIGOS_ESPERADOS

    def test_ordem_de_1_a_10_sem_buracos(self):
        ordens = sorted(k["ordem"] for k in KPIS)
        assert ordens == list(range(1, 11))

    def test_tipos_validos(self):
        validos = {"cumulativo", "media", "taxa_invertida"}
        for kpi in KPIS:
            assert kpi["tipo"] in validos, f"{kpi['codigo']} tem tipo invalido"

    def test_polaridade_valida(self):
        validos = {"maior", "menor"}
        for kpi in KPIS:
            assert kpi["polaridade"] in validos

    def test_taxa_invertida_eh_menor(self):
        # Por contrato: taxa_invertida sempre tem polaridade 'menor'.
        for kpi in KPIS:
            if kpi["tipo"] == "taxa_invertida":
                assert kpi["polaridade"] == "menor", (
                    f"{kpi['codigo']}: taxa_invertida deveria ser polaridade menor"
                )

    def test_noshow_eh_taxa_invertida_e_menor(self):
        noshow = next(k for k in KPIS if k["codigo"] == "NOSHOW")
        assert noshow["tipo"] == "taxa_invertida"
        assert noshow["polaridade"] == "menor"

    def test_tick_med_eh_media(self):
        tick = next(k for k in KPIS if k["codigo"] == "TICK_MED")
        assert tick["tipo"] == "media"

    def test_demais_sao_cumulativos(self):
        # LEAD, AGEN, APRE, NMRR, RN_PARC, AGEND_MES, APPS, TREIN
        cumulativos_esperados = {
            "LEAD",
            "AGEN",
            "APRE",
            "NMRR",
            "RN_PARC",
            "AGEND_MES",
            "APPS",
            "TREIN",
        }
        cumulativos_reais = {k["codigo"] for k in KPIS if k["tipo"] == "cumulativo"}
        assert cumulativos_reais == cumulativos_esperados

    @pytest.mark.parametrize("kpi", KPIS, ids=[k["codigo"] for k in KPIS])
    def test_cor_hex_formato_valido(self, kpi):
        cor = kpi["cor_hex"]
        assert cor.startswith("#")
        assert len(cor) == 7
        # tem que parsear como hex
        int(cor[1:], 16)

    @pytest.mark.parametrize("kpi", KPIS, ids=[k["codigo"] for k in KPIS])
    def test_icone_tabler_outline(self, kpi):
        # Padrao tabler outline: comeca com 'ti-' e nao termina com '-filled'.
        assert kpi["icone"].startswith("ti-"), (
            f"{kpi['codigo']}: icone deve ser tabler ti-*"
        )
        assert not kpi["icone"].endswith("-filled"), (
            f"{kpi['codigo']}: icone filled nao e suportado pelo widget"
        )

    @pytest.mark.parametrize("kpi", KPIS, ids=[k["codigo"] for k in KPIS])
    def test_fonte_eh_bridge_ou_hipo(self, kpi):
        assert kpi["fonte"] in {"bridge", "hipo"}

    def test_seed_inicial_todos_bridge(self):
        # Decisao da Etapa 1: como ainda nao migramos nenhuma fonte de dados,
        # todos os 10 KPIs partem como 'bridge'. As proximas etapas v1.5+ vao
        # virando cada um para 'hipo' conforme a operacao migra.
        for kpi in KPIS:
            assert kpi["fonte"] == "bridge", (
                f"{kpi['codigo']}: seed inicial deveria ser 'bridge', e {kpi['fonte']}"
            )

    @pytest.mark.parametrize("kpi", KPIS, ids=[k["codigo"] for k in KPIS])
    def test_nome_nao_vazio(self, kpi):
        assert kpi["nome"]
        assert kpi["nome"].strip() == kpi["nome"]
