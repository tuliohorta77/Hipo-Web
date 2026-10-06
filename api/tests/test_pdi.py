"""
HIPO — Carreira · PDI (/carreira/pdi), com banco.

Reaproveita o agosto/2026 da RPeR: o EV fechou NMRR 450 contra meta 900
(50%), então o HIPO sugere uma ação de Desempenho.
"""
from datetime import timedelta

from routers.carreira import _hoje
from tests.test_carreira import _login, _meta
from tests.test_rper import agosto, time  # noqa: F401  (fixtures)

HOJE = "2026-08-31"


def _prazo(dias=20):
    # "Hoje" no fuso da operacao, como o servidor: date.today() do runner
    # (UTC) ja e amanha depois das 21h em Sao Paulo.
    return (_hoje() + timedelta(days=dias)).isoformat()


async def _pdi(client, h, **params):
    r = await client.get("/carreira/pdi", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


class TestSugestoes:
    async def test_desempenho_abaixo_de_70_vira_sugestao_para_a_gestao(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        b = await _pdi(client, agosto["h"], usuario_id=str(agosto["ev"]), hoje=HOJE)
        assert b["pode_gerir"] is True and b["modo_leitura"] is True
        s = next(x for x in b["sugestoes"] if x["chave"] == "desempenho:2026-08:nmrr")
        assert s["origem"] == "desempenho" and "50%" in s["objetivo"]
        assert b["sugestoes_pendentes"] == len(b["sugestoes"])

    async def test_colaborador_ve_so_a_contagem(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        h = await _login(client, "jakeline@teste.com")
        b = await _pdi(client, h, hoje=HOJE)
        assert b["pode_gerir"] is False and b["pode_concluir"] is True
        assert b["sugestoes"] == [] and b["sugestoes_pendentes"] >= 1
        assert b["pessoas"] == [] and b["trilhas"] == []

    async def test_inicio_de_mes_olha_o_mes_anterior(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        b = await _pdi(client, agosto["h"], usuario_id=str(agosto["ev"]), hoje="2026-09-02")
        assert any(x["chave"] == "desempenho:2026-08:nmrr" for x in b["sugestoes"])

    async def test_confirmar_tira_a_sugestao_e_cria_a_acao(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        corpo = {"usuario_id": str(agosto["ev"]), "objetivo": "Dobrar o NMRR",
                 "o_que_fazer": "Revisar as propostas abertas toda segunda.", "prazo": _prazo(),
                 "chave_origem": "desempenho:2026-08:nmrr"}
        r = await client.post("/carreira/pdi/acoes", json=corpo, headers=agosto["h"])
        assert r.status_code == 201, r.text
        b = await _pdi(client, agosto["h"], usuario_id=str(agosto["ev"]), hoje=HOJE)
        assert not any(x["chave"] == "desempenho:2026-08:nmrr" for x in b["sugestoes"])
        a = b["acoes_abertas"][0]
        assert (a["objetivo"], a["origem"], a["origem_rotulo"]) == ("Dobrar o NMRR", "desempenho", "Desempenho")
        assert b["proxima"]["id"] == a["id"]
        de_novo = await client.post("/carreira/pdi/acoes", json=corpo, headers=agosto["h"])
        assert de_novo.status_code == 409

    async def test_descartar_nao_volta(self, agosto, client):  # noqa: F811
        await _meta(agosto["db"], "EV", agosto["ev"], "nmrr", 900)
        r = await client.post("/carreira/pdi/sugestoes/descartar",
                              json={"usuario_id": str(agosto["ev"]), "chave": "desempenho:2026-08:nmrr"},
                              headers=agosto["h"])
        assert r.status_code == 200, r.text
        b = await _pdi(client, agosto["h"], usuario_id=str(agosto["ev"]), hoje=HOJE)
        assert not any(x["chave"] == "desempenho:2026-08:nmrr" for x in b["sugestoes"])
        assert b["acoes_abertas"] == [] and b["acoes_feitas"] == []


class TestAcoes:
    async def _criar(self, client, agosto, **extra):
        corpo = {"usuario_id": str(agosto["ev"]), "objetivo": "Confirmar reuniões na véspera",
                 "o_que_fazer": "WhatsApp no dia útil anterior.", "prazo": _prazo(), **extra}
        r = await client.post("/carreira/pdi/acoes", json=corpo, headers=agosto["h"])
        assert r.status_code == 201, r.text
        return r.json()["acoes_abertas"][0]

    async def test_operacional_nao_cria(self, agosto, client):  # noqa: F811
        h = await _login(client, "jakeline@teste.com")
        r = await client.post("/carreira/pdi/acoes", headers=h, json={
            "usuario_id": str(agosto["ev"]), "objetivo": "x" * 5, "o_que_fazer": "y" * 5, "prazo": _prazo()})
        assert r.status_code == 403

    async def test_validacao_em_portugues(self, agosto, client):  # noqa: F811
        r = await client.post("/carreira/pdi/acoes", headers=agosto["h"], json={
            "usuario_id": str(agosto["ev"]), "objetivo": "", "o_que_fazer": "y" * 5, "prazo": _prazo()})
        assert r.status_code == 422 and "objetivo" in r.json()["detail"]
        r = await client.post("/carreira/pdi/acoes", headers=agosto["h"], json={
            "usuario_id": str(agosto["ev"]), "objetivo": "Ok ok", "o_que_fazer": "y" * 5,
            "prazo": _prazo(-1)})
        assert r.status_code == 422 and "passado" in r.json()["detail"]

    async def test_dono_marca_feita_e_desfaz(self, agosto, client):  # noqa: F811
        a = await self._criar(client, agosto)
        h = await _login(client, "jakeline@teste.com")
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=h,
                               json={"status": "concluida", "nota_conclusao": "Feito a semana toda."})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["acoes_abertas"] == [] and b["acoes_feitas"][0]["situacao"]["rotulo"] == "Feita"
        assert b["acoes_feitas"][0]["concluida_automatica"] is False
        assert b["resumo"]["feitas_no_mes"] == 1
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=h, json={"status": "aberta"})
        assert r.status_code == 200 and len(r.json()["acoes_abertas"]) == 1

    async def test_dono_nao_muda_prazo_nem_mexe_no_de_outro(self, agosto, client):  # noqa: F811
        a = await self._criar(client, agosto)
        h = await _login(client, "jakeline@teste.com")
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=h, json={"prazo": _prazo(40)})
        assert r.status_code == 403
        outro = await _login(client, "aline@teste.com")
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=outro, json={"status": "concluida"})
        assert r.status_code == 403

    async def test_gestao_edita_e_cancela(self, agosto, client):  # noqa: F811
        a = await self._criar(client, agosto)
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=agosto["h"],
                               json={"objetivo": "Novo objetivo", "prazo": _prazo(30)})
        assert r.status_code == 200 and r.json()["acoes_abertas"][0]["objetivo"] == "Novo objetivo"
        r = await client.patch(f"/carreira/pdi/acoes/{a['id']}", headers=agosto["h"], json={"status": "cancelada"})
        assert r.json()["acoes_feitas"][0]["situacao"]["codigo"] == "cancelada"

    async def test_acao_de_trilha_conclui_sozinha(self, agosto, client):  # noqa: F811
        db = agosto["db"]
        trilha = await db.fetchval(
            "INSERT INTO uc_trilhas (titulo, pilar, status) VALUES ('01 · Teste', 'tecnica', 'publicada') RETURNING id")
        aula = await db.fetchval(
            "INSERT INTO uc_aulas (trilha_id, ordem, titulo, status) VALUES ($1, 1, 'Única', 'publicada') RETURNING id",
            trilha)
        a = await self._criar(client, agosto, trilha_id=str(trilha))
        assert a["trilha"]["titulo"] == "01 · Teste"
        await db.execute(
            "INSERT INTO uc_progresso (usuario_id, aula_id, aula_versao, aberta_em, concluida_em) "
            "VALUES ($1, $2, 1, NOW() - interval '1 hour', NOW())", agosto["ev"], aula)
        b = await _pdi(client, agosto["h"], usuario_id=str(agosto["ev"]), hoje=HOJE)
        feita = b["acoes_feitas"][0]
        assert feita["id"] == a["id"] and feita["concluida_automatica"] is True
