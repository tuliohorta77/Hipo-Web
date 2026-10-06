"""
HIPO — Confirmação da véspera criada pela agenda (029).

O roteiro de vendas manda quem agendou confirmar a reunião por WhatsApp
no dia útil anterior. A agenda abre essa tarefa sozinha e a mantém de
acordo com a reunião:

  * nasce ao marcar numa oportunidade com dois dias úteis de folga
  * é de quem AGENDOU, com o contato da reunião e a mensagem pronta
  * remarcou -> muda de dia (ou é cancelada, se não sobrou folga)
  * reunião cancelada ou com desfecho -> é cancelada
  * não conta como próximo passo da oportunidade

As reuniões ficam DUAS semanas à frente: com uma, a suíte rodada numa
sexta marcaria para segunda sem folga, e o teste mudaria de resultado
conforme o dia. O caso sem folga fixa o relógio pelo `_agora` do router.
"""
from datetime import datetime, timedelta

import pytest

import routers.crm_agenda as crm_agenda
from services import agenda as regras
from tests.conftest import contato_do_alvo, contato_para_proxima, criar_usuario
from tests.test_crm_agenda import (  # noqa: F401  (cenario é fixture)
    as_horas, cenario, nova_reuniao, novo_parceiro, proxima_segunda,
)

SP = regras.FUSO_OPERACAO


def segunda():
    return proxima_segunda(2)


async def confirmacoes(db_conn, tarefa_reuniao_id):
    return await db_conn.fetch(
        """
        SELECT * FROM tarefas WHERE confirmacao_de = $1 ORDER BY criado_em
        """,
        tarefa_reuniao_id,
    )


def fixar_relogio(monkeypatch, quando: datetime):
    monkeypatch.setattr(crm_agenda, "_agora", lambda: quando)


async def id_de(client, usuario):
    return (await client.get("/auth/me", headers=usuario["headers"])).json()["id"]


