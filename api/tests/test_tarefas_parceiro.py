"""
HIPO — Tarefa presa ao parceiro e farol semanal (migration 006).

O que só aparece com banco: o CHECK do alvo, a herança do alvo na corrente de
follow-up, o recorte de semana feito no Postgres com o fuso da operação, e os
dois agregados novos da linha do parceiro (farol e mini-funil).

Todo teste que envolve relógio passa `hoje` para os endpoints de parceiro e
carimba as tarefas em datas ABSOLUTAS. Nenhum deles muda de resultado
conforme o dia em que a suíte roda — mesmo padrão de test_crm_parceiros.py.

HOJE é 12/08/2026, uma QUARTA-FEIRA. A semana corrente vai de 10/08 (segunda)
a 16/08 (domingo). Quase todo assert daqui depende disso.
"""
import pytest

from tests.conftest import criar_usuario
from tests.test_crm_parceiros import (
    CNPJ_CLIENTE,
    CNPJ_CLIENTE_2,
    CNPJ_PARCEIRO,
    CNPJ_PARCEIRO_2,
    HOJE,
    id_do_usuario,
    marcar_parceiro,
    nova_conta,
    nova_oportunidade,
)

SEMANA_CORRENTE = "2026-08-12"      # quarta
SEMANA_PASSADA = "2026-08-05"       # quarta anterior
DOMINGO_DA_SEMANA = "2026-08-16"
SEGUNDA_DA_SEMANA = "2026-08-10"
FORA_DA_JANELA = "2026-06-10"


# ── Helpers ──────────────────────────────────────────────────────────

async def nova_tarefa(client, headers, responsavel_id, **alvo):
    corpo = {
        "tipo": "ligacao",
        "titulo": "Falar com o contador",
        "responsavel_id": responsavel_id,
        "prazo": "2026-08-12T13:00:00Z",
        **alvo,
    }
    return await client.post("/crm/tarefas", json=corpo, headers=headers)


async def carimbar(db_conn, tarefa_id, *, prazo=None, concluida_em=None):
    """
    Move prazo e/ou conclusão para uma data absoluta.

    Vai direto no banco de propósito: concluir pela API carimba NOW(), e um
    teste de farol que dependesse de NOW() mudaria de resposta toda semana.
    As datas usam 12:00 no fuso da operação para ficarem longe da virada do
    dia — é o corte de SEMANA que está sob teste, não o de dia.
    """
    if prazo is not None:
        await db_conn.execute(
            "UPDATE tarefas SET prazo = ($1 || ' 12:00')::timestamp "
            "AT TIME ZONE 'America/Sao_Paulo' WHERE id = $2::uuid",
            prazo, tarefa_id,
        )
    if concluida_em is not None:
        await db_conn.execute(
            "UPDATE tarefas SET concluida_em = ($1 || ' 12:00')::timestamp "
            "AT TIME ZONE 'America/Sao_Paulo' WHERE id = $2::uuid",
            concluida_em, tarefa_id,
        )


