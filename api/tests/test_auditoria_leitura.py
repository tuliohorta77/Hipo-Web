"""
HIPO -- trilha de leitura de dado pessoal (032).

O que esta suite protege:

  1. Toda rota de ROTAS_INSTRUMENTADAS existe e grava, com os ids que
     devolveu -- e nao com o conteudo.
  2. "Quem leu o registro X" responde pela rota de gestao.
  3. Falha ao gravar a trilha nao derruba a leitura.
"""
import json
import uuid

import pytest

from main import app
from services import auditoria
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"


async def nova_conta(client, h, cnpj=CNPJ_A):
    r = await client.post(
        "/crm/contas", json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": cnpj}, headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def novo_contato(client, h, conta_id=None, nome="Maria RH", **extra):
    corpo = {"nome": nome, **extra}
    if conta_id:
        corpo["conta_id"] = conta_id
    r = await client.post("/crm/contatos", json=corpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def leituras(db_conn, rota=None):
    sql = "SELECT * FROM leituras_sensiveis"
    args = []
    if rota:
        sql += " WHERE rota = $1"
        args.append(rota)
    sql += " ORDER BY id"
    linhas = await db_conn.fetch(sql, *args)
    saida = []
    for r in linhas:
        d = dict(r)
        d["contexto"] = json.loads(d["contexto"]) if isinstance(d["contexto"], str) else d["contexto"]
        d["registro_ids"] = [str(i) for i in d["registro_ids"]]
        saida.append(d)
    return saida


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = await nova_conta(client, h)
    contato = await novo_contato(
        client, h, conta_id=conta["id"], email="maria@alfa.com", telefone="11999990000",
    )
    me = (await client.get("/auth/me", headers=h)).json()
    # O cadastro acima nao e leitura; comeca do zero.
    await db_conn.execute("DELETE FROM leituras_sensiveis")
    return {"h": h, "conta": conta, "contato": contato, "uid": me["id"]}


class TestCobertura:
    def test_toda_rota_listada_existe(self):
        existentes = {
            (m, r.path)
            for r in app.routes
            for m in getattr(r, "methods", set()) or set()
        }
        faltando = set(auditoria.ROTAS_INSTRUMENTADAS) - existentes
        assert not faltando, f"rotas instrumentadas que nao existem mais: {faltando}"


class TestContatos:
    async def test_detalhe_grava_o_id(self, db_conn, client, cenario, usuario_adm):
        r = await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=cenario["h"])
        assert r.status_code == 200
        [l] = await leituras(db_conn)
        assert l["recurso"] == "contato"
        assert l["rota"] == "/crm/contatos/{contato_id}"
        assert l["registro_ids"] == [cenario["contato"]["id"]]
        assert str(l["usuario_id"]) == cenario["uid"]
        assert l["usuario_email"] == usuario_adm["email"]
        assert l["cargo"] == "ADM"

    async def test_lista_grava_os_ids_da_pagina(self, db_conn, client, cenario):
        outro = await novo_contato(client, cenario["h"], nome="Joao Compras")
        await db_conn.execute("DELETE FROM leituras_sensiveis")
        r = await client.get("/crm/contatos", params={"q": "a"}, headers=cenario["h"])
        assert r.status_code == 200
        [l] = await leituras(db_conn, "/crm/contatos")
        assert set(l["registro_ids"]) == {cenario["contato"]["id"], outro["id"]}
        assert l["contexto"]["q"] == "a"

    async def test_busca_grava_termo_e_resultado(self, db_conn, client, cenario):
        r = await client.get("/crm/contatos/busca", params={"q": "Maria"}, headers=cenario["h"])
        assert r.status_code == 200
        [l] = await leituras(db_conn, "/crm/contatos/busca")
        assert l["registro_ids"] == [cenario["contato"]["id"]]
        assert l["contexto"]["q"] == "Maria"

    async def test_busca_vazia_tambem_grava(self, db_conn, client, cenario):
        await client.get("/crm/contatos/busca", params={"q": "zzzz"}, headers=cenario["h"])
        [l] = await leituras(db_conn, "/crm/contatos/busca")
        assert l["registro_ids"] == []

    async def test_por_alvo_da_conta(self, db_conn, client, cenario):
        r = await client.get(
            "/crm/contatos/por-alvo", params={"conta_id": cenario["conta"]["id"]},
            headers=cenario["h"],
        )
        assert r.status_code == 200
        [l] = await leituras(db_conn, "/crm/contatos/por-alvo")
        assert l["registro_ids"] == [cenario["contato"]["id"]]
        assert l["contexto"]["conta_id"] == cenario["conta"]["id"]

    async def test_duplicatas_nao_guarda_o_dado_digitado(self, db_conn, client, cenario):
        r = await client.get(
            "/crm/contatos/duplicatas", params={"email": "maria@alfa.com"},
            headers=cenario["h"],
        )
        assert r.status_code == 200
        [l] = await leituras(db_conn, "/crm/contatos/duplicatas")
        assert l["registro_ids"] == [cenario["contato"]["id"]]
        assert "maria@alfa.com" not in json.dumps(l["contexto"])
        assert l["contexto"] == {"por_email": True, "por_telefone": False}

    async def test_conteudo_nunca_vai_para_a_trilha(self, db_conn, client, cenario):
        await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=cenario["h"])
        await client.get("/crm/contatos", headers=cenario["h"])
        bruto = await db_conn.fetchval(
            "SELECT string_agg(row_to_json(l)::text, ' ') FROM leituras_sensiveis l"
        )
        assert "11999990000" not in bruto
        assert "maria@alfa.com" not in bruto

    async def test_comite_da_oportunidade(self, db_conn, client, cenario):
        h = cenario["h"]
        opp = (await client.post(
            "/crm/oportunidades", json={"conta_id": cenario["conta"]["id"]}, headers=h,
        )).json()
        add = await client.post(
            f"/crm/oportunidades/{opp['id']}/contatos",
            json={"contato_id": cenario["contato"]["id"]}, headers=h,
        )
        assert add.status_code == 201, add.text
        await db_conn.execute("DELETE FROM leituras_sensiveis")

        r = await client.get(f"/crm/oportunidades/{opp['id']}/contatos", headers=h)
        assert r.status_code == 200
        [l] = await leituras(db_conn, "/crm/oportunidades/{oportunidade_id}/contatos")
        assert l["registro_ids"] == [cenario["contato"]["id"]]
        assert l["contexto"]["oportunidade_id"] == opp["id"]

    async def test_404_nao_grava(self, db_conn, client, cenario):
        r = await client.get(f"/crm/contatos/{uuid.uuid4()}", headers=cenario["h"])
        assert r.status_code == 404
        assert await leituras(db_conn) == []

    async def test_escrita_nao_e_leitura(self, db_conn, client, cenario):
        await client.patch(
            f"/crm/contatos/{cenario['contato']['id']}", json={"nome": "Maria R."},
            headers=cenario["h"],
        )
        assert await leituras(db_conn) == []


