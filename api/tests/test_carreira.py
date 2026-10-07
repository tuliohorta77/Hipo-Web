"""
HIPO — Carreira · Desempenho (/carreira/desempenho), com banco.

Reaproveita o agosto/2026 da RPeR (tests/test_rper.py): os números da
pessoa no Desempenho têm que ser os mesmos da coluna dela na RPeR.
"""
from datetime import date

from tests.test_rper import agosto, time  # noqa: F401  (fixtures)

SENHA = "test123"


async def _login(client, email):
    r = await client.post("/auth/login", data={"username": email, "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ind(body, chave):
    return next(l for l in body["indicadores"] if l["chave"] == chave)


async def _meta(db, squad, uid, indicador, valor, ano=2026, mes=8):
    await db.execute(
        "INSERT INTO metas_comerciais (squad, usuario_id, indicador, ano, mes, valor) "
        "VALUES ($1, $2, $3, $4, $5, $6)", squad, uid, indicador, ano, mes, valor,
    )


async def _get(client, h, **params):
    return await client.get("/carreira/desempenho", params=params, headers=h)


class TestMesFechado:
    async def test_ev_ve_o_proprio_mes_com_meta(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        h = await _login(client, "jakeline@teste.com")
        r = await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["squad"] == "EV" and b["aberto"] is False and b["modo_leitura"] is False
        assert b["pode_escolher_pessoa"] is False and b["pessoas"] == []
        nmrr = _ind(b, "nmrr")
        # Mesmos números da coluna da pessoa na RPeR.
        assert nmrr["realizado"] == 450 and nmrr["meta_mes"] == 900
        assert nmrr["atingimento"] == 0.5 and nmrr["carinha"] == "triste"
        assert _ind(b, "reunioes_realizadas")["realizado"] == 2
        assert b["tem_meta"] is True
        assert b["ponto_de_atencao"]["chave"] == "nmrr"
        assert [e["chave"] for e in b["funil"]] == ["reunioes_realizadas", "propostas", "vendas"]
        assert len(b["historico"]) == 6 and b["historico"][-1]["mes"] == 8

    async def test_sem_meta_nao_inventa_atingimento(self, agosto, client):  # noqa: F811
        h = await _login(client, "kethlleen@teste.com")
        b = (await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")).json()
        assert b["squad"] == "SDR" and b["tem_meta"] is False
        assert _ind(b, "agendamentos")["realizado"] == 3
        assert all(l["atingimento"] is None for l in b["indicadores"])
        assert b["ponto_de_atencao"] is None


class TestMesAberto:
    async def test_mes_corrente_vai_ate_hoje_e_compara_com_a_meta_de_hoje(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "reunioes_realizadas", 10)
        h = await _login(client, "jakeline@teste.com")
        b = (await _get(client, h, hoje="2026-08-13")).json()
        assert b["aberto"] is True and (b["ano"], b["mes"]) == (2026, 8)
        assert 0 < b["dia_util"] < b["dias_uteis"]
        reun = _ind(b, "reunioes_realizadas")
        # Só a reunião de 12/08: a de 14 e a de 31 ainda não aconteceram.
        assert reun["realizado"] == 1
        assert reun["meta_hoje"] < reun["meta_mes"] == 10
        # A venda de 20/08 ainda não aconteceu em 13/08.
        assert _ind(b, "vendas")["realizado"] == 0


class TestQuemVe:
    async def test_gestao_ve_a_pessoa_em_modo_leitura(self, agosto, client):  # noqa: F811
        r = await _get(client, agosto["h"], usuario_id=str(agosto["ec"]),
                       ano=2026, mes=8, hoje="2026-09-10")
        b = r.json()
        assert b["squad"] == "EC" and b["modo_leitura"] is True
        assert b["pode_escolher_pessoa"] is True
        assert {p["cargo"] for p in b["pessoas"]} == {"SDR", "EV", "EC"}
        assert _ind(b, "mrr")["realizado"] == 450

    async def test_operacional_nao_ve_outra_pessoa(self, agosto, client):  # noqa: F811
        h = await _login(client, "jakeline@teste.com")
        r = await _get(client, h, usuario_id=str(agosto["sdr"]))
        assert r.status_code == 403

    async def test_cargo_sem_squad_recebe_resposta_vazia(self, time, client):  # noqa: F811
        b = (await _get(client, time["h"])).json()
        assert b["squad"] is None and b["indicadores"] == [] and b["historico"] == []

    async def test_mes_futuro_e_recusado(self, time, client):  # noqa: F811
        r = await _get(client, time["h"], ano=2026, mes=12, hoje=str(date(2026, 8, 10)))
        assert r.status_code == 422

    async def test_ano_sem_mes_e_recusado(self, time, client):  # noqa: F811
        r = await _get(client, time["h"], ano=2026)
        assert r.status_code == 422


# ── Scorecard das reuniões (só EV) ───────────────────────────────────

from services import roteiro_scorecard as sc  # noqa: E402
from tests.test_rper import em  # noqa: E402


async def _reuniao_do_dia(db, dia, hora=10):
    return await db.fetchval(
        "SELECT r.id FROM reunioes r JOIN tarefas t ON t.id = r.tarefa_id WHERE t.prazo = $1",
        em(dia, hora),
    )


async def _avaliar(db, rid, notas, *, versao=None, status="pronta", foco=None,
                   gestor=None):
    """Grava uma avaliação pronta: `notas` = {item: nota_ia}."""
    total = None
    if status == "pronta":
        total = sum((gestor or {}).get(i, n) or 0 for i, n in notas.items())
    await db.execute(
        """
        INSERT INTO reuniao_avaliacoes (reuniao_id, versao_roteiro, status, nota_total,
                                        foco_proxima, gerada_em)
        VALUES ($1, $2, $3::varchar, $4, $5, CASE WHEN $3::varchar = 'pronta' THEN NOW() END)
        """,
        rid, versao or sc.VERSAO, status, total, foco,
    )
    for item, nota in notas.items():
        g = (gestor or {}).get(item)
        await db.execute(
            "INSERT INTO reuniao_avaliacao_itens (reuniao_id, item, nota_ia, nota_gestor, ajustada_em) "
            "VALUES ($1, $2, $3, $4, CASE WHEN $4::smallint IS NULL THEN NULL ELSE NOW() END)",
            rid, item, nota, g,
        )


class TestScorecard:
    async def test_ev_ve_a_nota_do_scorecard_das_suas_reunioes(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        dia12 = await _reuniao_do_dia(db, 12)
        dia31 = await _reuniao_do_dia(db, 31, 23)
        no_show = await _reuniao_do_dia(db, 14)
        # 12/08: itens 1-8 com 2 e 9-10 com 0 = 16, e a gestão baixou o item 1
        # para 0 -> 14.
        notas = {i: (2 if i <= 8 else 0) for i in range(1, 11)}
        await _avaliar(db, dia12, notas, foco="Explorar a objeção antes de responder.",
                       gestor={1: 0})
        # 31/08: ainda avaliando -> fora da média.
        await _avaliar(db, dia31, {}, status="aguardando")
        # No-show não entra, nem com avaliação (não acontece, mas não pode contar).
        await _avaliar(db, no_show, {i: 2 for i in range(1, 11)})

        h = await _login(client, "jakeline@teste.com")
        b = (await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")).json()
        s = b["scorecard"]
        assert s["media"] == 14.0 and s["avaliadas"] == 1 and s["realizadas"] == 2
        assert s["sem_nota"] == 1
        assert s["meta"] == 15.0 and s["meta_padrao"] is True
        assert s["carinha"] == "neutro" and s["faixa"] == "media"
        assert s["foco"]["texto"] == "Explorar a objeção antes de responder."
        # Item 1 vale a nota da gestão (0); 9 e 10 empatam em 0 com ele -> o 1.
        assert s["item_fraco"]["item"] == 1
        itens = {i["item"]: i["media"] for i in s["itens"]}
        assert itens[2] == 2.0 and itens[9] == 0.0
        # Mais recente primeiro: a de 31/08 (avaliando) e depois a de 12/08.
        assert [r["nota_status"] for r in s["reunioes"]] == ["avaliando", "ia"]
        assert s["reunioes"][1]["empresa"] == "Metalurgica Alfa LTDA"
        assert len(s["historico"]) == 6 and s["historico"][-1]["media"] == 14.0
        assert s["historico"][0]["media"] is None

    async def test_meta_vem_do_quadro_do_monitor(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        await db.execute(
            "INSERT INTO monitor_metas (indicador, ano, mes, valor) VALUES ('scorecard', 2026, 8, 12)")
        await _avaliar(db, await _reuniao_do_dia(db, 12), {i: 2 for i in range(1, 11)})
        h = await _login(client, "jakeline@teste.com")
        s = (await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")).json()["scorecard"]
        assert s["meta"] == 12.0 and s["meta_padrao"] is False
        assert s["media"] == 20.0 and s["carinha"] == "muito_feliz"
        assert s["item_fraco"] is None

    async def test_versao_antiga_do_roteiro_nao_conta(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        await _avaliar(db, await _reuniao_do_dia(db, 12), {i: 1 for i in range(1, 11)},
                       versao="2000-01-01")
        h = await _login(client, "jakeline@teste.com")
        s = (await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")).json()["scorecard"]
        assert s["media"] is None and s["avaliadas"] == 0 and s["realizadas"] == 2

    async def test_gestao_ve_o_scorecard_do_ev(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        await _avaliar(db, await _reuniao_do_dia(db, 12), {i: 1 for i in range(1, 11)})
        b = (await _get(client, agosto["h"], usuario_id=str(agosto["ev"]),
                        ano=2026, mes=8, hoje="2026-09-10")).json()
        assert b["modo_leitura"] is True and b["scorecard"]["media"] == 10.0

    async def test_quem_nao_e_ev_nao_tem_scorecard(self, agosto, client):  # noqa: F811
        h = await _login(client, "kethlleen@teste.com")
        b = (await _get(client, h, ano=2026, mes=8, hoje="2026-09-10")).json()
        assert b["squad"] == "SDR" and b["scorecard"] is None

    async def test_mes_aberto_so_conta_ate_hoje(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        await _avaliar(db, await _reuniao_do_dia(db, 12), {i: 2 for i in range(1, 11)})
        h = await _login(client, "jakeline@teste.com")
        s = (await _get(client, h, hoje="2026-08-13")).json()["scorecard"]
        assert s["realizadas"] == 1 and s["media"] == 20.0