async def linha_do_parceiro(client, headers, conta_id, **params):
    resp = await client.get(
        f"/crm/parceiros/{conta_id}",
        params={"hoje": HOJE, **params},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def cores(client, headers, conta_id):
    linha = await linha_do_parceiro(client, headers, conta_id)
    return [s["cor"] for s in linha["farol"]]


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    """Um parceiro marcado, com o ADM como responsável de tudo."""
    h = usuario_adm["headers"]
    parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
    await marcar_parceiro(client, h, parceiro["id"])
    return {
        "headers": h,
        "parceiro_id": parceiro["id"],
        "usuario_id": await id_do_usuario(db_conn, usuario_adm["email"]),
    }


# ── O alvo ───────────────────────────────────────────────────────────

class TestAlvoDaTarefa:
    """
    ck_tarefa_alvo no banco, validar_alvo no service e o model_validator no
    schema. Os três dizem a mesma coisa; o que muda é a qualidade do erro.
    """

    async def test_dois_alvos_e_422(self, client, cenario):
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(client, cenario["headers"], conta["id"])
        resp = await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            oportunidade_id=opp["id"], conta_id=cenario["parceiro_id"],
        )
        assert resp.status_code == 422
        assert "não das duas" in resp.text

    async def test_nenhum_alvo_e_422(self, client, cenario):
        resp = await nova_tarefa(client, cenario["headers"], cenario["usuario_id"])
        assert resp.status_code == 422
        assert "Informe a oportunidade" in resp.text

    async def test_conta_que_nao_e_parceira_e_422(self, client, cenario):
        """
        Tarefa presa a conta existe para cultivar a PARCERIA. Aceitar
        qualquer conta abriria a porta para follow-up de cliente sem
        oportunidade — a lista de afazeres pessoal com outro nome.
        """
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE_2, "Cliente Dois"
        )
        resp = await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"], conta_id=conta["id"]
        )
        assert resp.status_code == 422
        assert "parceira" in resp.text

    async def test_conta_inexistente_e_422(self, client, cenario):
        resp = await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id="00000000-0000-0000-0000-000000000000",
        )
        assert resp.status_code == 422

    async def test_o_banco_tambem_recusa_tarefa_sem_alvo(self, db_conn, cenario):
        """
        A API é a primeira linha de defesa; ck_tarefa_alvo é a última. Se
        alguém escrever direto no banco — um script, uma migration futura —
        o CHECK ainda pega.
        """
        import asyncpg
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await db_conn.execute(
                "INSERT INTO tarefas (tipo, titulo, responsavel_id, prazo) "
                "VALUES ('ligacao', 'sem alvo', $1::uuid, NOW())",
                cenario["usuario_id"],
            )


class TestTarefaDeParceiro:
    async def test_nasce_com_alvo_parceiro_e_sem_oportunidade(self, client, cenario):
        resp = await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )
        assert resp.status_code == 201, resp.text
        t = resp.json()
        assert t["alvo"] == "parceiro"
        assert t["alvo_rotulo"] == "Parceiro"
        assert t["oportunidade_id"] is None
        assert t["oportunidade_numero"] is None
        assert t["status_oportunidade"] is None
        # A empresa da tarefa é o próprio parceiro.
        assert t["conta_id"] == cenario["parceiro_id"]
        assert t["conta_razao_social"] == "Contabilidade Alfa"

    async def test_tarefa_de_oportunidade_continua_com_alvo_oportunidade(
        self, client, cenario
    ):
        """Regressão: a 006 não pode mudar o que já existia."""
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(client, cenario["headers"], conta["id"])
        resp = await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            oportunidade_id=opp["id"],
        )
        assert resp.status_code == 201, resp.text
        t = resp.json()
        assert t["alvo"] == "oportunidade"
        assert t["oportunidade_numero"] == opp["numero"]
        assert t["conta_id"] == conta["id"]
        assert t["conta_razao_social"] == "Cliente Um"

    async def test_listagem_por_conta_id(self, client, cenario):
        await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )
        resp = await client.get(
            "/crm/tarefas",
            params={"conta_id": cenario["parceiro_id"]},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_conta_id_nao_traz_tarefa_da_oportunidade_daquela_conta(
        self, client, cenario
    ):
        """
        `conta_id` recorta as tarefas DO PARCEIRO, não as dos negócios
        daquela empresa. São perguntas diferentes, e confundir as duas faria
        a aba do parceiro mostrar follow-up de venda.
        """
        opp = await nova_oportunidade(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            oportunidade_id=opp["id"],
        )
        resp = await client.get(
            "/crm/tarefas",
            params={"conta_id": cenario["parceiro_id"]},
            headers=cenario["headers"],
        )
        assert resp.json()["total"] == 0

    async def test_aparece_no_kanban_de_gestao(self, client, cenario):
        """
        Os JOINs de _SELECT_BASE viraram LEFT na 006. Com INNER, toda tarefa
        de parceiro sumiria das listas em silêncio — o pior modo de falha
        possível para uma tela cuja promessa é não deixar nada cair.
        """
        await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )
        resp = await client.get("/crm/tarefas/kanban", headers=cenario["headers"])
        assert resp.status_code == 200
        todas = [t for col in resp.json() for t in col["itens"]]
        assert [t["alvo"] for t in todas] == ["parceiro"]

    async def test_busca_do_kanban_acha_pelo_nome_do_parceiro(self, client, cenario):
        """
        `co.razao_social ILIKE` devolve NULL para tarefa de parceiro, e NULL
        num OR não é falso — é ausência. Sem o COALESCE a busca nunca
        encontraria tarefa de parceiro.
        """
        await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )
        resp = await client.get(
            "/crm/tarefas/kanban", params={"q": "Alfa"}, headers=cenario["headers"]
        )
        assert sum(c["quantidade"] for c in resp.json()) == 1