class TestSocios:
    async def _socio(self, db_conn, conta_id):
        return await db_conn.fetchval(
            """
            INSERT INTO conta_socios (conta_id, nome, nome_normalizado,
                                      documento_mascarado, fonte)
            VALUES ($1, 'JOSE DA SILVA', 'JOSE DA SILVA', '***456789**', 'brasilapi')
            RETURNING id
            """,
            uuid.UUID(conta_id),
        )

    async def test_socios_da_conta(self, db_conn, client, cenario):
        socio_id = await self._socio(db_conn, cenario["conta"]["id"])
        r = await client.get(
            f"/crm/enriquecimento/contas/{cenario['conta']['id']}/socios",
            headers=cenario["h"],
        )
        assert r.status_code == 200, r.text
        [l] = await leituras(db_conn)
        assert l["recurso"] == "socio"
        assert l["registro_ids"] == [str(socio_id)]

    async def test_busca_reversa_grava_o_nome_sem_o_documento(
        self, db_conn, client, cenario
    ):
        await self._socio(db_conn, cenario["conta"]["id"])
        r = await client.get(
            "/crm/enriquecimento/socios/empresas",
            params={"nome": "Jose da Silva", "documento": "***456789**"},
            headers=cenario["h"],
        )
        assert r.status_code == 200, r.text
        [l] = await leituras(db_conn, "/crm/enriquecimento/socios/empresas")
        assert l["contexto"]["nome"] == "Jose da Silva"
        assert l["contexto"]["com_documento"] is True
        assert "456789" not in json.dumps(l["contexto"])


