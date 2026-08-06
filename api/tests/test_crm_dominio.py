"""
HIPO — Testes das listas de domínio do CRM.

O ponto sensível aqui é a idempotência: o combobox cria "Metalúrgica" e, na
próxima vez, alguém digita "metalurgica". Sem deduplicação por slug, a lista
vira lixo em semanas.
"""
import pytest

from tests.conftest import criar_usuario

LISTAS = ["verticais", "origens", "concorrentes"]


class TestCriarItem:
    @pytest.mark.parametrize("lista", LISTAS)
    async def test_cria_item(self, db_conn, client, usuario_adm, lista):
        resp = await client.post(
            f"/crm/dominio/{lista}", json={"nome": "Metalúrgica"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["nome"] == "Metalúrgica"
        assert body["slug"] == "metalurgica"

    @pytest.mark.parametrize("variacao", [
        "metalurgica", "METALÚRGICA", "  Metalúrgica  ", "Metalúrgica.",
    ])
    async def test_variacoes_devolvem_o_mesmo_registro(
        self, db_conn, client, usuario_adm, variacao
    ):
        primeiro = (await client.post(
            "/crm/dominio/verticais", json={"nome": "Metalúrgica"},
            headers=usuario_adm["headers"],
        )).json()
        segundo = (await client.post(
            "/crm/dominio/verticais", json={"nome": variacao},
            headers=usuario_adm["headers"],
        )).json()
        assert segundo["id"] == primeiro["id"]

    async def test_nome_original_e_preservado_na_primeira_criacao(
        self, db_conn, client, usuario_adm
    ):
        """O slug deduplica, mas quem aparece na tela é o nome como digitado."""
        await client.post(
            "/crm/dominio/verticais", json={"nome": "Metalúrgica"},
            headers=usuario_adm["headers"],
        )
        segundo = (await client.post(
            "/crm/dominio/verticais", json={"nome": "METALURGICA"},
            headers=usuario_adm["headers"],
        )).json()
        assert segundo["nome"] == "Metalúrgica"

    async def test_espacos_internos_sao_colapsados(self, db_conn, client, usuario_adm):
        body = (await client.post(
            "/crm/dominio/verticais", json={"nome": "Construção   Civil"},
            headers=usuario_adm["headers"],
        )).json()
        assert body["nome"] == "Construção Civil"
        assert body["slug"] == "construcao-civil"

    async def test_nome_so_com_pontuacao_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/dominio/verticais", json={"nome": "///"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_nome_vazio_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/dominio/verticais", json={"nome": ""},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_lista_desconhecida_404(self, db_conn, client, usuario_adm):
        """A whitelist é o que impede nome de tabela vindo da URL na query."""
        resp = await client.post(
            "/crm/dominio/usuarios", json={"nome": "x"}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 404


class TestListar:
    async def test_lista_ordenada_por_nome(self, db_conn, client, usuario_adm):
        for nome in ["Serviços", "Construção", "Alimentação"]:
            await client.post(
                "/crm/dominio/verticais", json={"nome": nome},
                headers=usuario_adm["headers"],
            )
        nomes = [v["nome"] for v in (
            await client.get("/crm/dominio/verticais", headers=usuario_adm["headers"])
        ).json()]
        assert nomes == sorted(nomes)

    async def test_lista_nasce_vazia(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/dominio/verticais", headers=usuario_adm["headers"])
        assert resp.json() == []

    async def test_filtra_por_trecho(self, db_conn, client, usuario_adm):
        for nome in ["Metalúrgica", "Construção"]:
            await client.post(
                "/crm/dominio/verticais", json={"nome": nome},
                headers=usuario_adm["headers"],
            )
        resp = await client.get(
            "/crm/dominio/verticais?q=metal", headers=usuario_adm["headers"]
        )
        assert len(resp.json()) == 1

    async def test_lista_desconhecida_404(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/dominio/contas", headers=usuario_adm["headers"])
        assert resp.status_code == 404


class TestMotivosDesfecho:
    async def test_cria_motivo_de_perda(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/dominio/motivos/perda", json={"nome": "Preço"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["tipo"] == "perda"

    async def test_listas_de_perda_e_cancelamento_sao_separadas(
        self, db_conn, client, usuario_adm
    ):
        """
        Mesmo slug em tipos diferentes coexiste — o UNIQUE é (tipo, slug).
        Misturar as duas listas faria o relatório somar motivo comercial com
        erro de cadastro.
        """
        p = (await client.post(
            "/crm/dominio/motivos/perda", json={"nome": "Duplicado"},
            headers=usuario_adm["headers"],
        )).json()
        c = (await client.post(
            "/crm/dominio/motivos/cancelamento", json={"nome": "Duplicado"},
            headers=usuario_adm["headers"],
        )).json()
        assert p["id"] != c["id"]

        perdas = (await client.get(
            "/crm/dominio/motivos/perda", headers=usuario_adm["headers"]
        )).json()
        assert len(perdas) == 1
        assert perdas[0]["tipo"] == "perda"

    async def test_idempotente_dentro_do_mesmo_tipo(self, db_conn, client, usuario_adm):
        primeiro = (await client.post(
            "/crm/dominio/motivos/perda", json={"nome": "Lead errado"},
            headers=usuario_adm["headers"],
        )).json()
        segundo = (await client.post(
            "/crm/dominio/motivos/perda", json={"nome": "LEAD ERRADO"},
            headers=usuario_adm["headers"],
        )).json()
        assert primeiro["id"] == segundo["id"]

    async def test_tipo_invalido_404(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/dominio/motivos/inventado", json={"nome": "x"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404


class TestPermissoesDominio:
    @pytest.mark.parametrize("cargo", ["EC", "SDR", "EV", "EP"])
    async def test_operacional_pode_criar(self, db_conn, client, cargo):
        """
        Decidido: qualquer usuário do módulo cria entrada de domínio pelo
        combobox. Exigir ADM travaria o cadastro no meio do formulário.
        """
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-dom@teste.com")
        resp = await client.post(
            "/crm/dominio/verticais", json={"nome": "Saúde"}, headers=u["headers"]
        )
        assert resp.status_code == 200

    async def test_cargo_extinto_403(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Gerente", "ger-dom@teste.com")
        resp = await client.get("/crm/dominio/verticais", headers=u["headers"])
        assert resp.status_code == 403

    async def test_sem_token_401(self, db_conn, client):
        resp = await client.get("/crm/dominio/verticais")
        assert resp.status_code == 401
