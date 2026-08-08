"""
HIPO — Testes do router /crm/tarefas.

As regras puras já estão em test_tarefa_regras.py. Aqui o foco é o que só
aparece com banco:

  * a corrente de follow-up (tarefa_anterior_id) sendo montada de verdade
  * conclusão e criação da próxima na MESMA transação
  * a contagem de abertas que alimenta o badge da aba
  * os CHECKs do banco como última linha de defesa
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services import tarefa as regras
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"


# ── Helpers ──────────────────────────────────────────────────────────

def em(dias, hora=10):
    d = datetime.now(timezone.utc) + timedelta(days=dias)
    return d.replace(hour=hora, minute=0, second=0, microsecond=0).isoformat()


async def nova_conta(client, headers):
    resp = await client.post(
        "/crm/contas",
        json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": CNPJ_A},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_oportunidade(client, headers, conta_id):
    resp = await client.post(
        "/crm/oportunidades", json={"conta_id": conta_id}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_tarefa(client, headers, oportunidade_id, usuario_id, **extra):
    corpo = {
        "oportunidade_id": oportunidade_id,
        "tipo": "ligacao",
        "titulo": "Ligar para o RH",
        "responsavel_id": usuario_id,
        "prazo": em(1),
    }
    corpo.update(extra)
    resp = await client.post("/crm/tarefas", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def proxima(usuario_id, **extra):
    corpo = {
        "tipo": "reuniao",
        "titulo": "Apresentar proposta",
        "responsavel_id": usuario_id,
        "prazo": em(7),
    }
    corpo.update(extra)
    return corpo


async def id_do_usuario(db_conn, email):
    """
    O helper criar_usuario do conftest devolve token e headers, não o id — e
    responsavel_id é obrigatório em toda tarefa.
    """
    return str(await db_conn.fetchval(
        "SELECT id FROM usuarios WHERE email = $1", email
    ))


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    conta = await nova_conta(client, usuario_adm["headers"])
    opp = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
    return {
        "headers": usuario_adm["headers"],
        "usuario_id": await id_do_usuario(db_conn, usuario_adm["email"]),
        "conta": conta,
        "opp": opp,
    }


# ── Criação ──────────────────────────────────────────────────────────

class TestCriar:
    async def test_cria_com_contexto(self, db_conn, client, cenario):
        t = await nova_tarefa(
            client, cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        )
        assert t["oportunidade_numero"] == cenario["opp"]["numero"]
        assert t["conta_razao_social"] == "Metalurgica Alfa LTDA"
        assert t["tipo_rotulo"] == "Ligação"
        assert t["situacao"] == "futura"
        assert t["tarefa_anterior_id"] is None

    async def test_prazo_no_passado_nasce_atrasada(self, db_conn, client, cenario):
        """
        Nada impede registrar uma tarefa com prazo vencido — é assim que se
        lança o que já devia ter sido feito. A situação apenas conta a
        verdade.
        """
        t = await nova_tarefa(
            client, cenario["headers"], cenario["opp"]["id"],
            cenario["usuario_id"], prazo=em(-3),
        )
        assert t["situacao"] == "atrasada"

    async def test_titulo_so_de_espaco_e_422(self, db_conn, client, cenario):
        resp = await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": cenario["opp"]["id"], "tipo": "ligacao",
                "titulo": "   ", "responsavel_id": cenario["usuario_id"],
                "prazo": em(1),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_tipo_desconhecido_e_422(self, db_conn, client, cenario):
        resp = await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": cenario["opp"]["id"], "tipo": "cafezinho",
                "titulo": "X", "responsavel_id": cenario["usuario_id"],
                "prazo": em(1),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_oportunidade_inexistente_e_422(self, db_conn, client, cenario):
        resp = await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": str(uuid.uuid4()), "tipo": "ligacao",
                "titulo": "X", "responsavel_id": cenario["usuario_id"],
                "prazo": em(1),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422
        assert "Oportunidade" in resp.json()["detail"]

    async def test_responsavel_inexistente_e_422(self, db_conn, client, cenario):
        resp = await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": cenario["opp"]["id"], "tipo": "ligacao",
                "titulo": "X", "responsavel_id": str(uuid.uuid4()),
                "prazo": em(1),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422
        assert "Responsável" in resp.json()["detail"]


# ── Listagem ─────────────────────────────────────────────────────────

class TestListagem:
    async def test_passadas_em_aberto_e_futuras_na_mesma_lista(
        self, db_conn, client, cenario
    ):
        """O pedido original: histórico, aberto e futuro juntos."""
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u, prazo=em(-5), titulo="Atrasada")
        await nova_tarefa(client, h, o, u, prazo=em(0), titulo="De hoje")
        await nova_tarefa(client, h, o, u, prazo=em(5), titulo="Futura")

        body = (await client.get(
            f"/crm/tarefas?oportunidade_id={o}", headers=h
        )).json()
        assert body["total"] == 3
        assert [i["situacao"] for i in body["itens"]] == ["atrasada", "hoje", "futura"]

    async def test_ordena_atrasada_primeiro_e_concluida_por_ultimo(
        self, db_conn, client, cenario
    ):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        futura = await nova_tarefa(client, h, o, u, prazo=em(5), titulo="Futura")
        await nova_tarefa(client, h, o, u, prazo=em(-2), titulo="Atrasada")
        await client.post(
            f"/crm/tarefas/{futura['id']}/concluir",
            json={"proxima": proxima(u, prazo=em(9), titulo="Nova")},
            headers=h,
        )
        body = (await client.get(f"/crm/tarefas?oportunidade_id={o}", headers=h)).json()
        situacoes = [i["situacao"] for i in body["itens"]]
        assert situacoes[0] == "atrasada"
        assert situacoes[-1] == "concluida"

    async def test_ordem_cronologica_poe_o_futuro_no_topo(
        self, db_conn, client, cenario
    ):
        """
        Duas ordens porque sao duas perguntas: 'urgencia' e de quem vai
        TRABALHAR a lista, 'cronologico' e de quem vai LER a historia. A
        linha do tempo usa a segunda.
        """
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u, prazo=em(-10), titulo="Mais antiga")
        await nova_tarefa(client, h, o, u, prazo=em(20), titulo="Mais futura")
        await nova_tarefa(client, h, o, u, prazo=em(-1), titulo="Do meio")

        body = (await client.get(
            f"/crm/tarefas?oportunidade_id={o}&ordenar=cronologico", headers=h
        )).json()
        assert [i["titulo"] for i in body["itens"]] == [
            "Mais futura", "Do meio", "Mais antiga",
        ]

    async def test_urgencia_continua_sendo_o_padrao(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u, prazo=em(20), titulo="Futura")
        await nova_tarefa(client, h, o, u, prazo=em(-10), titulo="Atrasada")
        body = (await client.get(f"/crm/tarefas?oportunidade_id={o}", headers=h)).json()
        assert body["itens"][0]["titulo"] == "Atrasada"

    async def test_ordenar_invalido_e_422(self, db_conn, client, cenario):
        resp = await client.get(
            "/crm/tarefas?ordenar=alfabetica", headers=cenario["headers"]
        )
        assert resp.status_code == 422

    async def test_contadores_ignoram_fechadas(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u, prazo=em(-3), titulo="Atrasada")
        t = await nova_tarefa(client, h, o, u, prazo=em(2), titulo="Futura")
        await client.post(f"/crm/tarefas/{t['id']}/cancelar", json={}, headers=h)

        body = (await client.get(f"/crm/tarefas?oportunidade_id={o}", headers=h)).json()
        assert body["total"] == 2
        assert body["abertas"] == 1
        assert body["atrasadas"] == 1

    async def test_filtra_por_situacao(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u, prazo=em(-3))
        await nova_tarefa(client, h, o, u, prazo=em(3))
        body = (await client.get(
            f"/crm/tarefas?oportunidade_id={o}&situacao=atrasada", headers=h
        )).json()
        assert len(body["itens"]) == 1
        # Os contadores continuam sendo do conjunto INTEIRO, não do filtrado —
        # senão o cabeçalho mentiria sobre quanto falta.
        assert body["total"] == 2

    async def test_situacao_invalida_e_422(self, db_conn, client, cenario):
        resp = await client.get(
            "/crm/tarefas?situacao=amanha", headers=cenario["headers"]
        )
        assert resp.status_code == 422

    async def test_filtra_por_responsavel(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await criar_usuario(db_conn, client, "EV", "outro@teste.com")
        outro_id = await id_do_usuario(db_conn, "outro@teste.com")
        await nova_tarefa(client, h, o, u)
        await nova_tarefa(client, h, o, outro_id, titulo="Do outro")
        body = (await client.get(
            f"/crm/tarefas?responsavel_id={outro_id}", headers=h
        )).json()
        assert [i["titulo"] for i in body["itens"]] == ["Do outro"]

    async def test_tarefa_de_outra_oportunidade_nao_vaza(self, db_conn, client, cenario):
        h, u = cenario["headers"], cenario["usuario_id"]
        outra = await nova_oportunidade(client, h, cenario["conta"]["id"])
        await nova_tarefa(client, h, cenario["opp"]["id"], u, titulo="Da primeira")
        await nova_tarefa(client, h, outra["id"], u, titulo="Da segunda")
        body = (await client.get(
            f"/crm/tarefas?oportunidade_id={outra['id']}", headers=h
        )).json()
        assert [i["titulo"] for i in body["itens"]] == ["Da segunda"]


# ── Conclusão e a corrente ───────────────────────────────────────────

class TestConcluir:
    async def test_sem_proxima_com_oportunidade_ativa_e_recusado(
        self, db_conn, client, cenario
    ):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir", json={"resultado": "Falei"}, headers=h
        )
        assert resp.status_code == 422
        assert "próxima tarefa" in resp.json()["detail"]

    async def test_com_proxima_conclui_e_agenda(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"resultado": "Atendeu, pediu proposta", "proxima": proxima(u)},
            headers=h,
        )
        assert resp.status_code == 200
        # Devolve a CONCLUÍDA, não a nova: quem chamou está fechando um item.
        assert resp.json()["id"] == t["id"]
        assert resp.json()["situacao"] == "concluida"
        assert resp.json()["resultado"] == "Atendeu, pediu proposta"

        body = (await client.get(f"/crm/tarefas?oportunidade_id={o}", headers=h)).json()
        assert body["total"] == 2
        assert body["abertas"] == 1

    async def test_a_proxima_aponta_para_a_anterior(self, db_conn, client, cenario):
        """
        A corrente é o que permite reconstruir depois quanto tempo a
        negociação levou entre um contato e outro, sem inferir nada.
        """
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(u)}, headers=h,
        )
        body = (await client.get(f"/crm/tarefas?oportunidade_id={o}", headers=h)).json()
        nova = next(i for i in body["itens"] if i["id"] != t["id"])
        assert nova["tarefa_anterior_id"] == t["id"]

    async def test_oportunidade_finalizada_dispensa_a_proxima(
        self, db_conn, client, cenario
    ):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.post(
            f"/crm/oportunidades/{o}/desfecho",
            json={"status": "conquistado"}, headers=h,
        )
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"resultado": "Assinou"}, headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["situacao"] == "concluida"

    async def test_suspensa_continua_exigindo(self, db_conn, client, cenario):
        """Pausa sem data para voltar é como oportunidade morre em silêncio."""
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.patch(
            f"/crm/oportunidades/{o}/status",
            json={"status": "suspensa"}, headers=h,
        )
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir", json={}, headers=h
        )
        assert resp.status_code == 422

    async def test_proxima_com_responsavel_invalido_nao_conclui_nada(
        self, db_conn, client, cenario
    ):
        """
        Conclusão e próxima vivem na mesma transação. Se a próxima é
        impossível, a tarefa NÃO pode ficar concluída — senão a oportunidade
        ficaria sem próximo passo, que é o buraco que a regra tapa.
        """
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(str(uuid.uuid4()))}, headers=h,
        )
        assert resp.status_code == 422
        depois = (await client.get(f"/crm/tarefas/{t['id']}", headers=h)).json()
        assert depois["situacao"] != "concluida"
        assert depois["concluida_em"] is None

    async def test_nao_conclui_duas_vezes(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(u)}, headers=h,
        )
        resp = await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(u)}, headers=h,
        )
        assert resp.status_code == 422
        assert "já foi concluída" in resp.json()["detail"]

    async def test_resultado_em_branco_vira_nulo(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        body = (await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"resultado": "   ", "proxima": proxima(u)}, headers=h,
        )).json()
        assert body["resultado"] is None


# ── Cancelamento ─────────────────────────────────────────────────────

class TestCancelar:
    async def test_cancela_sem_exigir_proxima(self, db_conn, client, cenario):
        """
        Cancelar é dizer que aquilo não deveria ter sido agendado, não que o
        negócio andou.
        """
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        body = (await client.post(
            f"/crm/tarefas/{t['id']}/cancelar",
            json={"motivo": "Agendei duplicado"}, headers=h,
        )).json()
        assert body["situacao"] == "cancelada"
        assert body["motivo_cancelamento"] == "Agendei duplicado"

    async def test_concluida_nao_cancela(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(u)}, headers=h,
        )
        resp = await client.post(f"/crm/tarefas/{t['id']}/cancelar", json={}, headers=h)
        assert resp.status_code == 422


# ── Edição ───────────────────────────────────────────────────────────

class TestEditar:
    async def test_edita_aberta(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        body = (await client.patch(
            f"/crm/tarefas/{t['id']}",
            json={"titulo": "Ligar de novo", "tipo": "whatsapp"}, headers=h,
        )).json()
        assert body["titulo"] == "Ligar de novo"
        assert body["tipo_rotulo"] == "WhatsApp"

    async def test_fechada_nao_edita(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        await client.post(
            f"/crm/tarefas/{t['id']}/concluir",
            json={"proxima": proxima(u)}, headers=h,
        )
        resp = await client.patch(
            f"/crm/tarefas/{t['id']}", json={"titulo": "Reescrevendo"}, headers=h
        )
        assert resp.status_code == 422
        assert "imutável" in resp.json()["detail"]

    async def test_patch_vazio_nao_quebra(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        resp = await client.patch(f"/crm/tarefas/{t['id']}", json={}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["titulo"] == t["titulo"]

    async def test_muda_prazo_muda_a_situacao(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u, prazo=em(5))
        assert t["situacao"] == "futura"
        body = (await client.patch(
            f"/crm/tarefas/{t['id']}", json={"prazo": em(-2)}, headers=h
        )).json()
        assert body["situacao"] == "atrasada"

    async def test_inexistente_e_404(self, db_conn, client, cenario):
        resp = await client.patch(
            f"/crm/tarefas/{uuid.uuid4()}", json={"titulo": "X"},
            headers=cenario["headers"],
        )
        assert resp.status_code == 404


# ── Integração com a oportunidade ────────────────────────────────────

class TestBadgeDaAba:
    async def test_detalhe_conta_as_abertas(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        detalhe = (await client.get(f"/crm/oportunidades/{o}", headers=h)).json()
        assert detalhe["tarefas_abertas"] == 0

        await nova_tarefa(client, h, o, u)
        t = await nova_tarefa(client, h, o, u, prazo=em(3))
        await client.post(f"/crm/tarefas/{t['id']}/cancelar", json={}, headers=h)

        detalhe = (await client.get(f"/crm/oportunidades/{o}", headers=h)).json()
        assert detalhe["tarefas_abertas"] == 1

    async def test_apagar_oportunidade_leva_as_tarefas(self, db_conn, client, cenario):
        """ON DELETE CASCADE: tarefa órfã de oportunidade não faz sentido."""
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        await nova_tarefa(client, h, o, u)
        await db_conn.execute("DELETE FROM oportunidades WHERE id = $1", uuid.UUID(o))
        restam = await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1", uuid.UUID(o)
        )
        assert restam == 0


# ── CHECKs do banco, última linha de defesa ──────────────────────────

class TestChecksDoBanco:
    async def test_nao_aceita_concluida_e_cancelada(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        with pytest.raises(Exception, match="ck_tarefa_desfecho_unico"):
            await db_conn.execute(
                "UPDATE tarefas SET concluida_em = NOW(), cancelada_em = NOW()"
                " WHERE id = $1",
                uuid.UUID(t["id"]),
            )

    async def test_resultado_exige_conclusao(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        with pytest.raises(Exception, match="ck_tarefa_resultado"):
            await db_conn.execute(
                "UPDATE tarefas SET resultado = 'x' WHERE id = $1", uuid.UUID(t["id"])
            )

    async def test_tarefa_nao_e_a_propria_antecessora(self, db_conn, client, cenario):
        h, o, u = cenario["headers"], cenario["opp"]["id"], cenario["usuario_id"]
        t = await nova_tarefa(client, h, o, u)
        with pytest.raises(Exception, match="ck_tarefa_corrente"):
            await db_conn.execute(
                "UPDATE tarefas SET tarefa_anterior_id = id WHERE id = $1",
                uuid.UUID(t["id"]),
            )


# ── Schema x codigo ──────────────────────────────────────────────────

class TestSchemaBateComOCodigo:
    """
    Mesmo guarda que existe para as fases: o CI cria o banco a partir de
    api/schema.sql, não das migrations. Se a 004 mudar um CHECK e o
    schema.sql não acompanhar, isto falha com mensagem acionável em vez de
    dezenas de CheckViolationError.
    """

    async def test_o_banco_aceita_todos_os_tipos_do_codigo(self, db_conn):
        definicao = await db_conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'tarefas'::regclass AND conname = 'ck_tarefa_tipo'"
        )
        assert definicao, "constraint ck_tarefa_tipo nao existe no banco de teste"
        faltando = [t for t in regras.TIPOS if f"'{t}'" not in definicao]
        assert faltando == [], (
            f"ck_tarefa_tipo nao aceita {faltando}. "
            "Atualize api/schema.sql junto com a migration."
        )

    async def test_indice_das_abertas_existe(self, db_conn):
        """É o índice que a 'próxima tarefa' da Etapa 5 vai usar."""
        existe = await db_conn.fetchval(
            "SELECT 1 FROM pg_indexes"
            " WHERE tablename = 'tarefas' AND indexname = 'idx_tarefas_abertas'"
        )
        assert existe == 1
