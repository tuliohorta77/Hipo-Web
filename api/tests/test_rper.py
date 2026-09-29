"""
HIPO — Testes do router /rper (o PPT da Reuniao de Planejamento e
Resultados) e das metas por squad e por pessoa.

As regras puras estao em test_rper_regras.py. Aqui o que so aparece com
banco: a coleta de cada linha no mes certo e no fuso da operacao, as metas
com as duas unicidades parciais, e a guarda de gestao.

Os dados sao gravados por SQL direto em agosto/2026 (mes fechado fixo),
para o teste nao depender do dia em que o CI roda.
"""
from datetime import datetime
from io import BytesIO

import pytest

from services.tarefa import FUSO_OPERACAO
from tests.conftest import criar_usuario


def em(dia: int, hora: int = 10, mes: int = 8) -> datetime:
    return datetime(2026, mes, dia, hora, tzinfo=FUSO_OPERACAO)


async def _id(db, email):
    return await db.fetchval("SELECT id FROM usuarios WHERE email = $1", email)


@pytest.fixture
async def time(db_conn, client, usuario_franqueado):
    await criar_usuario(db_conn, client, "SDR", "kethlleen@teste.com")
    await criar_usuario(db_conn, client, "EV", "jakeline@teste.com")
    await criar_usuario(db_conn, client, "EC", "aline@teste.com")
    await db_conn.execute("UPDATE usuarios SET nome = 'Kethlleen Gomes' WHERE email = 'kethlleen@teste.com'")
    await db_conn.execute("UPDATE usuarios SET nome = 'Jakeline Santana' WHERE email = 'jakeline@teste.com'")
    await db_conn.execute("UPDATE usuarios SET nome = 'Aline Martins' WHERE email = 'aline@teste.com'")
    return {
        "h": usuario_franqueado["headers"],
        "sdr": await _id(db_conn, "kethlleen@teste.com"),
        "ev": await _id(db_conn, "jakeline@teste.com"),
        "ec": await _id(db_conn, "aline@teste.com"),
        "db": db_conn,
    }


async def _conta(db, cnpj, razao, **extra):
    colunas = ["razao_social", "cnpj"] + list(extra)
    valores = [razao, cnpj] + list(extra.values())
    marcas = ", ".join(f"${i + 1}" for i in range(len(valores)))
    return await db.fetchval(
        f"INSERT INTO contas ({', '.join(colunas)}) VALUES ({marcas}) RETURNING id",
        *valores,
    )


async def _opp(db, conta, numero, *, fase="negociacao", status="ativa", valor=None,
               envolvidos=(), finder=None, criado_em=None):
    fase_desfecho = None
    if status != "ativa":
        fase, fase_desfecho = "finalizado", "negociacao"
    oid = await db.fetchval(
        """
        INSERT INTO oportunidades (numero, conta_id, fase, status, fase_desfecho,
                                   valor_mensalidade, temperatura, finder_conta_id,
                                   criado_em)
        VALUES ($1, $2, $3, $4, $5, $6, 50, $7, COALESCE($8, NOW()))
        RETURNING id
        """,
        numero, conta, fase, status, fase_desfecho, valor, finder, criado_em,
    )
    for uid, papel in envolvidos:
        await db.execute(
            "INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel) "
            "VALUES ($1, $2, $3)", oid, uid, papel,
        )
    return oid


async def _tarefa(db, *, resp, prazo, opp=None, conta=None, concluida=None, tipo="ligacao"):
    return await db.fetchval(
        """
        INSERT INTO tarefas (oportunidade_id, conta_id, tipo, titulo, responsavel_id,
                             prazo, concluida_em)
        VALUES ($1, $2, $3, 'Tarefa', $4, $5, $6) RETURNING id
        """,
        opp, conta, tipo, resp, prazo, concluida,
    )


async def _reuniao(db, *, anfitriao, agendado_por, inicio, criado_em, opp=None,
                   conta=None, desfecho=None):
    t = await _tarefa(db, resp=anfitriao, prazo=inicio, opp=opp, conta=conta, tipo="reuniao")
    await db.execute(
        """
        INSERT INTO reunioes (tarefa_id, agendado_por, desfecho, desfecho_em, criado_em)
        VALUES ($1, $2, $3, $4, $5)
        """,
        t, agendado_por, desfecho, criado_em if desfecho else None, criado_em,
    )