class TestNasce:
    async def test_marcar_cria_a_confirmacao_na_vespera(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        terca = segunda() + timedelta(days=1)
        r = await nova_reuniao(client, h, opp, uid, inicio=as_horas(terca, 10, 30))

        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["tipo"] == "whatsapp"
        assert str(c["oportunidade_id"]) == opp
        assert str(c["responsavel_id"]) == uid
        assert str(c["contato_id"]) == cenario["contato_id"]
        assert c["prazo"] == datetime(
            segunda().year, segunda().month, segunda().day, 9, 0, tzinfo=SP
        )
        assert c["concluida_em"] is None and c["cancelada_em"] is None
        assert "tudo certo para amanhã às 10:30" in c["descricao"]
        assert c["titulo"].startswith(f"Confirmar reunião {terca.strftime('%d/%m')} 10:30")

    async def test_e_de_quem_agendou_e_nao_do_anfitriao(self, cenario, client, db_conn):
        opp, uid = cenario["oportunidade"]["id"], cenario["usuario_id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-conf@teste.com")
        sdr_id = await id_de(client, sdr)
        r = await nova_reuniao(
            client, sdr["headers"], opp, uid,
            inicio=as_horas(segunda() + timedelta(days=2), 9),
        )
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert str(c["responsavel_id"]) == sdr_id
        assert str(c["criado_por"]) == sdr_id
        # O nome do EV vai na mensagem.
        assert "com Test?" in c["descricao"]

    async def test_agendado_por_informado_e_o_dono(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-cred@teste.com")
        sdr_id = await id_de(client, sdr)
        r = await nova_reuniao(
            client, h, opp, uid, agendado_por=sdr_id,
            inicio=as_horas(segunda() + timedelta(days=2), 9),
        )
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert str(c["responsavel_id"]) == sdr_id

    async def test_segunda_confirma_na_sexta_dizendo_o_dia(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid, inicio=as_horas(segunda(), 14))
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        sexta = segunda() - timedelta(days=3)
        assert c["prazo"].astimezone(SP).date() == sexta
        assert "tudo certo para segunda às 14:00" in c["descricao"]

    async def test_pula_o_dia_sem_expediente(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await db_conn.execute(
            "INSERT INTO dia_nao_util (data, motivo) VALUES ($1, 'Feriado')", segunda()
        )
        terca = segunda() + timedelta(days=1)
        r = await nova_reuniao(client, h, opp, uid, inicio=as_horas(terca, 9))
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["prazo"].astimezone(SP).date() == segunda() - timedelta(days=3)

    async def test_sem_dois_dias_uteis_nao_cria(self, cenario, client, db_conn, monkeypatch):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        fixar_relogio(monkeypatch, datetime.combine(
            segunda(), datetime.min.time(), tzinfo=SP
        ).replace(hour=8))
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 10)
        )
        assert await confirmacoes(db_conn, r["tarefa_id"]) == []

    async def test_colocar_tarefa_na_agenda_tambem_cria(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = (await client.post("/crm/tarefas", json={
            "oportunidade_id": opp, "tipo": "reuniao", "titulo": "Apresentar",
            "responsavel_id": uid, "contato_id": cenario["contato_id"],
            "prazo": as_horas(segunda() + timedelta(days=3), 15),
        }, headers=h)).json()
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        assert resp.status_code == 201, resp.text
        assert len(await confirmacoes(db_conn, t["id"])) == 1

    async def test_reuniao_com_parceiro_nao_cria(self, cenario, client, db_conn):
        h, uid = cenario["headers"], cenario["usuario_id"]
        parceiro = await novo_parceiro(client, h)
        resp = await client.post("/crm/agenda/reunioes", json={
            "conta_id": parceiro["id"], "anfitriao_id": uid,
            "contato_id": await contato_do_alvo(client, h, conta_id=parceiro["id"]),
            "inicio": as_horas(segunda() + timedelta(days=2), 11),
        }, headers=h)
        assert resp.status_code == 201, resp.text
        assert await confirmacoes(db_conn, resp.json()["tarefa_id"]) == []


class TestAcompanhaAReuniao:
    async def test_remarcar_move_a_confirmacao(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        [antes] = await confirmacoes(db_conn, r["tarefa_id"])
        quinta = segunda() + timedelta(days=3)
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"inicio": as_horas(quinta, 16)}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [depois] = await confirmacoes(db_conn, r["tarefa_id"])
        assert depois["id"] == antes["id"]
        assert depois["prazo"].astimezone(SP).date() == quinta - timedelta(days=1)
        assert "amanhã às 16:00" in depois["descricao"]

    async def test_remarcar_pela_tarefa_tambem_move(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        quarta = segunda() + timedelta(days=2)
        resp = await client.patch(
            f"/crm/tarefas/{r['tarefa_id']}",
            json={"prazo": as_horas(quarta, 11)}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["prazo"].astimezone(SP).date() == quarta - timedelta(days=1)

    async def test_remarcar_sem_folga_cancela(self, cenario, client, db_conn, monkeypatch):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=3), 9)
        )
        # Na segunda de manhã o cliente pede para antecipar para terça.
        fixar_relogio(monkeypatch, datetime.combine(
            segunda(), datetime.min.time(), tzinfo=SP
        ).replace(hour=8))
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"inicio": as_horas(segunda() + timedelta(days=1), 9)}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["cancelada_em"] is not None
        assert c["motivo_cancelamento"] == crm_agenda.MOTIVO_CONFIRMACAO_SEM_FOLGA

    async def test_remarcar_depois_de_confirmada_abre_outra(self, cenario, client, db_conn):
        """O cliente confirmou e, na mesma conversa, pediu para a semana seguinte."""
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert (await client.post(
            f"/crm/tarefas/{c['id']}/concluir", json={"resultado": "pediu outra semana"},
            headers=h,
        )).status_code == 200
        nova_data = segunda() + timedelta(days=8)
        assert (await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"inicio": as_horas(nova_data, 10)}, headers=h,
        )).status_code == 200
        primeira, segunda_conf = await confirmacoes(db_conn, r["tarefa_id"])
        assert primeira["concluida_em"] is not None
        assert segunda_conf["concluida_em"] is None and segunda_conf["cancelada_em"] is None
        assert segunda_conf["prazo"].astimezone(SP).date() == nova_data - timedelta(days=1)

    async def test_editar_observacao_nao_mexe(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        [antes] = await confirmacoes(db_conn, r["tarefa_id"])
        await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"observacoes": "levar proposta impressa"}, headers=h,
        )
        [depois] = await confirmacoes(db_conn, r["tarefa_id"])
        assert depois["atualizado_em"] == antes["atualizado_em"]

    async def test_trocar_quem_agendou_troca_o_dono(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-troca@teste.com")
        sdr_id = await id_de(client, sdr)
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}", json={"agendado_por": sdr_id}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert str(c["responsavel_id"]) == sdr_id

    async def test_trocar_o_contato_pela_tarefa_acompanha(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        outro = (await client.post("/crm/contatos", json={
            "nome": "Bruno Compras", "conta_id": cenario["conta"]["id"],
        }, headers=h)).json()
        resp = await client.patch(
            f"/crm/tarefas/{r['tarefa_id']}", json={"contato_id": outro["id"]}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert str(c["contato_id"]) == outro["id"]
        assert c["descricao"].count("Bruno, tudo certo") == 1


class TestEncerra:
    @pytest.mark.parametrize("desfecho", ["cancelada", "no_show"])
    async def test_desfecho_que_cancela_cancela_a_confirmacao(
        self, desfecho, cenario, client, db_conn,
    ):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": desfecho}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["cancelada_em"] is not None
        assert c["motivo_cancelamento"].startswith("Reunião registrada como")

    async def test_cancelar_a_reuniao_cancela_a_confirmacao(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/cancelar", json={"motivo": "x"}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["motivo_cancelamento"] == crm_agenda.MOTIVO_CONFIRMACAO_REUNIAO_CANCELADA


class TestNaoEProximoPasso:
    async def test_realizada_continua_exigindo_a_proxima(self, cenario, client, db_conn):
        """
        Sozinha na oportunidade, a reunião é o último passo. A confirmação
        aberta não pode contar como "sobra outra": o desfecho a cancela logo
        em seguida, e a oportunidade ficaria sem próximo passo.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        assert r["outras_abertas"] == 0
        url = f"/crm/agenda/reunioes/{r['id']}/desfecho"
        sem = await client.post(url, json={"desfecho": "realizada"}, headers=h)
        assert sem.status_code == 422, sem.text

        com = await client.post(url, json={
            "desfecho": "realizada",
            "proxima": {
                "contato_id": await contato_para_proxima(client, h, url),
                "tipo": "ligacao", "titulo": "Retomar", "responsavel_id": uid,
                "prazo": as_horas(segunda() + timedelta(days=7), 9),
            },
        }, headers=h)
        assert com.status_code == 200, com.text
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        assert c["cancelada_em"] is not None

    async def test_concluir_a_confirmacao_nao_exige_a_proxima(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(segunda() + timedelta(days=1), 9)
        )
        [c] = await confirmacoes(db_conn, r["tarefa_id"])
        resp = await client.post(
            f"/crm/tarefas/{c['id']}/concluir", json={"resultado": "confirmou"}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["confirmacao_de"] == r["tarefa_id"]