class TestConsultaDaTrilha:
    async def test_quem_leu_este_registro(self, db_conn, client, cenario):
        sdr = await criar_usuario(db_conn, client, "SDR")
        await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=sdr["headers"])
        await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=cenario["h"])
        outro = await novo_contato(client, cenario["h"], nome="Outro")
        await client.get(f"/crm/contatos/{outro['id']}", headers=cenario["h"])

        r = await client.get(
            "/telemetria/leituras-sensiveis",
            params={"registro_id": cenario["contato"]["id"]},
            headers=cenario["h"],
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["total"] == 2
        assert [i["cargo"] for i in corpo["itens"]] == ["ADM", "SDR"]
        assert corpo["itens"][1]["usuario_nome"] == "Test SDR"

    async def test_o_que_esta_pessoa_leu(self, db_conn, client, cenario):
        sdr = await criar_usuario(db_conn, client, "SDR")
        await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=sdr["headers"])
        me = (await client.get("/auth/me", headers=sdr["headers"])).json()
        r = await client.get(
            "/telemetria/leituras-sensiveis", params={"usuario_id": me["id"]},
            headers=cenario["h"],
        )
        assert r.json()["total"] == 1

    async def test_intervalo_invertido(self, db_conn, client, cenario):
        r = await client.get(
            "/telemetria/leituras-sensiveis",
            params={"desde": "2026-10-10", "ate": "2026-10-01"},
            headers=cenario["h"],
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("cargo", ["SDR", "EV", "EC", "EP"])
    async def test_operacional_nao_ve(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        r = await client.get("/telemetria/leituras-sensiveis", headers=u["headers"])
        assert r.status_code == 403


class TestFalhaNaoDerruba:
    async def test_tabela_fora_a_leitura_sai(self, db_conn, client, cenario, monkeypatch):
        original = auditoria._contexto_serializavel

        def quebra(*a, **k):
            raise RuntimeError("simulando falha na trilha")

        monkeypatch.setattr(auditoria, "_contexto_serializavel", quebra)
        r = await client.get(f"/crm/contatos/{cenario['contato']['id']}", headers=cenario["h"])
        assert r.status_code == 200
        assert await leituras(db_conn) == []
        monkeypatch.setattr(auditoria, "_contexto_serializavel", original)

    async def test_falha_dentro_de_transacao_nao_envenena_a_request(self, db_conn):
        """
        O INSERT roda em savepoint: o erro dele nao aborta a transacao de
        quem chamou.
        """
        async with db_conn.transaction():
            # FK quebrada de proposito -> erro no INSERT da trilha.
            await auditoria.registrar_leitura(
                db_conn, None, {"id": uuid.uuid4(), "email": "x@y"},
                "contato", [],
            )
            assert await db_conn.fetchval("SELECT 1") == 1


class TestIdsValidos:
    def test_ignora_lixo_e_repetidos(self):
        u = uuid.uuid4()
        assert auditoria.ids_validos([None, str(u), u, "nao-e-uuid"]) == [u]

    def test_teto(self):
        assert len(auditoria.ids_validos(uuid.uuid4() for _ in range(900))) == auditoria.MAX_IDS