@pytest.fixture
async def agosto(time):
    """Um mes de agosto pequeno, com uma linha de cada coisa que o RPeR conta."""
    db = time["db"]
    cliente = await _conta(db, "11222333000181", "Metalurgica Alfa LTDA")
    parceiro = await _conta(db, "11444777000161", "Contabilidade Beta LTDA",
                            eh_finder=True, ec_responsavel_id=time["ec"])
    negociando = await _opp(db, cliente, "OPP-1", valor=1200,
                            envolvidos=[(time["ev"], "EV"), (time["sdr"], "SDR")])
    ganha = await _opp(db, cliente, "OPP-2", status="conquistado", valor=450,
                       envolvidos=[(time["ev"], "EV"), (time["ec"], "EC")])
    await db.execute(
        "INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para, usuario_id, criado_em) "
        "VALUES ($1, 'status', 'ativa', 'conquistado', $2, $3)", ganha, time["ev"], em(20),
    )
    # Ganho registrado em setembro NAO entra no RPeR de agosto.
    fora = await _opp(db, cliente, "OPP-3", status="conquistado", valor=9999,
                      envolvidos=[(time["ev"], "EV")])
    await db.execute(
        "INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para, usuario_id, criado_em) "
        "VALUES ($1, 'status', 'ativa', 'conquistado', $2, $3)", fora, time["ev"], em(2, mes=9),
    )
    await db.execute(
        "INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para, usuario_id, criado_em) "
        "VALUES ($1, 'fase', 'suspect', 'lead', $2, $3)", negociando, time["sdr"], em(5),
    )
    # Reunioes de cliente agendadas pelo SDR, conduzidas pelo EV.
    await _reuniao(db, anfitriao=time["ev"], agendado_por=time["sdr"], inicio=em(12),
                   criado_em=em(4), opp=negociando, desfecho="realizada")
    await _reuniao(db, anfitriao=time["ev"], agendado_por=time["sdr"], inicio=em(14),
                   criado_em=em(4), opp=negociando, desfecho="no_show")
    # 31/08 as 23h em Brasilia e 01/09 em UTC: tem que contar em AGOSTO.
    await _reuniao(db, anfitriao=time["ev"], agendado_por=time["sdr"], inicio=em(31, hora=23),
                   criado_em=em(31, hora=23), opp=negociando, desfecho="realizada")
    # Reuniao de parceiro, do EC.
    await _reuniao(db, anfitriao=time["ec"], agendado_por=time["ec"], inicio=em(18),
                   criado_em=em(10), conta=parceiro, desfecho="realizada")
    # Tarefas do SDR: uma feita, uma nao.
    await _tarefa(db, resp=time["sdr"], prazo=em(6), opp=negociando, concluida=em(6))
    await _tarefa(db, resp=time["sdr"], prazo=em(7), opp=negociando)
    await db.execute(
        "INSERT INTO propostas (oportunidade_id, versao, vidas, valor_por_vida, escopo, "
        "data_proposta, validade, cliente_razao_social, executivo_id, executivo_nome, "
        "executivo_email, criado_em) VALUES ($1, 1, 10, 30, '[\"PGR\"]', '2026-08-15', "
        "'2026-09-15', 'Metalurgica Alfa LTDA', $2, 'Jakeline', 'j@t.com', $3)",
        negociando, time["ev"], em(15),
    )
    await db.execute(
        "INSERT INTO parceiro_eventos (conta_id, tipo, para_usuario_id, usuario_id, criado_em) "
        "VALUES ($1, 'atribuido', $2, $2, $3)", parceiro, time["ec"], em(3),
    )
    await _opp(db, cliente, "OPP-4", fase="lead", finder=parceiro, criado_em=em(22))
    return time


def _indicador(squad, chave):
    return next(l for l in squad["total"] if l["chave"] == chave)


async def _previa(client, h):
    resp = await client.get("/rper/previa", params={"ano": 2026, "mes": 8}, headers=h)
    assert resp.status_code == 200, resp.text
    return {s["squad"]: s for s in resp.json()["squads"]}


