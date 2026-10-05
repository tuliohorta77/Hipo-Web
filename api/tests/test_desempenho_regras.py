"""
HIPO — Carreira · Desempenho: regras puras (services/desempenho.py).
"""
from services import desempenho as d
from services import rper


def _bruto_ev(**extra):
    base = {"followups": 10, "taxa_execucao": 80.0, "oportunidades": 5, "propostas": 4,
            "reunioes_realizadas": 8, "vendas": 2, "taxa_conversao": 25.0, "nmrr": 900.0,
            "ticket_medio": 450.0, "em_negociacao": 3, "pipeline": 5000.0}
    base.update(extra)
    return base


def test_squad_do_cargo():
    assert d.squad_do_cargo("SDR") == "SDR"
    assert d.squad_do_cargo("EC") == "EC"
    assert d.squad_do_cargo("EP") is None
    assert d.squad_do_cargo(None) is None


def test_linhas_na_ordem_da_rper():
    linhas = d.linhas("EV", _bruto_ev(), {}, aberto=False, dia_util=0, dias_uteis=20)
    assert [l["chave"] for l in linhas] == [i.chave for i in rper.INDICADORES["EV"]]
    assert all(l["atingimento"] is None and l["carinha"] is None for l in linhas)


def test_mes_aberto_compara_com_a_meta_de_hoje():
    linhas = d.linhas("EV", _bruto_ev(), {"nmrr": 2000, "noshow": 10}, aberto=True,
                      dia_util=10, dias_uteis=20)
    nmrr = next(l for l in linhas if l["chave"] == "nmrr")
    assert nmrr["meta_hoje"] == 1000.0
    assert nmrr["atingimento"] == 0.9
    assert nmrr["falta_mes"] == 1100.0
    assert nmrr["falta_mes_txt"] == "R$ 1.100"


def test_posicao_compara_com_a_meta_cheia_mesmo_aberto():
    linhas = d.linhas("EV", _bruto_ev(), {"pipeline": 10000}, aberto=True,
                      dia_util=5, dias_uteis=20)
    pipe = next(l for l in linhas if l["chave"] == "pipeline")
    assert pipe["meta_hoje"] == 10000.0 and pipe["atingimento"] == 0.5


def test_mes_fechado_usa_a_meta_do_mes_e_nao_mostra_meta_de_hoje():
    linhas = d.linhas("EV", _bruto_ev(), {"nmrr": 900}, aberto=False, dia_util=20, dias_uteis=20)
    nmrr = next(l for l in linhas if l["chave"] == "nmrr")
    assert nmrr["meta_hoje"] is None and nmrr["atingimento"] == 1.0
    assert nmrr["carinha"] == "feliz" and nmrr["falta_mes"] == 0.0


def test_ponto_de_atencao_e_o_pior_com_meta():
    linhas = d.linhas("EV", _bruto_ev(), {"nmrr": 900, "propostas": 10, "vendas": 2},
                      aberto=False, dia_util=20, dias_uteis=20)
    assert d.ponto_de_atencao(linhas)["chave"] == "propostas"


def test_sem_ponto_de_atencao_quando_tudo_bate():
    linhas = d.linhas("EV", _bruto_ev(), {"nmrr": 900}, aberto=False, dia_util=20, dias_uteis=20)
    assert d.ponto_de_atencao(linhas) is None
    assert d.ponto_de_atencao([]) is None


def test_funil_do_ev_com_taxas():
    f = d.funil("EV", _bruto_ev())
    assert [e["chave"] for e in f] == ["reunioes_realizadas", "propostas", "vendas"]
    assert f[0]["taxa_txt"] == ""
    assert f[1]["taxa_txt"] == "50%" and f[2]["taxa_txt"] == "50%"


def test_funil_com_etapa_zerada_nao_divide_por_zero():
    f = d.funil("EV", _bruto_ev(reunioes_realizadas=0, propostas=0, vendas=0))
    assert f[1]["taxa"] is None and f[1]["taxa_txt"] == "—"


def test_funil_do_ec_usa_razao_por_parceiro():
    f = d.funil("EC", {"contas_gestao": 10, "reunioes_carteira": 15, "leads": 3, "vendas": 1})
    assert f[1]["taxa_txt"] == "1,5"
    assert f[3]["taxa_txt"] == "33%"


def test_funil_de_cada_squad_usa_indicadores_que_existem():
    for squad, etapas in d.FUNIS.items():
        chaves = {i.chave for i in rper.INDICADORES[squad]}
        assert {e.chave for e in etapas} <= chaves, squad


def test_historico_ignora_indicador_de_posicao():
    p = d.ponto_historico("EV", 2026, 8, _bruto_ev(), {"nmrr": 900})
    assert "pipeline" not in p["indicadores"] and "em_negociacao" not in p["indicadores"]
    assert p["indicadores"]["nmrr"]["atingimento_txt"] == "100%"
    assert p["rotulo"] == "agosto"


def test_meses_anteriores_atravessa_o_ano():
    assert d.meses_anteriores(2026, 2, 3) == [(2025, 11), (2025, 12), (2026, 1)]