class TestConclusaoDeTarefaDeParceiro:
    async def test_conclui_sem_proxima(self, client, cenario):
        """
        Parceria não tem estado final. Exigir a próxima ali produziria
        corrente infinita de tarefa de mentira — quem cobra cadência é o
        farol.
        """
        criada = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        resp = await client.post(
            f"/crm/tarefas/{criada['id']}/concluir",
            json={"resultado": "Atendeu, mandou dois contatos"},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["situacao"] == "concluida"

    async def test_a_proxima_herda_o_parceiro(self, client, cenario):
        """
        A corrente de follow-up não pula de alvo: `tarefa_anterior_id`
        apontando para fora do histórico da aba seria história perdida.
        """
        criada = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        resp = await client.post(
            f"/crm/tarefas/{criada['id']}/concluir",
            json={
                "proxima": {
                    "tipo": "reuniao",
                    "titulo": "Café com o contador",
                    "responsavel_id": cenario["usuario_id"],
                    "prazo": "2026-08-20T13:00:00Z",
                }
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text

        lista = await client.get(
            "/crm/tarefas",
            params={"conta_id": cenario["parceiro_id"]},
            headers=cenario["headers"],
        )
        itens = lista.json()["itens"]
        assert len(itens) == 2
        nova = next(i for i in itens if i["id"] != criada["id"])
        assert nova["alvo"] == "parceiro"
        assert nova["conta_id"] == cenario["parceiro_id"]
        assert nova["oportunidade_id"] is None
        assert nova["tarefa_anterior_id"] == criada["id"]

    async def test_oportunidade_aberta_continua_exigindo_a_proxima(
        self, client, cenario
    ):
        """Regressão da regra da Sprint 5. A 006 não pode afrouxá-la."""
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(client, cenario["headers"], conta["id"])
        criada = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            oportunidade_id=opp["id"],
        )).json()
        resp = await client.post(
            f"/crm/tarefas/{criada['id']}/concluir", json={},
            headers=cenario["headers"],
        )
        assert resp.status_code == 422
        assert "próxima" in resp.text


# ── Farol semanal ────────────────────────────────────────────────────

class TestFarolSemanal:
    async def test_parceiro_sem_tarefa_e_quatro_vermelhos(self, client, cenario):
        assert await cores(client, cenario["headers"], cenario["parceiro_id"]) == [
            "vermelho"
        ] * 4

    async def test_concluida_na_semana_pinta_a_corrente_de_verde(
        self, db_conn, client, cenario
    ):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)
        assert (await cores(client, cenario["headers"], cenario["parceiro_id"]))[-1] \
            == "verde"

    async def test_apenas_agendada_pinta_de_amarelo(self, db_conn, client, cenario):
        """
        Agendar dez visitas e não fazer nenhuma não é semana verde. É este
        teste que impede o farol de virar medidor de intenção.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], prazo=SEMANA_CORRENTE)
        assert (await cores(client, cenario["headers"], cenario["parceiro_id"]))[-1] \
            == "amarelo"

    async def test_o_verde_olha_a_conclusao_e_nao_o_prazo(
        self, db_conn, client, cenario
    ):
        """
        Tarefa marcada para a semana passada e feita nesta: verde vai para a
        semana em que o contato ACONTECEU, não para a em que estava previsto.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(
            db_conn, t["id"], prazo=SEMANA_PASSADA, concluida_em=SEMANA_CORRENTE
        )
        assert await cores(client, cenario["headers"], cenario["parceiro_id"]) == [
            "vermelho", "vermelho", "vermelho", "verde",
        ]

    async def test_cancelada_nao_pinta_nada(self, db_conn, client, cenario):
        """Cancelar é dizer que aquilo não deveria ter sido marcado."""
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], prazo=SEMANA_CORRENTE)
        await client.post(
            f"/crm/tarefas/{t['id']}/cancelar", json={"motivo": "duplicada"},
            headers=cenario["headers"],
        )
        assert (await cores(client, cenario["headers"], cenario["parceiro_id"]))[-1] \
            == "vermelho"

    async def test_domingo_ainda_e_a_semana_corrente(self, db_conn, client, cenario):
        """
        A semana vai de segunda a domingo. Em calendário que começa no
        domingo, 16/08 abriria semana nova e a visita de domingo cairia na
        casa errada.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=DOMINGO_DA_SEMANA)
        assert (await cores(client, cenario["headers"], cenario["parceiro_id"]))[-1] \
            == "verde"

    async def test_segunda_tambem_e_a_semana_corrente(self, db_conn, client, cenario):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEGUNDA_DA_SEMANA)
        assert (await cores(client, cenario["headers"], cenario["parceiro_id"]))[-1] \
            == "verde"

    async def test_semana_passada_pinta_a_casa_anterior(
        self, db_conn, client, cenario
    ):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_PASSADA)
        assert await cores(client, cenario["headers"], cenario["parceiro_id"]) == [
            "vermelho", "vermelho", "verde", "vermelho",
        ]

    async def test_contato_antigo_fica_fora_da_janela(self, db_conn, client, cenario):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=FORA_DA_JANELA)
        assert await cores(client, cenario["headers"], cenario["parceiro_id"]) == [
            "vermelho"
        ] * 4

    async def test_tarefa_de_oportunidade_nao_conta_para_o_farol(
        self, db_conn, client, cenario
    ):
        """
        A oportunidade indicada pelo parceiro é trabalho do VENDEDOR. O farol
        mede o cultivo da RELAÇÃO, e contar o follow-up da venda ali faria a
        tela dizer que o parceiro está sendo cuidado quando ninguém falou
        com ele.
        """
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(
            client, cenario["headers"], conta["id"],
            finder_conta_id=cenario["parceiro_id"],
        )
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            oportunidade_id=opp["id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)
        assert await cores(client, cenario["headers"], cenario["parceiro_id"]) == [
            "vermelho"
        ] * 4

    async def test_semanas_sem_contato_conta_ate_o_primeiro_verde(
        self, db_conn, client, cenario
    ):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_PASSADA)
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["semanas_sem_contato"] == 1
        assert linha["sem_contato"] is True

    async def test_o_farol_ignora_o_periodo_da_barra(self, db_conn, client, cenario):
        """
        O período recorta as MÉTRICAS de indicação. O farol é sempre das
        últimas quatro semanas — recortá-lo junto faria a trilha sumir
        quando alguém olhasse o ano corrente.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)
        for periodo in ("sempre", "90d", "ano"):
            linha = await linha_do_parceiro(
                client, cenario["headers"], cenario["parceiro_id"], periodo=periodo
            )
            assert linha["farol"][-1]["cor"] == "verde", periodo