class TestPrevia:
    async def test_sdr(self, agosto, client):
        sdr = (await _previa(client, agosto["h"]))["SDR"]
        assert _indicador(sdr, "agendamentos")["realizado"] == 3
        assert _indicador(sdr, "reunioes_realizadas")["realizado"] == 2
        assert _indicador(sdr, "noshow")["realizado"] == 33.3
        assert _indicador(sdr, "leads")["realizado"] == 1
        assert _indicador(sdr, "tarefas")["realizado"] == 2
        assert _indicador(sdr, "contas")["realizado"] == 1
        assert _indicador(sdr, "pipeline_gerado")["realizado"] == 1200
        # O SDR esta envolvido so na oportunidade que ainda negocia.
        assert _indicador(sdr, "nmrr")["realizado"] == 0

    async def test_ev(self, agosto, client):
        ev = (await _previa(client, agosto["h"]))["EV"]
        assert _indicador(ev, "vendas")["realizado"] == 1
        assert _indicador(ev, "nmrr")["realizado"] == 450
        assert _indicador(ev, "reunioes_realizadas")["realizado"] == 2
        assert _indicador(ev, "propostas")["realizado"] == 1
        assert _indicador(ev, "em_negociacao")["realizado"] == 1
        assert _indicador(ev, "pipeline")["realizado"] == 1200
        assert _indicador(ev, "taxa_conversao")["realizado"] == 50.0

    async def test_ec(self, agosto, client):
        ec = (await _previa(client, agosto["h"]))["EC"]
        assert _indicador(ec, "contas_gestao")["realizado"] == 1
        assert _indicador(ec, "reunioes_carteira")["realizado"] == 1
        assert _indicador(ec, "parcerias")["realizado"] == 1
        assert _indicador(ec, "leads")["realizado"] == 1
        # MRR = vendas do mes com o EC envolvido.
        assert _indicador(ec, "mrr")["realizado"] == 450

    async def test_sem_parametro_e_o_mes_anterior(self, time, client):
        resp = await client.get("/rper/previa", headers=time["h"])
        assert resp.status_code == 200
        hoje = datetime.now(FUSO_OPERACAO).date()
        esperado = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
        assert (resp.json()["ano"], resp.json()["mes"]) == esperado

    async def test_ano_sem_mes_e_422(self, time, client):
        resp = await client.get("/rper/previa", params={"ano": 2026}, headers=time["h"])
        assert resp.status_code == 422


class TestArquivo:
    async def test_gera_o_pptx(self, agosto, client):
        resp = await client.get(
            "/rper/arquivo", params={"ano": 2026, "mes": 8, "ia": "false"},
            headers=agosto["h"],
        )
        assert resp.status_code == 200, resp.text
        assert "RPeR_SETEMBRO_2026_CONTROLLER_MEDSEG.pptx" in resp.headers["content-disposition"]
        assert resp.headers["x-rper-ia"] == "0"
        from pptx import Presentation
        prs = Presentation(BytesIO(resp.content))
        assert len(prs.slides) == 15

    async def test_formato_invalido_e_422(self, time, client):
        resp = await client.get("/rper/arquivo", params={"formato": "docx"}, headers=time["h"])
        assert resp.status_code == 422


