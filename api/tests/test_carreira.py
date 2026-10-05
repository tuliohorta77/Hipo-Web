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
