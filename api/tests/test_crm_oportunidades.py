"""
HIPO — Testes do router /crm/oportunidades.

As regras do funil já têm testes puros em test_oportunidade_regras.py. Aqui o
foco é o que só aparece com banco: numeração sob concorrência, a trilha em
oportunidade_eventos, o marcador automático de finder e os agregados do
kanban e do resumo.
"""
import asyncio
import uuid

import pytest

from routers import crm_oportunidades
from services import oportunidade as regras
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_B = "34.028.316/0001-03"
CNPJ_C = "47.960.950/0001-21"


# ── Helpers ──────────────────────────────────────────────────────────

async def nova_conta(client, headers, cnpj=CNPJ_A, razao="Metalurgica Alfa LTDA"):
    resp = await client.post(
        "/crm/contas", json={"razao_social": razao, "cnpj": cnpj}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_oportunidade(client, headers, conta_id, **extra):
    corpo = {"conta_id": conta_id}
    corpo.update(extra)
    resp = await client.post("/crm/oportunidades", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def novo_motivo(client, headers, tipo="perda", nome="Preço"):
    resp = await client.post(
        f"/crm/dominio/motivos/{tipo}", json={"nome": nome}, headers=headers
    )
    return resp.json()


# ── Schema x codigo ──────────────────────────────────────────────────

class TestSchemaBateComOCodigo:
    """
    O CI cria o banco de teste a partir de api/schema.sql, NAO das migrations.
    Quando uma migration muda um CHECK e o schema.sql nao acompanha, a suite
    passa na maquina de quem aplicou a migration a mao e quebra no CI com
    CheckViolationError em dezenas de testes de uma vez. Aconteceu com a fase
    'suspect'. Estes dois testes comparam as duas fontes direto no catalogo do
    Postgres e falham com mensagem que diz o que fazer.
    """

    async def _definicao(self, conn, nome):
        return await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'oportunidades'::regclass AND conname = $1",
            nome,
        )

    async def test_o_banco_aceita_todas_as_fases_do_codigo(self, db_conn):
        definicao = await self._definicao(db_conn, "ck_opp_fase")
        assert definicao, "constraint ck_opp_fase nao existe no banco de teste"
        faltando = [f for f in regras.FASES if f"'{f}'" not in definicao]
        assert faltando == [], (
            f"ck_opp_fase nao aceita {faltando}. "
            "Atualize api/schema.sql junto com a migration."
        )

    async def test_o_banco_aceita_todas_as_fases_de_desfecho(self, db_conn):
        definicao = await self._definicao(db_conn, "ck_opp_fase_desfecho")
        assert definicao, "constraint ck_opp_fase_desfecho nao existe no banco de teste"
        faltando = [f for f in regras.FASES_ABERTAS if f"'{f}'" not in definicao]
        assert faltando == [], (
            f"ck_opp_fase_desfecho nao aceita {faltando}. "
            "Atualize api/schema.sql junto com a migration."
        )


# ── Criação e numeração ──────────────────────────────────────────────

class TestCriar:
    async def test_nasce_ativa_em_suspect(self, db_conn, client, usuario_adm):
        """Sem fase informada, a oportunidade nasce na boca do funil."""
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        assert o["fase"] == "suspect"
        assert o["status"] == "ativa"
        assert o["temperatura"] == 50
        assert o["fase_desfecho"] is None

    async def test_numero_no_formato_esperado(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        assert o["numero"].startswith("OPP-")
        _, ano, seq = o["numero"].split("-")
        assert len(ano) == 4 and seq.isdigit() and len(seq) >= 5

    async def test_numeros_sao_unicos_sob_concorrencia(self, db_conn, client, usuario_adm):
        """
        A numeração é gerada dentro do INSERT (nextval + lpad). Ler a sequence
        antes e inserir depois deixaria duas requisições pegarem o mesmo
        número.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        respostas = await asyncio.gather(*[
            client.post(
                "/crm/oportunidades",
                json={"conta_id": conta["id"]},
                headers=usuario_adm["headers"],
            )
            for _ in range(8)
        ])
        numeros = [r.json()["numero"] for r in respostas if r.status_code == 201]
        assert len(numeros) == 8
        assert len(set(numeros)) == 8

    async def test_registra_evento_de_criacao(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        eventos = (await client.get(
            f"/crm/oportunidades/{o['id']}/eventos", headers=usuario_adm["headers"]
        )).json()
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "criacao"
        assert eventos[0]["para"] == "suspect"
        assert eventos[0]["usuario"] == "Test ADM"

    async def test_pode_nascer_em_outra_fase_aberta(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        assert o["fase"] == "negociacao"

    async def test_nao_nasce_finalizada(self, db_conn, client, usuario_adm):
        """Desfecho é transição, não estado inicial."""
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "fase": "finalizado"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_temperatura_fora_da_escala(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "temperatura": 55},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_conta_inexistente(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": str(uuid.uuid4())},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_contato_precisa_estar_vinculado_a_conta(
        self, db_conn, client, usuario_adm
    ):
        """
        Contato de outra empresa numa oportunidade é erro de digitação com
        consequência: o vendedor ligaria para a pessoa errada.
        """
        conta = await nova_conta(client, usuario_adm["headers"], CNPJ_A)
        outra = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Beta SA")
        contato = (await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": outra["id"]},
            headers=usuario_adm["headers"],
        )).json()

        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "contato_id": contato["id"]},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "vinculado" in resp.json()["detail"]

    async def test_contato_vinculado_e_aceito(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        contato = (await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )).json()
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], contato_id=contato["id"]
        )
        assert o["contato_nome"] == "Maria"

    async def test_conta_nao_indica_a_si_mesma(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "finder_conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422


class TestFinderAutomatico:
    async def test_usar_como_finder_marca_a_conta(self, db_conn, client, usuario_adm):
        """
        O sistema aprende do uso. Exigir marcar a caixinha antes criaria um
        passo que o usuário só descobre quando o picker não acha a empresa.
        """
        conta = await nova_conta(client, usuario_adm["headers"], CNPJ_A)
        contador = await nova_conta(
            client, usuario_adm["headers"], CNPJ_B, "Contabilidade Beta"
        )
        assert contador["eh_finder"] is False

        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], finder_conta_id=contador["id"]
        )
        atualizada = (await client.get(
            f"/crm/contas/{contador['id']}", headers=usuario_adm["headers"]
        )).json()
        assert atualizada["eh_finder"] is True

    async def test_marca_tambem_ao_editar(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"], CNPJ_A)
        contador = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Beta")
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])

        await client.patch(
            f"/crm/oportunidades/{o['id']}",
            json={"finder_conta_id": contador["id"]},
            headers=usuario_adm["headers"],
        )
        atualizada = (await client.get(
            f"/crm/contas/{contador['id']}", headers=usuario_adm["headers"]
        )).json()
        assert atualizada["eh_finder"] is True


# ── Movimento no funil ───────────────────────────────────────────────

class TestMoverFase:
    async def test_move_e_registra_evento(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])

        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}/fase",
            json={"fase": "qualificacao"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["fase"] == "qualificacao"

        eventos = (await client.get(
            f"/crm/oportunidades/{o['id']}/eventos", headers=usuario_adm["headers"]
        )).json()
        fase = next(e for e in eventos if e["tipo"] == "fase")
        assert (fase["de"], fase["para"]) == ("suspect", "qualificacao")

    async def test_arrastar_para_finalizado_e_recusado(self, db_conn, client, usuario_adm):
        """O kanban precisa abrir o modal de desfecho."""
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}/fase",
            json={"fase": "finalizado"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "desfecho" in resp.json()["detail"]

    async def test_finalizada_nao_muda_de_fase(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}/fase",
            json={"fase": "negociacao"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_404_em_inexistente(self, db_conn, client, usuario_adm):
        resp = await client.patch(
            f"/crm/oportunidades/{uuid.uuid4()}/fase",
            json={"fase": "lead"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404


class TestDesfecho:
    async def test_conquistar_guarda_a_fase_de_origem(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )).json()
        assert body["fase"] == "finalizado"
        assert body["status"] == "conquistado"
        assert body["fase_desfecho"] == "negociacao"

    async def test_perder_exige_motivo(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "perdido"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "motivo" in resp.json()["detail"]

    async def test_perder_com_motivo(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        motivo = await novo_motivo(client, usuario_adm["headers"], "perda", "Preço")
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="apresentacao"
        )
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "perdido", "motivo_desfecho_id": motivo["id"]},
            headers=usuario_adm["headers"],
        )).json()
        assert body["motivo_desfecho"] == "Preço"
        assert body["fase_desfecho"] == "apresentacao"

    async def test_motivo_inexistente(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "perdido", "motivo_desfecho_id": 99999},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_cancelar_com_motivo_proprio(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        motivo = await novo_motivo(
            client, usuario_adm["headers"], "cancelamento", "Lead errado do finder"
        )
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "cancelado", "motivo_desfecho_id": motivo["id"]},
            headers=usuario_adm["headers"],
        )).json()
        assert body["status"] == "cancelado"

    async def test_observacao_do_desfecho_e_anexada(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], observacoes="Contato inicial"
        )
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado", "observacoes": "Assinou dia 10"},
            headers=usuario_adm["headers"],
        )).json()
        assert "Contato inicial" in body["observacoes"]
        assert "Assinou dia 10" in body["observacoes"]

    async def test_nao_finaliza_duas_vezes(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        url = f"/crm/oportunidades/{o['id']}/desfecho"
        await client.post(url, json={"status": "conquistado"}, headers=usuario_adm["headers"])
        resp = await client.post(
            url, json={"status": "conquistado"}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422


class TestReabrir:
    async def test_volta_para_a_fase_de_origem(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        motivo = await novo_motivo(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "perdido", "motivo_desfecho_id": motivo["id"]},
            headers=usuario_adm["headers"],
        )
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/reabrir",
            json={},
            headers=usuario_adm["headers"],
        )).json()
        assert body["fase"] == "negociacao"
        assert body["status"] == "ativa"
        assert body["fase_desfecho"] is None
        assert body["motivo_desfecho"] is None

    async def test_fase_explicita(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        body = (await client.post(
            f"/crm/oportunidades/{o['id']}/reabrir",
            json={"fase": "lead", "temperatura": 30},
            headers=usuario_adm["headers"],
        )).json()
        assert (body["fase"], body["temperatura"]) == ("lead", 30)

    async def test_registra_evento_de_reabertura(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        await client.post(
            f"/crm/oportunidades/{o['id']}/reabrir", json={}, headers=usuario_adm["headers"]
        )
        eventos = (await client.get(
            f"/crm/oportunidades/{o['id']}/eventos", headers=usuario_adm["headers"]
        )).json()
        assert any(e["tipo"] == "reabertura" for e in eventos)

    async def test_reabertura_preserva_os_eventos_de_fase_e_status(
        self, db_conn, client, usuario_adm
    ):
        """
        Reabrir grava TRÊS eventos: fase, status e o marcador de reabertura.

        Antes da correção o tipo dos três era reescrito para 'reabertura': a
        transição de fase da volta sumia — e com ela o tempo por fase —, o
        status sumia — e com ele conquistadas/perdidas —, e uma reabertura
        contava como duas.

        O teste vizinho usa any() e passa MESMO COM O BUG, porque com o bug
        todos os eventos viram 'reabertura'. Este exige os três tipos
        distintos, que é o que o any() não consegue ver.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        await client.post(
            f"/crm/oportunidades/{o['id']}/reabrir",
            json={},
            headers=usuario_adm["headers"],
        )

        eventos = (await client.get(
            f"/crm/oportunidades/{o['id']}/eventos", headers=usuario_adm["headers"]
        )).json()

        # A rota devolve do mais novo para o mais antigo, então os três
        # primeiros são os da reabertura.
        da_reabertura = eventos[:3]
        assert sorted(e["tipo"] for e in da_reabertura) == [
            "fase", "reabertura", "status",
        ]

        fase = next(e for e in da_reabertura if e["tipo"] == "fase")
        assert (fase["de"], fase["para"]) == ("finalizado", "negociacao")

        status = next(e for e in da_reabertura if e["tipo"] == "status")
        assert (status["de"], status["para"]) == ("conquistado", "ativa")

        # Uma reabertura é UM evento de reabertura, não dois.
        assert sum(1 for e in eventos if e["tipo"] == "reabertura") == 1

    async def test_so_reabre_finalizada(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.post(
            f"/crm/oportunidades/{o['id']}/reabrir", json={}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422


class TestStatus:
    async def test_suspende_e_reativa(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        url = f"/crm/oportunidades/{o['id']}/status"

        assert (await client.patch(
            url, json={"status": "suspensa"}, headers=usuario_adm["headers"]
        )).json()["status"] == "suspensa"

        assert (await client.patch(
            url, json={"status": "ativa"}, headers=usuario_adm["headers"]
        )).json()["status"] == "ativa"

    async def test_suspensa_nao_conta_como_vendedor_da_conta(
        self, db_conn, client, usuario_adm
    ):
        """Regra do vendedor derivado: só status='ativa' alimenta a conta."""
        ev = await criar_usuario(db_conn, client, "EV", "ev-susp-opp@teste.com")
        ev_id = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1", ev["email"]
        )
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": str(ev_id), "papel": "EV"}],
        )
        antes = (await client.get(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert antes["vendedores"] == ["Test EV"]

        await client.patch(
            f"/crm/oportunidades/{o['id']}/status",
            json={"status": "suspensa"},
            headers=usuario_adm["headers"],
        )
        depois = (await client.get(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert depois["vendedores"] == []

    async def test_nao_aceita_desfecho(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}/status",
            json={"status": "perdido"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422


# ── Envolvidos e concorrentes ────────────────────────────────────────

class TestEnvolvidos:
    async def test_define_na_criacao(self, db_conn, client, usuario_adm):
        u = await criar_usuario(db_conn, client, "EC", "ec-env@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", u["email"])
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": str(uid), "papel": "EC"}],
        )
        assert o["envolvidos"][0]["papel"] == "EC"
        assert o["envolvidos"][0]["nome"] == "Test EC"

    async def test_mesma_pessoa_com_dois_papeis(self, db_conn, client, usuario_adm):
        """Quem prospectou como SDR e tocou como EV é o caso comum."""
        u = await criar_usuario(db_conn, client, "SDR", "sdr-duplo@teste.com")
        uid = str(await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1", u["email"]
        ))
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[
                {"usuario_id": uid, "papel": "SDR"},
                {"usuario_id": uid, "papel": "EV"},
            ],
        )
        assert sorted(e["papel"] for e in o["envolvidos"]) == ["EV", "SDR"]

    async def test_put_substitui_a_lista(self, db_conn, client, usuario_adm):
        a = await criar_usuario(db_conn, client, "EC", "a-env@teste.com")
        b = await criar_usuario(db_conn, client, "EV", "b-env@teste.com")
        ida = str(await db_conn.fetchval("SELECT id FROM usuarios WHERE email=$1", a["email"]))
        idb = str(await db_conn.fetchval("SELECT id FROM usuarios WHERE email=$1", b["email"]))
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": ida, "papel": "EC"}],
        )
        body = (await client.put(
            f"/crm/oportunidades/{o['id']}/envolvidos",
            json=[{"usuario_id": idb, "papel": "EV"}],
            headers=usuario_adm["headers"],
        )).json()
        assert len(body["envolvidos"]) == 1
        assert body["envolvidos"][0]["papel"] == "EV"

    async def test_lista_vazia_remove_todos(self, db_conn, client, usuario_adm):
        u = await criar_usuario(db_conn, client, "EC", "limpar@teste.com")
        uid = str(await db_conn.fetchval("SELECT id FROM usuarios WHERE email=$1", u["email"]))
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": uid, "papel": "EC"}],
        )
        body = (await client.put(
            f"/crm/oportunidades/{o['id']}/envolvidos",
            json=[], headers=usuario_adm["headers"],
        )).json()
        assert body["envolvidos"] == []

    async def test_papel_invalido(self, db_conn, client, usuario_adm):
        u = await criar_usuario(db_conn, client, "EC", "papel@teste.com")
        uid = str(await db_conn.fetchval("SELECT id FROM usuarios WHERE email=$1", u["email"]))
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={
                "conta_id": conta["id"],
                "envolvidos": [{"usuario_id": uid, "papel": "GERENTE"}],
            },
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_usuario_inexistente(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={
                "conta_id": conta["id"],
                "envolvidos": [{"usuario_id": str(uuid.uuid4()), "papel": "EC"}],
            },
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422


class TestConcorrentes:
    async def test_define_e_substitui(self, db_conn, client, usuario_adm):
        c1 = (await client.post(
            "/crm/dominio/concorrentes", json={"nome": "Rival A"},
            headers=usuario_adm["headers"],
        )).json()
        c2 = (await client.post(
            "/crm/dominio/concorrentes", json={"nome": "Rival B"},
            headers=usuario_adm["headers"],
        )).json()
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], concorrentes=[c1["id"]]
        )
        assert [c["nome"] for c in o["concorrentes"]] == ["Rival A"]

        body = (await client.put(
            f"/crm/oportunidades/{o['id']}/concorrentes",
            json=[c1["id"], c2["id"]],
            headers=usuario_adm["headers"],
        )).json()
        assert sorted(c["nome"] for c in body["concorrentes"]) == ["Rival A", "Rival B"]

    async def test_concorrente_inexistente(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/oportunidades",
            json={"conta_id": conta["id"], "concorrentes": [99999]},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422


# ── Kanban ───────────────────────────────────────────────────────────

class TestKanban:
    async def test_seis_colunas_na_ordem_do_funil(self, db_conn, client, usuario_adm):
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        assert [c["fase"] for c in colunas] == [
            "suspect", "lead", "qualificacao", "apresentacao",
            "negociacao", "finalizado",
        ]

    async def test_so_finalizado_e_somente_leitura(self, db_conn, client, usuario_adm):
        """
        Fechar exige status e motivo. A flag e o que faz o front recusar o
        cartao solto na coluna e abrir o modal de desfecho no lugar.
        """
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        leitura = [c["fase"] for c in colunas if c["somente_leitura"]]
        assert leitura == ["finalizado"]

    async def test_soma_ticket_por_coluna(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        for valor in (1000, 2500):
            await nova_oportunidade(
                client, usuario_adm["headers"], conta["id"],
                fase="negociacao", valor_mensalidade=valor,
            )
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        negociacao = next(c for c in colunas if c["fase"] == "negociacao")
        assert negociacao["quantidade"] == 2
        assert float(negociacao["ticket_total"]) == 3500.0

    async def test_finalizada_sai_das_abertas_e_entra_na_coluna_final(
        self, db_conn, client, usuario_adm
    ):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        abertas = [c for c in colunas if not c["somente_leitura"]]
        final = next(c for c in colunas if c["fase"] == "finalizado")
        assert sum(c["quantidade"] for c in abertas) == 0
        assert final["quantidade"] == 1
        assert [i["numero"] for i in final["itens"]] == [o["numero"]]

    async def test_ticket_da_coluna_final_conta_so_conquistadas(
        self, db_conn, client, usuario_adm
    ):
        """
        Somar mensalidade de perdida com ganha produz um numero que nao
        significa nada. A coluna soma so o que entrou de fato.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        ganha = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], valor_mensalidade=1000
        )
        perdida = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], valor_mensalidade=9000
        )
        motivo = (await client.post(
            "/crm/dominio/motivos/perda", json={"nome": "Preco"},
            headers=usuario_adm["headers"],
        )).json()
        await client.post(
            f"/crm/oportunidades/{ganha['id']}/desfecho",
            json={"status": "conquistado"}, headers=usuario_adm["headers"],
        )
        await client.post(
            f"/crm/oportunidades/{perdida['id']}/desfecho",
            json={"status": "perdido", "motivo_desfecho_id": motivo["id"]},
            headers=usuario_adm["headers"],
        )
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        final = next(c for c in colunas if c["fase"] == "finalizado")
        assert final["quantidade"] == 2
        assert float(final["ticket_total"]) == 1000.0

    async def test_coluna_final_so_traz_o_mes_corrente(
        self, db_conn, client, usuario_adm
    ):
        """
        O funil aberto e estoque e cresce devagar; o finalizado e fluxo e
        cresce para sempre. Sem recorte a coluna viraria arquivo morto.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"}, headers=usuario_adm["headers"],
        )
        # Empurra o fechamento para o mes passado direto no banco: nao existe
        # endpoint para reescrever atualizado_em, e a regra e do SELECT.
        await db_conn.execute(
            "UPDATE oportunidades SET atualizado_em = NOW() - interval '45 days'"
            " WHERE id = $1",
            uuid.UUID(o["id"]),
        )
        colunas = (await client.get(
            "/crm/oportunidades/kanban", headers=usuario_adm["headers"]
        )).json()
        final = next(c for c in colunas if c["fase"] == "finalizado")
        assert final["quantidade"] == 0
        assert final["itens"] == []

    async def test_total_da_coluna_independe_do_limite_de_cartoes(
        self, db_conn, client, usuario_adm
    ):
        """
        O topo mostra o pipeline inteiro mesmo quando a coluna tem mais itens
        do que cabe na tela.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        for _ in range(3):
            await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        colunas = (await client.get(
            "/crm/oportunidades/kanban?por_coluna=1", headers=usuario_adm["headers"]
        )).json()
        suspect = next(c for c in colunas if c["fase"] == "suspect")
        assert suspect["quantidade"] == 3
        assert len(suspect["itens"]) == 1

    async def test_filtra_por_conta(self, db_conn, client, usuario_adm):
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Alfa")
        b = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Beta")
        await nova_oportunidade(client, usuario_adm["headers"], a["id"])
        await nova_oportunidade(client, usuario_adm["headers"], b["id"])
        colunas = (await client.get(
            f"/crm/oportunidades/kanban?conta_id={a['id']}", headers=usuario_adm["headers"]
        )).json()
        assert sum(c["quantidade"] for c in colunas) == 1


# ── Resumo ───────────────────────────────────────────────────────────

class TestResumo:
    async def test_banco_vazio(self, db_conn, client, usuario_adm):
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        assert body["abertas"] == 0
        assert float(body["ticket_aberto"]) == 0.0
        assert len(body["por_fase"]) == 5

    async def test_conta_abertas_e_ticket(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], valor_mensalidade=1500
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], valor_mensalidade=500
        )
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        assert body["abertas"] == 2
        assert float(body["ticket_aberto"]) == 2000.0

    async def test_resumo_nao_tem_sem_proxima_acao(self, db_conn, client, usuario_adm):
        """
        O indicador saiu do produto: concluir uma tarefa vai obrigar o
        vendedor a criar a proxima, entao ele nasceria zerado para sempre.
        Este teste existe para o campo nao voltar por engano junto com algum
        merge antigo.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        assert "sem_proxima_acao" not in body

    async def test_perda_por_fase_ignora_cancelados(self, db_conn, client, usuario_adm):
        """
        Cancelado é erro de CRM. Se entrasse aqui, distorceria a leitura de
        onde o funil realmente perde negócio.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        m_perda = await novo_motivo(client, usuario_adm["headers"], "perda", "Preço")
        m_canc = await novo_motivo(
            client, usuario_adm["headers"], "cancelamento", "Lead errado"
        )

        perdida = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await client.post(
            f"/crm/oportunidades/{perdida['id']}/desfecho",
            json={"status": "perdido", "motivo_desfecho_id": m_perda["id"]},
            headers=usuario_adm["headers"],
        )
        cancelada = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await client.post(
            f"/crm/oportunidades/{cancelada['id']}/desfecho",
            json={"status": "cancelado", "motivo_desfecho_id": m_canc["id"]},
            headers=usuario_adm["headers"],
        )

        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        negociacao = next(f for f in body["perda_por_fase"] if f["fase"] == "negociacao")
        assert negociacao["quantidade"] == 1

    async def test_ganhas_no_mes(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{o['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        assert body["ganhas_mes"] == 1

    async def test_por_fase_soma_quantidade_e_ticket(self, db_conn, client, usuario_adm):
        """
        `por_fase` é o que desenha a visão de funil. Se a soma sair errada, a
        faixa sai com a largura errada — e o erro não aparece em lugar nenhum
        além do desenho.
        """
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            fase="negociacao", valor_mensalidade=1000,
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            fase="negociacao", valor_mensalidade=500,
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="lead", valor_mensalidade=300
        )
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        negociacao = next(f for f in body["por_fase"] if f["fase"] == "negociacao")
        assert negociacao["quantidade"] == 2
        assert float(negociacao["ticket"]) == 1500.0

    async def test_filtra_por_busca_textual(self, db_conn, client, usuario_adm):
        """
        O funil e a lista precisam responder à MESMA pergunta quando há filtro
        ativo. Antes, /resumo ignorava tudo e a tela mostrava um funil global
        ao lado de uma lista filtrada.
        """
        alfa = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        beta = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Transportes Beta")
        await nova_oportunidade(
            client, usuario_adm["headers"], alfa["id"],
            fase="negociacao", valor_mensalidade=1000,
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], beta["id"],
            fase="negociacao", valor_mensalidade=7000,
        )

        body = (await client.get(
            "/crm/oportunidades/resumo?q=Alfa", headers=usuario_adm["headers"]
        )).json()
        assert body["abertas"] == 1
        assert float(body["ticket_aberto"]) == 1000.0
        negociacao = next(f for f in body["por_fase"] if f["fase"] == "negociacao")
        assert negociacao["quantidade"] == 1
        assert float(negociacao["ticket"]) == 1000.0

    async def test_filtra_por_envolvido(self, db_conn, client, usuario_adm):
        u = await criar_usuario(db_conn, client, "EV", "resumo-env@teste.com")
        uid = str(await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email=$1", u["email"]
        ))
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": uid, "papel": "EV"}],
        )
        await nova_oportunidade(client, usuario_adm["headers"], conta["id"])

        body = (await client.get(
            f"/crm/oportunidades/resumo?envolvido_id={uid}",
            headers=usuario_adm["headers"],
        )).json()
        assert body["abertas"] == 1
        assert sum(f["quantidade"] for f in body["por_fase"]) == 1

    async def test_sem_filtro_continua_global(self, db_conn, client, usuario_adm):
        """
        Os parâmetros novos são todos opcionais: a chamada sem filtro tem de
        devolver exatamente o que devolvia antes.
        """
        alfa = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        beta = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Transportes Beta")
        await nova_oportunidade(client, usuario_adm["headers"], alfa["id"])
        await nova_oportunidade(client, usuario_adm["headers"], beta["id"])
        body = (await client.get(
            "/crm/oportunidades/resumo", headers=usuario_adm["headers"]
        )).json()
        assert body["abertas"] == 2
        assert sum(f["quantidade"] for f in body["por_fase"]) == 2

    async def test_paradas_respeita_o_filtro(self, db_conn, client, usuario_adm):
        """
        'paradas' tem SQL próprio (subconsulta em oportunidade_eventos) e é o
        ponto mais fácil de esquecer quando se adiciona filtro ao endpoint —
        é a única das quatro consultas em que o placeholder do parâmetro vem
        DEPOIS dos parâmetros do filtro.
        """
        alfa = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        beta = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Transportes Beta")
        await nova_oportunidade(client, usuario_adm["headers"], alfa["id"])
        await nova_oportunidade(client, usuario_adm["headers"], beta["id"])
        # dias_parada=1 com tudo criado agora: ninguém está parado ainda.
        body = (await client.get(
            "/crm/oportunidades/resumo?q=Alfa&dias_parada=1",
            headers=usuario_adm["headers"],
        )).json()
        assert body["paradas"] == 0
        assert body["abertas"] == 1


# ── Listagem ─────────────────────────────────────────────────────────

class TestListagem:
    async def test_paginacao(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        for _ in range(3):
            await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.get(
            "/crm/oportunidades?limit=2", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 3
        assert len(body["itens"]) == 2

    async def test_filtra_por_fase_multipla(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(client, usuario_adm["headers"], conta["id"], fase="lead")
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="negociacao"
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], fase="apresentacao"
        )
        body = (await client.get(
            "/crm/oportunidades?fase=lead&fase=negociacao", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 2

    async def test_filtra_por_envolvido(self, db_conn, client, usuario_adm):
        u = await criar_usuario(db_conn, client, "EV", "filtro-env@teste.com")
        uid = str(await db_conn.fetchval("SELECT id FROM usuarios WHERE email=$1", u["email"]))
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"],
            envolvidos=[{"usuario_id": uid, "papel": "EV"}],
        )
        await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.get(
            f"/crm/oportunidades?envolvido_id={uid}", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1

    async def test_apenas_abertas(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        aberta = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        fechada = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        await client.post(
            f"/crm/oportunidades/{fechada['id']}/desfecho",
            json={"status": "conquistado"},
            headers=usuario_adm["headers"],
        )
        body = (await client.get(
            "/crm/oportunidades?apenas_abertas=true", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1
        assert body["itens"][0]["id"] == aberta["id"]

    async def test_busca_por_numero(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.get(
            f"/crm/oportunidades?q={o['numero']}", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1

    async def test_busca_por_razao_social(self, db_conn, client, usuario_adm):
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        b = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Padaria Beta")
        await nova_oportunidade(client, usuario_adm["headers"], a["id"])
        await nova_oportunidade(client, usuario_adm["headers"], b["id"])
        body = (await client.get(
            "/crm/oportunidades?q=padaria", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1

    async def test_busca_por_cnpj_formatado(self, db_conn, client, usuario_adm):
        """
        A coluna é CHAR(14) sem pontuação. Quem copia o CNPJ de um contrato
        cola com ponto e barra — e tem que achar a mesma oportunidade.
        """
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        b = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Padaria Beta")
        alvo = await nova_oportunidade(client, usuario_adm["headers"], a["id"])
        await nova_oportunidade(client, usuario_adm["headers"], b["id"])
        body = (await client.get(
            f"/crm/oportunidades?q={CNPJ_A}", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1
        assert body["itens"][0]["id"] == alvo["id"]

    async def test_busca_por_cnpj_so_digitos_parcial(self, db_conn, client, usuario_adm):
        """Raiz do CNPJ, sem os dígitos da filial, também acha."""
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        alvo = await nova_oportunidade(client, usuario_adm["headers"], a["id"])
        body = (await client.get(
            "/crm/oportunidades?q=11222333", headers=usuario_adm["headers"]
        )).json()
        assert [i["id"] for i in body["itens"]] == [alvo["id"]]

    async def test_busca_pelo_contato_da_oportunidade(self, db_conn, client, usuario_adm):
        """
        "Aquela negociação da Maria" é como o vendedor lembra do negócio —
        antes de lembrar da razão social ou do número.
        """
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        b = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Padaria Beta")
        contato = (await client.post(
            "/crm/contatos",
            json={"nome": "Maria Aparecida", "conta_id": a["id"]},
            headers=usuario_adm["headers"],
        )).json()
        alvo = await nova_oportunidade(
            client, usuario_adm["headers"], a["id"], contato_id=contato["id"]
        )
        await nova_oportunidade(client, usuario_adm["headers"], b["id"])

        body = (await client.get(
            "/crm/oportunidades?q=aparecida", headers=usuario_adm["headers"]
        )).json()
        assert [i["id"] for i in body["itens"]] == [alvo["id"]]

    async def test_busca_por_contato_da_conta_sem_contato_na_oportunidade(
        self, db_conn, client, usuario_adm
    ):
        """
        Oportunidade sem contato preenchido continua achável pelo nome de
        quem atende naquela empresa — senão o campo em branco esconderia o
        negócio de quem só sabe o nome da pessoa.
        """
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        await client.post(
            "/crm/contatos",
            json={"nome": "Joana Ribeiro", "conta_id": a["id"]},
            headers=usuario_adm["headers"],
        )
        alvo = await nova_oportunidade(client, usuario_adm["headers"], a["id"])

        body = (await client.get(
            "/crm/oportunidades?q=joana", headers=usuario_adm["headers"]
        )).json()
        assert [i["id"] for i in body["itens"]] == [alvo["id"]]

    async def test_busca_por_nome_fantasia(self, db_conn, client, usuario_adm):
        """A empresa é conhecida pelo fantasia; a razão social só aparece na nota."""
        conta = (await client.post(
            "/crm/contas",
            json={
                "razao_social": "Comercio de Alimentos Sigma LTDA",
                "nome_fantasia": "Padaria do Ze",
                "cnpj": CNPJ_C,
            },
            headers=usuario_adm["headers"],
        )).json()
        alvo = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.get(
            "/crm/oportunidades?q=padaria do ze", headers=usuario_adm["headers"]
        )).json()
        assert [i["id"] for i in body["itens"]] == [alvo["id"]]

    async def test_busca_textual_vale_no_resumo(self, db_conn, client, usuario_adm):
        """
        Os KPIs do topo usam o MESMO `_montar_filtros`. Se a busca por contato
        valesse só na lista, o funil mostraria um total e a lista, outro.
        """
        a = await nova_conta(client, usuario_adm["headers"], CNPJ_A, "Metalurgica Alfa")
        b = await nova_conta(client, usuario_adm["headers"], CNPJ_B, "Padaria Beta")
        contato = (await client.post(
            "/crm/contatos",
            json={"nome": "Maria Aparecida", "conta_id": a["id"]},
            headers=usuario_adm["headers"],
        )).json()
        await nova_oportunidade(
            client, usuario_adm["headers"], a["id"], contato_id=contato["id"]
        )
        await nova_oportunidade(client, usuario_adm["headers"], b["id"])

        body = (await client.get(
            "/crm/oportunidades/resumo?q=aparecida", headers=usuario_adm["headers"]
        )).json()
        assert body["abertas"] == 1

    async def test_fase_invalida_no_filtro(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/crm/oportunidades?fase=inventada", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_ordenar_por_invalido(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/crm/oportunidades?ordenar_por=numero;DROP", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_aparece_na_aba_da_conta(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], valor_mensalidade=900
        )
        detalhe = (await client.get(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert len(detalhe["oportunidades"]) == 1
        assert detalhe["qtd_oportunidades_ativas"] == 1


# ── Edição ───────────────────────────────────────────────────────────

class TestEditar:
    async def test_patch_parcial(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(
            client, usuario_adm["headers"], conta["id"], descricao="Original"
        )
        body = (await client.patch(
            f"/crm/oportunidades/{o['id']}",
            json={"valor_mensalidade": 3200},
            headers=usuario_adm["headers"],
        )).json()
        assert float(body["valor_mensalidade"]) == 3200.0
        assert body["descricao"] == "Original"

    async def test_patch_nao_muda_fase_nem_status(self, db_conn, client, usuario_adm):
        """Fase e status têm endpoints próprios, que aplicam as regras."""
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        body = (await client.patch(
            f"/crm/oportunidades/{o['id']}",
            json={"fase": "negociacao", "status": "perdido", "descricao": "X"},
            headers=usuario_adm["headers"],
        )).json()
        assert body["fase"] == "suspect"
        assert body["status"] == "ativa"
        assert body["descricao"] == "X"

    async def test_ativa_nao_fica_sem_temperatura(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}",
            json={"temperatura": None},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_patch_vazio(self, db_conn, client, usuario_adm):
        conta = await nova_conta(client, usuario_adm["headers"])
        o = await nova_oportunidade(client, usuario_adm["headers"], conta["id"])
        resp = await client.patch(
            f"/crm/oportunidades/{o['id']}", json={}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422


# ── Usuários para o picker ───────────────────────────────────────────

class TestUsuariosParaPicker:
    async def test_lista_sem_dados_sensiveis(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/dominio/usuarios", headers=usuario_adm["headers"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) >= 1
        # Nada de e-mail nem senha_hash no payload de um picker.
        assert set(body[0].keys()) == {"id", "nome", "cargo"}

    async def test_filtra_por_cargo(self, db_conn, client, usuario_adm):
        await criar_usuario(db_conn, client, "EV", "ev-picker@teste.com")
        resp = await client.get(
            "/crm/dominio/usuarios?cargo=EV", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        assert body[0]["cargo"] == "EV"

    async def test_filtra_por_nome(self, db_conn, client, usuario_adm):
        await criar_usuario(db_conn, client, "EV", "ev-nome@teste.com")
        body = (await client.get(
            "/crm/dominio/usuarios?q=Test EV", headers=usuario_adm["headers"]
        )).json()
        assert len(body) == 1

    async def test_nao_conflita_com_a_rota_curinga_de_dominio(
        self, db_conn, client, usuario_adm
    ):
        """
        Regressão: /{tabela} declarado antes de /usuarios fazia o FastAPI
        tratar "usuarios" como nome de tabela e devolver 404.
        """
        assert (await client.get(
            "/crm/dominio/usuarios", headers=usuario_adm["headers"]
        )).status_code == 200
        assert (await client.get(
            "/crm/dominio/verticais", headers=usuario_adm["headers"]
        )).status_code == 200
        assert (await client.get(
            "/crm/dominio/inventada", headers=usuario_adm["headers"]
        )).status_code == 404

    async def test_operacional_pode_listar(self, db_conn, client):
        """Escolher envolvidos é operar o CRM, não administrar acessos."""
        u = await criar_usuario(db_conn, client, "SDR", "sdr-picker@teste.com")
        resp = await client.get("/crm/dominio/usuarios", headers=u["headers"])
        assert resp.status_code == 200


# ── Permissões ───────────────────────────────────────────────────────

class TestPermissoes:
    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM", "EC", "SDR", "EV", "EP"])
    async def test_todo_cargo_valido_acessa(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-opp@teste.com")
        resp = await client.get("/crm/oportunidades", headers=u["headers"])
        assert resp.status_code == 200

    @pytest.mark.parametrize("cargo", ["Gerente", "Hunter", "Farmer"])
    async def test_cargo_extinto_403(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-opp@teste.com")
        resp = await client.get("/crm/oportunidades", headers=u["headers"])
        assert resp.status_code == 403

    async def test_sem_token_401(self, db_conn, client):
        assert (await client.get("/crm/oportunidades")).status_code == 401


# ── Montagem do filtro textual (sem banco) ───────────────────────────
#
# Rodam no pytest local do Windows: `_montar_filtros` é função pura. O que
# elas seguram é a decisão de quando o termo digitado TAMBÉM vale como CNPJ.

class TestMontagemDaBuscaTextual:
    def _filtro(self, q):
        return crm_oportunidades._montar_filtros(
            q, None, None, None, None, None, None, None, None, False,
        )

    def test_cnpj_formatado_vira_digitos(self):
        """A coluna guarda só dígitos; comparar o texto digitado nunca casaria."""
        _, params = self._filtro(CNPJ_A)
        assert params[1] == "%11222333000181%"

    def test_termo_curto_nao_vira_busca_de_cnpj(self):
        """
        "22" casaria com quase toda a base pelo documento e afogaria o
        resultado que o usuário procurava pelo nome.
        """
        _, params = self._filtro("22")
        assert params[1] is None

    def test_termo_sem_digito_nao_consulta_cnpj(self):
        _, params = self._filtro("Metalurgica")
        assert params[0] == "%Metalurgica%"
        assert params[1] is None

    def test_um_unico_where_para_todos_os_caminhos(self):
        """
        Número, razão social, fantasia, descrição, CNPJ e contato entram como
        UMA cláusula em OR. Quebrada em várias, viraria AND e a busca não
        acharia nada.
        """
        where, _ = self._filtro("alfa")
        assert len(where) == 1
        for campo in ("o.numero", "c.razao_social", "c.nome_fantasia",
                      "o.descricao", "c.cnpj", "ct_o.nome", "ct_q.nome"):
            assert campo in where[0]