class TestTarefasAbertasDoParceiro:
    async def test_zero_quando_nao_ha_tarefa(self, client, cenario):
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["tarefas_abertas"] == 0
        assert linha["proxima_tarefa_em"] is None

    async def test_conta_abertas_e_traz_a_proxima(self, db_conn, client, cenario):
        for prazo in ("2026-08-25", "2026-08-14"):
            t = (await nova_tarefa(
                client, cenario["headers"], cenario["usuario_id"],
                conta_id=cenario["parceiro_id"],
            )).json()
            await carimbar(db_conn, t["id"], prazo=prazo)
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["tarefas_abertas"] == 2
        assert linha["proxima_tarefa_em"].startswith("2026-08-14")

    async def test_a_proxima_nao_tem_janela(self, db_conn, client, cenario):
        """
        Tarefa marcada para daqui a dois meses continua sendo a próxima.
        Escondê-la faria a tela dizer "sem próximo passo" para quem tem um.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], prazo="2026-12-20")
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["tarefas_abertas"] == 1
        assert linha["proxima_tarefa_em"].startswith("2026-12-20")

    async def test_concluida_sai_da_contagem(self, client, cenario):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await client.post(
            f"/crm/tarefas/{t['id']}/concluir", json={}, headers=cenario["headers"]
        )
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["tarefas_abertas"] == 0


# ── Mini-funil da linha ──────────────────────────────────────────────

class TestMiniFunil:
    async def test_parceiro_sem_indicacao_tem_cinco_fases_zeradas(
        self, client, cenario
    ):
        """
        Modelo fechado, não dicionário livre: a tela desenha cinco faixas
        sempre. Fase ausente do payload viraria faixa que some e volta, e um
        mini-funil que muda de largura não dá para comparar entre linhas.
        """
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert set(linha["funil"]) == {
            "suspect", "lead", "qualificacao", "apresentacao", "negociacao",
        }
        assert all(f["qtd"] == 0 for f in linha["funil"].values())

    async def test_soma_qtd_e_ticket_por_fase(self, client, cenario):
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        conta2 = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE_2, "Cliente Dois"
        )
        for c in (conta, conta2):
            await nova_oportunidade(
                client, cenario["headers"], c["id"],
                finder_conta_id=cenario["parceiro_id"],
                valor_mensalidade=1500,
            )
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["funil"]["suspect"]["qtd"] == 2
        assert float(linha["funil"]["suspect"]["ticket"]) == 3000.0

    async def test_segue_a_oportunidade_quando_ela_muda_de_fase(
        self, client, cenario
    ):
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(
            client, cenario["headers"], conta["id"],
            finder_conta_id=cenario["parceiro_id"],
        )
        resp = await client.patch(
            f"/crm/oportunidades/{opp['id']}/fase",
            json={"fase": "negociacao"}, headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert linha["funil"]["suspect"]["qtd"] == 0
        assert linha["funil"]["negociacao"]["qtd"] == 1

    async def test_finalizada_sai_do_funil(self, client, cenario):
        """
        'finalizado' é fluxo, não estoque — mesma decisão da visão de funil
        da tela de Oportunidades. As taxas continuam contando o desfecho; o
        mini-funil, não.
        """
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        opp = await nova_oportunidade(
            client, cenario["headers"], conta["id"],
            finder_conta_id=cenario["parceiro_id"],
        )
        resp = await client.post(
            f"/crm/oportunidades/{opp['id']}/desfecho",
            json={"status": "conquistado"}, headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert all(f["qtd"] == 0 for f in linha["funil"].values())
        assert linha["convertidas"] == 1

    async def test_indicacao_de_outro_parceiro_nao_entra(self, client, cenario):
        outro = await nova_conta(
            client, cenario["headers"], CNPJ_PARCEIRO_2, "Contabilidade Beta"
        )
        await marcar_parceiro(client, cenario["headers"], outro["id"])
        conta = await nova_conta(
            client, cenario["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        await nova_oportunidade(
            client, cenario["headers"], conta["id"], finder_conta_id=outro["id"]
        )
        linha = await linha_do_parceiro(
            client, cenario["headers"], cenario["parceiro_id"]
        )
        assert all(f["qtd"] == 0 for f in linha["funil"].values())


# ── KPI e filtro da tela ─────────────────────────────────────────────

class TestSemContatoNaListagem:
    async def test_kpi_conta_os_vermelhos_da_semana(self, client, cenario):
        outro = await nova_conta(
            client, cenario["headers"], CNPJ_PARCEIRO_2, "Contabilidade Beta"
        )
        await marcar_parceiro(client, cenario["headers"], outro["id"])
        resp = await client.get(
            "/crm/parceiros/resumo", params={"hoje": HOJE},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["sem_contato_semana"] == 2
        vermelhos = next(
            c for c in corpo["por_cor_semana"] if c["cor"] == "vermelho"
        )
        assert vermelhos["quantidade"] == 2

    async def test_quem_teve_contato_sai_do_kpi(self, db_conn, client, cenario):
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)
        resp = await client.get(
            "/crm/parceiros/resumo", params={"hoje": HOJE},
            headers=cenario["headers"],
        )
        assert resp.json()["sem_contato_semana"] == 0

    async def test_amarelo_tambem_sai_do_kpi(self, db_conn, client, cenario):
        """
        Já tem tarefa marcada com alguém. Um KPI que cobra quem já agendou
        vira ruído que se aprende a ignorar.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], prazo=SEMANA_CORRENTE)
        resp = await client.get(
            "/crm/parceiros/resumo", params={"hoje": HOJE},
            headers=cenario["headers"],
        )
        assert resp.json()["sem_contato_semana"] == 0

    async def test_filtro_devolve_so_os_vermelhos(self, db_conn, client, cenario):
        outro = await nova_conta(
            client, cenario["headers"], CNPJ_PARCEIRO_2, "Contabilidade Beta"
        )
        await marcar_parceiro(client, cenario["headers"], outro["id"])
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)

        resp = await client.get(
            "/crm/parceiros",
            params={"sem_contato": True, "hoje": HOJE},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["total"] == 1
        assert corpo["itens"][0]["razao_social"] == "Contabilidade Beta"

    async def test_o_total_respeita_o_filtro(self, db_conn, client, cenario):
        """
        O filtro roda em Python, depois do SQL. Se o `total` não for
        recalculado ali, a paginação promete páginas que não existem.
        """
        t = (await nova_tarefa(
            client, cenario["headers"], cenario["usuario_id"],
            conta_id=cenario["parceiro_id"],
        )).json()
        await carimbar(db_conn, t["id"], concluida_em=SEMANA_CORRENTE)
        resp = await client.get(
            "/crm/parceiros",
            params={"sem_contato": True, "hoje": HOJE},
            headers=cenario["headers"],
        )
        assert resp.json()["total"] == 0
        assert resp.json()["itens"] == []

    async def test_listagem_traz_farol_e_funil_em_cada_linha(self, client, cenario):
        resp = await client.get(
            "/crm/parceiros", params={"hoje": HOJE}, headers=cenario["headers"]
        )
        item = resp.json()["itens"][0]
        assert len(item["farol"]) == 4
        assert item["farol"][-1]["corrente"] is True
        assert set(item["funil"]) == {
            "suspect", "lead", "qualificacao", "apresentacao", "negociacao",
        }


class TestPermissaoDoModulo:
    async def test_operacional_sem_carteira_nao_ve_o_farol(self, db_conn, client):
        """
        O farol vive dentro do módulo 'parceiros'. Se o guard cair, SDR e EV
        passam a enxergar a cadência de contato de carteira que não é deles.
        """
        u = await criar_usuario(db_conn, client, "SDR", "sdr-farol@teste.com")
        resp = await client.get("/crm/parceiros", headers=u["headers"])
        assert resp.status_code == 403
