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


# ── Scorecard das reuniões (EV) ──────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402

from services import roteiro_scorecard as sc  # noqa: E402


def _reuniao(rid, nota=None, status="pronta", versao=None, validada=False,
             foco=None, dia=10):
    return {
        "reuniao_id": rid, "inicio": datetime(2026, 8, dia, 13, tzinfo=timezone.utc),
        "empresa": f"Empresa {rid}", "oportunidade_numero": f"OPP-{rid}",
        "av_status": status, "av_nota": nota, "av_versao": versao or sc.VERSAO,
        "av_validada": validada, "foco_proxima": foco,
    }


def test_so_ev_tem_scorecard():
    assert d.tem_scorecard("EV")
    assert not d.tem_scorecard("SDR") and not d.tem_scorecard("EC")
    assert not d.tem_scorecard(None)


def test_nota_da_reuniao_segue_a_regra_do_monitor():
    assert d.nota_da_reuniao(_reuniao(1, 14)) == (14.0, "ia")
    assert d.nota_da_reuniao(_reuniao(1, 14, validada=True)) == (14.0, "validada")
    assert d.nota_da_reuniao(_reuniao(1, status="aguardando")) == (None, "avaliando")
    assert d.nota_da_reuniao(_reuniao(1, status="erro")) == (None, "erro")
    # Roteiro de outra versão não se compara.
    assert d.nota_da_reuniao(_reuniao(1, 14, versao="2000-01-01")) == (None, None)
    assert d.nota_da_reuniao({"av_status": None}) == (None, None)


def test_media_deixa_reuniao_sem_nota_fora():
    rs = [_reuniao(1, 12), _reuniao(2, 17), _reuniao(3, status="aguardando"), {"av_status": None}]
    assert d.media_scorecard(rs) == (14.5, 2)
    assert d.media_scorecard([]) == (None, 0)


def test_media_por_item_conta_item_sem_nota_como_zero():
    itens = {1: {1: 2, 5: 0}, 2: {1: 1, 5: None}}
    medias = d.medias_por_item(itens, [1, 2])
    assert [m["item"] for m in medias] == list(range(1, 11))
    assert medias[0]["media"] == 1.5 and medias[0]["fracao"] == 0.75
    assert medias[4]["media"] == 0.0 and medias[4]["media_txt"] == "0,0"
    # Sem reunião avaliada não há média nenhuma (nem zero).
    assert all(m["media"] is None for m in d.medias_por_item({}, []))


def test_item_mais_fraco_so_abaixo_do_limiar_e_empate_pelo_roteiro():
    itens = [{"item": i, "media": 2.0} for i in range(1, 11)]
    assert d.item_mais_fraco(itens) is None
    itens[6]["media"] = 0.5
    itens[3]["media"] = 0.5
    assert d.item_mais_fraco(itens)["item"] == 4
    assert d.item_mais_fraco([{"item": 1, "media": None}]) is None


def test_bloco_do_scorecard():
    rs = [
        _reuniao(3, status="aguardando", dia=20),
        _reuniao(2, 16, foco="Fazer duas perguntas de implicação.", dia=15),
        _reuniao(1, 10, foco="Foco antigo", dia=5),
    ]
    itens = {2: {i: 2 for i in range(1, 9)}, 1: {i: 1 for i in range(1, 11)}}
    b = d.scorecard(rs, itens, 15.0, meta_padrao=True)
    assert b["media"] == 13.0 and b["media_txt"] == "13,0"
    assert (b["avaliadas"], b["realizadas"], b["sem_nota"]) == (2, 3, 1)
    assert b["meta"] == 15.0 and b["meta_padrao"] is True
    assert round(b["atingimento"], 3) == round(13 / 15, 3) and b["carinha"] == "neutro"
    assert b["faixa"] == "media" and b["nota_maxima"] == 20
    # Itens 9 e 10: 0 numa reunião e 1 na outra -> 0,5; empate fica o 9.
    assert b["item_fraco"]["item"] == 9 and b["item_fraco"]["media"] == 0.5
    # O foco é o da reunião avaliada mais recente.
    assert b["foco"]["texto"] == "Fazer duas perguntas de implicação."
    assert b["foco"]["reuniao_id"] == "2"
    assert [r["nota_status"] for r in b["reunioes"]] == ["avaliando", "ia", "ia"]
    assert b["reunioes"][1]["faixa"] == "boa"


def test_bloco_sem_reuniao_avaliada_nao_inventa_nota():
    b = d.scorecard([_reuniao(1, status="erro")], {}, 15.0, meta_padrao=True)
    assert b["media"] is None and b["atingimento"] is None and b["carinha"] is None
    assert b["item_fraco"] is None and b["foco"] is None and b["sem_nota"] == 1


def test_ponto_do_historico_do_scorecard():
    p = d.ponto_scorecard(2026, 8, [_reuniao(1, 18), _reuniao(2, 15)])
    assert p == {"ano": 2026, "mes": 8, "rotulo": "agosto", "media": 16.5,
                 "media_txt": "16,5", "avaliadas": 2, "faixa": "boa"}