class TestPermissao:
    @pytest.mark.parametrize("rota", ["/rper/status", "/rper/previa", "/rper/arquivo", "/rper/metas"])
    async def test_operacional_nao_ve(self, db_conn, client, rota):
        ev = await criar_usuario(db_conn, client, "EV", "ev-rper@teste.com")
        resp = await client.get(rota, headers=ev["headers"])
        assert resp.status_code == 403

    async def test_adm_ve(self, usuario_adm, client):
        resp = await client.get("/rper/status", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        corpo = resp.json()
        assert {"pptx_disponivel", "pdf_disponivel", "ia_configurada"} <= set(corpo)


# ── Metas ────────────────────────────────────────────────────────────

async def _gravar(client, h, metas, ano=2026, mes=9):
    return await client.put("/rper/metas", json={"ano": ano, "mes": mes, "metas": metas},
                            headers=h)


class TestMetas:
    async def test_grade_completa_mesmo_sem_meta(self, time, client):
        resp = await client.get("/rper/metas", params={"ano": 2026, "mes": 9}, headers=time["h"])
        assert resp.status_code == 200
        squads = {s["squad"]: s for s in resp.json()["squads"]}
        assert set(squads) == {"EC", "SDR", "EV"}
        assert squads["SDR"]["squad_metas"]["agendamentos"] is None
        assert [p["nome"] for p in squads["SDR"]["pessoas"]] == ["Kethlleen Gomes"]

    async def test_squad_e_pessoa_convivem(self, time, client):
        """A meta do squad NAO e a soma: as duas ficam gravadas lado a lado."""
        resp = await _gravar(client, time["h"], [
            {"squad": "SDR", "indicador": "agendamentos", "valor": 90},
            {"squad": "SDR", "usuario_id": str(time["sdr"]), "indicador": "agendamentos",
             "valor": 40},
        ])
        assert resp.status_code == 200, resp.text
        sdr = next(s for s in resp.json()["squads"] if s["squad"] == "SDR")
        assert sdr["squad_metas"]["agendamentos"] == 90
        assert sdr["pessoas"][0]["metas"]["agendamentos"] == 40

        # Regravar atualiza, nao duplica.
        await _gravar(client, time["h"], [
            {"squad": "SDR", "indicador": "agendamentos", "valor": 95},
        ])
        n = await time["db"].fetchval("SELECT count(*) FROM metas_comerciais")
        assert n == 2

    async def test_null_apaga(self, time, client):
        await _gravar(client, time["h"], [{"squad": "EV", "indicador": "nmrr", "valor": 7200}])
        await _gravar(client, time["h"], [{"squad": "EV", "indicador": "nmrr", "valor": None}])
        assert await time["db"].fetchval("SELECT count(*) FROM metas_comerciais") == 0

    async def test_indicador_de_outro_squad_e_422(self, time, client):
        resp = await _gravar(client, time["h"], [
            {"squad": "SDR", "indicador": "pipeline", "valor": 1},
        ])
        assert resp.status_code == 422

    async def test_meta_de_pessoa_de_outro_cargo_e_422(self, time, client):
        resp = await _gravar(client, time["h"], [
            {"squad": "EV", "usuario_id": str(time["sdr"]), "indicador": "nmrr", "valor": 1},
        ])
        assert resp.status_code == 422
        assert "SDR" in resp.json()["detail"]

    async def test_operacional_nao_grava(self, time, db_conn, client):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-meta@teste.com")
        resp = await _gravar(client, sdr["headers"], [
            {"squad": "SDR", "indicador": "agendamentos", "valor": 999},
        ])
        assert resp.status_code == 403

    async def test_copiar_nao_sobrescreve(self, time, client):
        await _gravar(client, time["h"], [
            {"squad": "EV", "indicador": "nmrr", "valor": 7200},
            {"squad": "EV", "usuario_id": str(time["ev"]), "indicador": "nmrr", "valor": 5000},
            {"squad": "EV", "indicador": "vendas", "valor": 24},
        ], mes=8)
        await _gravar(client, time["h"], [{"squad": "EV", "indicador": "nmrr", "valor": 8000}])
        resp = await client.post("/rper/metas/copiar", params={"ano": 2026, "mes": 9},
                                 headers=time["h"])
        assert resp.status_code == 200
        ev = next(s for s in resp.json()["squads"] if s["squad"] == "EV")
        assert ev["squad_metas"]["nmrr"] == 8000
        assert ev["squad_metas"]["vendas"] == 24
        assert ev["pessoas"][0]["metas"]["nmrr"] == 5000

    async def test_metas_aparecem_na_previa(self, agosto, client):
        await _gravar(client, agosto["h"], [
            {"squad": "EV", "indicador": "nmrr", "valor": 900},
        ], mes=8)
        ev = (await _previa(client, agosto["h"]))["EV"]
        nmrr = _indicador(ev, "nmrr")
        assert nmrr["meta"] == 900
        assert nmrr["atingimento_txt"] == "50%"
