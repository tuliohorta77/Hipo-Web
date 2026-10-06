"""
HIPO — Testes da entrega 045: contatos (ABM / multithreading).

  * o comitê da oportunidade: vários contatos, papel, um principal, e o
    espelho em oportunidades.contato_id
  * contato obrigatório nas tarefas de interação (criar, editar, próxima)
  * reunião da agenda e tarefa dizendo o mesmo contato
  * editar o contato (2º telefone, WhatsApp, LinkedIn) em vez de recriar
"""
import uuid
from datetime import datetime, timedelta

import pytest

from services import tarefa as regras
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_B = "34.028.316/0001-03"


def em(dias, hora=10):
    d = datetime.now(regras.FUSO_OPERACAO) + timedelta(days=dias)
    return d.replace(hour=hora, minute=0, second=0, microsecond=0).isoformat()


def proxima_segunda_as(hora):
    hoje = datetime.now(regras.FUSO_OPERACAO)
    dias = (7 - hoje.weekday()) % 7 or 7
    d = hoje + timedelta(days=dias + 7)
    return d.replace(hour=hora, minute=0, second=0, microsecond=0).isoformat()


async def nova_conta(client, h, cnpj=CNPJ_A, razao="Metalurgica Alfa LTDA"):
    r = await client.post("/crm/contas", json={"razao_social": razao, "cnpj": cnpj}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def novo_contato(client, h, conta_id=None, nome="Maria RH", **extra):
    corpo = {"nome": nome, **extra}
    if conta_id:
        corpo["conta_id"] = conta_id
    r = await client.post("/crm/contatos", json=corpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = await nova_conta(client, h)
    opp = (await client.post("/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h)).json()
    me = (await client.get("/auth/me", headers=h)).json()
    return {"h": h, "conta": conta, "opp": opp, "uid": me["id"], "conn": db_conn}


async def comite(client, h, opp_id):
    r = await client.get(f"/crm/oportunidades/{opp_id}/contatos", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def incluir(client, h, opp_id, contato_id, **extra):
    return await client.post(
        f"/crm/oportunidades/{opp_id}/contatos",
        json={"contato_id": contato_id, **extra}, headers=h,
    )


# ── O comitê ─────────────────────────────────────────────────────────

class TestComite:
    async def test_oportunidade_nova_comeca_sem_ninguem(self, cenario, client):
        c = await comite(client, cenario["h"], cenario["opp"]["id"])
        assert c["itens"] == []
        assert c["farol"]["nivel"] == "sem_contato"

    async def test_o_primeiro_vira_principal_e_espelho(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana Diretora")
        r = await incluir(client, h, opp, ana["id"], papel="decisor")
        assert r.status_code == 201, r.text
        item = r.json()["itens"][0]
        assert item["principal"] is True
        assert item["papel"] == "decisor"
        assert item["papel_rotulo"] == "Decisor"
        detalhe = (await client.get(f"/crm/oportunidades/{opp}", headers=h)).json()
        assert detalhe["contato_id"] == ana["id"]
        assert detalhe["qtd_contatos"] == 1
        assert detalhe["tem_decisor"] is True

    async def test_varios_contatos_e_farol_ideal(self, cenario, client):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        for nome, papel in (("Ana", "decisor"), ("Bia", "operacional"), ("Caio", "tecnico")):
            c = await novo_contato(client, h, conta, nome)
            assert (await incluir(client, h, opp, c["id"], papel=papel)).status_code == 201
        c = await comite(client, h, opp)
        assert len(c["itens"]) == 3
        assert c["farol"]["nivel"] == "ideal"
        assert c["farol"]["tem_decisor"] is True
        # Só um principal, e é o primeiro.
        assert [i["nome"] for i in c["itens"] if i["principal"]] == ["Ana"]

    async def test_trocar_principal_atualiza_o_espelho(self, cenario, client, db_conn):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        await incluir(client, h, opp, ana["id"])
        await incluir(client, h, opp, bia["id"])
        r = await client.patch(
            f"/crm/oportunidades/{opp}/contatos/{bia['id']}",
            json={"principal": True}, headers=h,
        )
        assert r.status_code == 200, r.text
        principais = [i["nome"] for i in r.json()["itens"] if i["principal"]]
        assert principais == ["Bia"]
        assert str(await db_conn.fetchval(
            "SELECT contato_id FROM oportunidades WHERE id = $1", uuid.UUID(opp)
        )) == bia["id"]

    async def test_desmarcar_principal_direto_e_recusado(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        await incluir(client, h, opp, ana["id"])
        r = await client.patch(
            f"/crm/oportunidades/{opp}/contatos/{ana['id']}",
            json={"principal": False}, headers=h,
        )
        assert r.status_code == 422

    async def test_papel_invalido_e_422(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        r = await incluir(client, h, opp, ana["id"], papel="chefao")
        assert r.status_code == 422

    async def test_duplicado_e_409(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        await incluir(client, h, opp, ana["id"])
        assert (await incluir(client, h, opp, ana["id"])).status_code == 409

    async def test_pessoa_de_fora_e_vinculada_a_conta(self, cenario, client):
        """Descobriu alguém no meio da negociação: entra na conta junto."""
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        solto = await novo_contato(client, h, None, "Davi Compras")
        r = await incluir(client, h, opp, solto["id"], papel="compras", cargo="Comprador")
        assert r.status_code == 201, r.text
        assert r.json()["itens"][0]["cargo"] == "Comprador"
        conta_det = (await client.get(f"/crm/contas/{conta}", headers=h)).json()
        assert solto["id"] in [c["id"] for c in conta_det["contatos"]]

    async def test_contato_inativo_e_recusado(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        await client.delete(f"/crm/contatos/{ana['id']}", headers=h)
        assert (await incluir(client, h, opp, ana["id"])).status_code == 422

    async def test_remover_o_principal_promove_o_proximo(self, cenario, client, db_conn):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        await incluir(client, h, opp, ana["id"])
        await incluir(client, h, opp, bia["id"])
        r = await client.delete(f"/crm/oportunidades/{opp}/contatos/{ana['id']}", headers=h)
        assert r.status_code == 200, r.text
        assert [i["nome"] for i in r.json()["itens"] if i["principal"]] == ["Bia"]
        assert str(await db_conn.fetchval(
            "SELECT contato_id FROM oportunidades WHERE id = $1", uuid.UUID(opp)
        )) == bia["id"]

    async def test_remover_o_ultimo_zera_o_espelho(self, cenario, client, db_conn):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        await incluir(client, h, opp, ana["id"])
        await client.delete(f"/crm/oportunidades/{opp}/contatos/{ana['id']}", headers=h)
        assert await db_conn.fetchval(
            "SELECT contato_id FROM oportunidades WHERE id = $1", uuid.UUID(opp)
        ) is None
        # O vínculo com a conta fica.
        conta_det = (await client.get(f"/crm/contas/{cenario['conta']['id']}", headers=h)).json()
        assert ana["id"] in [c["id"] for c in conta_det["contatos"]]

    async def test_criar_oportunidade_com_contato_ja_poe_no_comite(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        conta = await nova_conta(client, h)
        ana = await novo_contato(client, h, conta["id"], "Ana")
        opp = (await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "contato_id": ana["id"]}, headers=h,
        )).json()
        c = await comite(client, h, opp["id"])
        assert [(i["nome"], i["principal"]) for i in c["itens"]] == [("Ana", True)]

    async def test_patch_antigo_de_contato_continua_funcionando(self, cenario, client):
        """O seletor antigo (PATCH contato_id) põe a pessoa como principal."""
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        await incluir(client, h, opp, ana["id"])
        r = await client.patch(f"/crm/oportunidades/{opp}", json={"contato_id": bia["id"]}, headers=h)
        assert r.status_code == 200, r.text
        c = await comite(client, h, opp)
        assert {i["nome"]: i["principal"] for i in c["itens"]} == {"Ana": False, "Bia": True}

    async def test_lista_de_oportunidades_traz_o_farol(self, cenario, client):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        for nome in ("Ana", "Bia"):
            c = await novo_contato(client, h, conta, nome)
            await incluir(client, h, opp, c["id"])
        lista = (await client.get("/crm/oportunidades", headers=h)).json()
        linha = next(o for o in lista["itens"] if o["id"] == opp)
        assert linha["qtd_contatos"] == 2
        assert linha["tem_decisor"] is False

    async def test_oportunidade_inexistente_e_404(self, cenario, client):
        r = await client.get(f"/crm/oportunidades/{uuid.uuid4()}/contatos", headers=cenario["h"])
        assert r.status_code == 404


# ── Contato na tarefa ────────────────────────────────────────────────

def tarefa(opp, uid, **extra):
    return {
        "oportunidade_id": opp, "tipo": "ligacao", "titulo": "FUP",
        "responsavel_id": uid, "prazo": em(1), **extra,
    }


class TestTarefaComContato:
    async def test_ligacao_sem_contato_e_422(self, cenario, client):
        r = await client.post("/crm/tarefas", json=tarefa(cenario["opp"]["id"], cenario["uid"]),
                              headers=cenario["h"])
        assert r.status_code == 422
        assert "com quem" in r.json()["detail"]

    async def test_proposta_dispensa_contato(self, cenario, client):
        r = await client.post(
            "/crm/tarefas",
            json=tarefa(cenario["opp"]["id"], cenario["uid"], tipo="proposta"),
            headers=cenario["h"],
        )
        assert r.status_code == 201, r.text

    async def test_contato_da_conta_entra_no_comite(self, cenario, client):
        """Conversar com alguém é envolver a pessoa."""
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana", telefone="11999990000",
                                 telefone_whatsapp=True)
        r = await client.post("/crm/tarefas", json=tarefa(opp, cenario["uid"], contato_id=ana["id"]),
                              headers=h)
        assert r.status_code == 201, r.text
        t = r.json()
        assert t["contato_nome"] == "Ana"
        assert t["contato_telefone"] == "11999990000"
        assert t["contato_whatsapp"] is True
        c = await comite(client, h, opp)
        assert [(i["nome"], i["principal"]) for i in c["itens"]] == [("Ana", True)]

    async def test_contato_de_outra_empresa_e_422(self, cenario, client):
        h = cenario["h"]
        outra = await nova_conta(client, h, CNPJ_B, "Beta SA")
        estranho = await novo_contato(client, h, outra["id"], "Zé de Fora")
        r = await client.post(
            "/crm/tarefas",
            json=tarefa(cenario["opp"]["id"], cenario["uid"], contato_id=estranho["id"]),
            headers=h,
        )
        assert r.status_code == 422
        assert "não é da empresa" in r.json()["detail"]

    async def test_interacoes_contam_no_comite(self, cenario, client):
        h, opp, uid = cenario["h"], cenario["opp"]["id"], cenario["uid"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        a = (await client.post("/crm/tarefas", json=tarefa(opp, uid, contato_id=ana["id"]),
                               headers=h)).json()
        b = (await client.post("/crm/tarefas", json=tarefa(opp, uid, contato_id=ana["id"]),
                               headers=h)).json()
        assert (await client.post(f"/crm/tarefas/{a['id']}/concluir", json={}, headers=h)).status_code == 200
        item = (await comite(client, h, opp))["itens"][0]
        assert item["interacoes"] == 1
        assert item["ultima_interacao"] is not None
        assert b["id"]

    async def test_proxima_sem_contato_e_422_e_nada_muda(self, cenario, client, db_conn):
        h, opp, uid = cenario["h"], cenario["opp"]["id"], cenario["uid"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        t = (await client.post("/crm/tarefas", json=tarefa(opp, uid, contato_id=ana["id"]),
                               headers=h)).json()
        r = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": {"tipo": "whatsapp", "titulo": "Mandar material",
                              "responsavel_id": uid, "prazo": em(3)}},
            headers=h,
        )
        assert r.status_code == 422
        assert await db_conn.fetchval(
            "SELECT concluida_em FROM tarefas WHERE id = $1", uuid.UUID(t["id"])
        ) is None

    async def test_proxima_com_contato_grava(self, cenario, client):
        h, opp, uid = cenario["h"], cenario["opp"]["id"], cenario["uid"]
        conta = cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        t = (await client.post("/crm/tarefas", json=tarefa(opp, uid, contato_id=ana["id"]),
                               headers=h)).json()
        r = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": {"tipo": "ligacao", "titulo": "Falar com o DP",
                              "responsavel_id": uid, "prazo": em(3), "contato_id": bia["id"]}},
            headers=h,
        )
        assert r.status_code == 200, r.text
        prox = (await client.get(f"/crm/tarefas/{r.json()['proxima_id']}", headers=h)).json()
        assert prox["contato_nome"] == "Bia"
        assert len((await comite(client, h, opp))["itens"]) == 2

    async def test_editar_so_o_prazo_de_tarefa_antiga_sem_contato_passa(self, cenario, client, db_conn):
        """Tarefa antiga aberta não trava enquanto ninguém mexe em tipo/contato."""
        h, opp, uid = cenario["h"], cenario["opp"]["id"], cenario["uid"]
        tid = await db_conn.fetchval(
            """
            INSERT INTO tarefas (oportunidade_id, tipo, titulo, responsavel_id, prazo)
            VALUES ($1, 'ligacao', 'Antiga', $2, NOW() + interval '1 day') RETURNING id
            """,
            uuid.UUID(opp), uuid.UUID(uid),
        )
        r = await client.patch(f"/crm/tarefas/{tid}", json={"prazo": em(5)}, headers=h)
        assert r.status_code == 200, r.text
        # Pelo formulário (que manda o tipo) passa a pedir o contato.
        r = await client.patch(f"/crm/tarefas/{tid}", json={"tipo": "ligacao", "titulo": "Antiga"}, headers=h)
        assert r.status_code == 422

    async def test_concluir_tarefa_antiga_sem_contato_nao_trava(self, cenario, client, db_conn):
        h, opp, uid = cenario["h"], cenario["opp"]["id"], cenario["uid"]
        ids = []
        for _ in range(2):
            ids.append(await db_conn.fetchval(
                """
                INSERT INTO tarefas (oportunidade_id, tipo, titulo, responsavel_id, prazo)
                VALUES ($1, 'ligacao', 'Antiga', $2, NOW()) RETURNING id
                """,
                uuid.UUID(opp), uuid.UUID(uid),
            ))
        r = await client.post(f"/crm/tarefas/{ids[0]}/concluir", json={}, headers=h)
        assert r.status_code == 200, r.text

    async def test_trocar_contato_pela_edicao(self, cenario, client):
        h, opp, uid, conta = cenario["h"], cenario["opp"]["id"], cenario["uid"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        t = (await client.post("/crm/tarefas", json=tarefa(opp, uid, contato_id=ana["id"]),
                               headers=h)).json()
        r = await client.patch(f"/crm/tarefas/{t['id']}", json={"contato_id": bia["id"]}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["contato_nome"] == "Bia"
        r = await client.patch(f"/crm/tarefas/{t['id']}", json={"contato_id": None}, headers=h)
        assert r.status_code == 422

    async def test_tarefa_de_parceiro_exige_contato_do_parceiro(self, cenario, client, db_conn):
        h, uid = cenario["h"], cenario["uid"]
        parceiro = await nova_conta(client, h, CNPJ_B, "Contabil Beta")
        await db_conn.execute("UPDATE contas SET eh_finder = TRUE WHERE id = $1", uuid.UUID(parceiro["id"]))
        base = {"conta_id": parceiro["id"], "tipo": "visita", "titulo": "Café",
                "responsavel_id": uid, "prazo": em(2)}
        assert (await client.post("/crm/tarefas", json=base, headers=h)).status_code == 422
        do_cliente = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        r = await client.post("/crm/tarefas", json={**base, "contato_id": do_cliente["id"]}, headers=h)
        assert r.status_code == 422
        contador = await novo_contato(client, h, parceiro["id"], "Carlos Contador")
        r = await client.post("/crm/tarefas", json={**base, "contato_id": contador["id"]}, headers=h)
        assert r.status_code == 201, r.text

    async def test_registro_do_fechamento_nao_exige_contato(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        r = await client.post(
            f"/crm/oportunidades/{opp}/desfecho",
            json={"status": "conquistado",
                  "tarefa": {"tipo": "reuniao", "titulo": "Fechamento"}},
            headers=h,
        )
        assert r.status_code == 200, r.text


# ── Agenda ───────────────────────────────────────────────────────────

class TestAgendaComContato:
    async def test_reuniao_sem_contato_e_422(self, cenario, client):
        r = await client.post(
            "/crm/agenda/reunioes",
            json={"oportunidade_id": cenario["opp"]["id"], "anfitriao_id": cenario["uid"],
                  "inicio": proxima_segunda_as(9)},
            headers=cenario["h"],
        )
        assert r.status_code == 422

    async def test_reuniao_grava_o_contato_na_tarefa_e_no_comite(self, cenario, client, db_conn):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        r = await client.post(
            "/crm/agenda/reunioes",
            json={"oportunidade_id": opp, "anfitriao_id": cenario["uid"],
                  "inicio": proxima_segunda_as(9), "contato_id": ana["id"]},
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert str(await db_conn.fetchval(
            "SELECT contato_id FROM tarefas WHERE id = $1", uuid.UUID(r.json()["tarefa_id"])
        )) == ana["id"]
        assert len((await comite(client, h, opp))["itens"]) == 1

    async def test_trocar_contato_pela_agenda_troca_na_tarefa(self, cenario, client, db_conn):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        r = (await client.post(
            "/crm/agenda/reunioes",
            json={"oportunidade_id": opp, "anfitriao_id": cenario["uid"],
                  "inicio": proxima_segunda_as(9), "contato_id": ana["id"]},
            headers=h,
        )).json()
        e = await client.patch(f"/crm/agenda/reunioes/{r['id']}", json={"contato_id": bia["id"]}, headers=h)
        assert e.status_code == 200, e.text
        assert str(await db_conn.fetchval(
            "SELECT contato_id FROM tarefas WHERE id = $1", uuid.UUID(r["tarefa_id"])
        )) == bia["id"]
        tira = await client.patch(f"/crm/agenda/reunioes/{r['id']}", json={"contato_id": None}, headers=h)
        assert tira.status_code == 422

    async def test_trocar_contato_pela_tarefa_troca_na_reuniao(self, cenario, client, db_conn):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        bia = await novo_contato(client, h, conta, "Bia")
        r = (await client.post(
            "/crm/agenda/reunioes",
            json={"oportunidade_id": opp, "anfitriao_id": cenario["uid"],
                  "inicio": proxima_segunda_as(9), "contato_id": ana["id"]},
            headers=h,
        )).json()
        e = await client.patch(f"/crm/tarefas/{r['tarefa_id']}", json={"contato_id": bia["id"]}, headers=h)
        assert e.status_code == 200, e.text
        assert str(await db_conn.fetchval(
            "SELECT contato_id FROM reunioes WHERE id = $1", uuid.UUID(r["id"])
        )) == bia["id"]

    async def test_colocar_na_agenda_herda_o_contato_da_tarefa(self, cenario, client):
        h, opp = cenario["h"], cenario["opp"]["id"]
        ana = await novo_contato(client, h, cenario["conta"]["id"], "Ana")
        t = (await client.post(
            "/crm/tarefas",
            json=tarefa(opp, cenario["uid"], tipo="reuniao", prazo=proxima_segunda_as(14),
                        contato_id=ana["id"]),
            headers=h,
        )).json()
        r = await client.post(f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h)
        assert r.status_code == 201, r.text
        assert r.json()["contato_id"] == ana["id"]


# ── Editar o contato ─────────────────────────────────────────────────

class TestEditarContato:
    async def test_troca_telefone_sem_recriar(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await novo_contato(client, h, None, "Ana", telefone="1111-1111")
        r = await client.patch(
            f"/crm/contatos/{c['id']}",
            json={"telefone": "11 98888-7777", "telefone_whatsapp": True,
                  "telefone_2": "11 3333-4444", "linkedin": "linkedin.com/in/ana"},
            headers=h,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == c["id"]
        assert d["telefone"] == "11 98888-7777"
        assert d["telefone_whatsapp"] is True
        assert d["telefone_2"] == "11 3333-4444"
        assert d["telefone_2_whatsapp"] is False
        assert d["linkedin"] == "https://linkedin.com/in/ana"

    async def test_linkedin_que_nao_e_linkedin_e_422(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await novo_contato(client, h, None, "Ana")
        r = await client.patch(f"/crm/contatos/{c['id']}", json={"linkedin": "meusite.com"}, headers=h)
        assert r.status_code == 422

    async def test_whatsapp_nulo_vira_falso(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await novo_contato(client, h, None, "Ana", telefone_whatsapp=True)
        r = await client.patch(f"/crm/contatos/{c['id']}", json={"telefone_whatsapp": None}, headers=h)
        assert r.status_code == 200
        assert r.json()["telefone_whatsapp"] is False

    async def test_duplicata_olha_o_segundo_telefone(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        await novo_contato(client, h, None, "Ana", telefone_2="11977776666")
        r = await client.get("/crm/contatos/duplicatas", params={"telefone": "11977776666"}, headers=h)
        assert [d["nome"] for d in r.json()] == ["Ana"]

    async def test_ficha_da_conta_traz_os_campos_novos(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        conta = await nova_conta(client, h)
        await novo_contato(client, h, conta["id"], "Ana", telefone_2="1199", linkedin="https://www.linkedin.com/in/ana")
        det = (await client.get(f"/crm/contas/{conta['id']}", headers=h)).json()
        assert det["contatos"][0]["telefone_2"] == "1199"
        assert det["contatos"][0]["linkedin"] == "https://www.linkedin.com/in/ana"


class TestPorAlvo:
    async def test_comite_primeiro_depois_a_empresa(self, cenario, client):
        h, opp, conta = cenario["h"], cenario["opp"]["id"], cenario["conta"]["id"]
        await novo_contato(client, h, conta, "Aaron Fora")
        bia = await novo_contato(client, h, conta, "Bia")
        caio = await novo_contato(client, h, conta, "Caio")
        await incluir(client, h, opp, caio["id"])          # principal
        await incluir(client, h, opp, bia["id"], papel="decisor")
        r = await client.get("/crm/contatos/por-alvo", params={"oportunidade_id": opp}, headers=h)
        assert r.status_code == 200, r.text
        assert [(c["nome"], c["no_comite"]) for c in r.json()] == [
            ("Caio", True), ("Bia", True), ("Aaron Fora", False),
        ]

    async def test_inativo_nao_aparece(self, cenario, client):
        h, conta = cenario["h"], cenario["conta"]["id"]
        ana = await novo_contato(client, h, conta, "Ana")
        await client.delete(f"/crm/contatos/{ana['id']}", headers=h)
        r = await client.get("/crm/contatos/por-alvo", params={"conta_id": conta}, headers=h)
        assert r.json() == []

    async def test_exige_um_alvo_so(self, cenario, client):
        h = cenario["h"]
        assert (await client.get("/crm/contatos/por-alvo", headers=h)).status_code == 422
        r = await client.get(
            "/crm/contatos/por-alvo",
            params={"oportunidade_id": cenario["opp"]["id"], "conta_id": cenario["conta"]["id"]},
            headers=h,
        )
        assert r.status_code == 422


class TestPermissao:
    async def test_sdr_monta_o_comite(self, cenario, client, db_conn):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-045@teste.com")
        ana = await novo_contato(client, sdr["headers"], cenario["conta"]["id"], "Ana")
        r = await incluir(client, sdr["headers"], cenario["opp"]["id"], ana["id"])
        assert r.status_code == 201, r.text
