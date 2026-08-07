"""
HIPO — Testes do router /crm/contatos.

Foco nas três decisões que dão identidade ao módulo:
  1. N:N de verdade — a mesma pessoa em mais de uma conta, cargo por vínculo
  2. duplicata sugere, não bloqueia (ao contrário do CNPJ)
  3. um principal por conta, com troca atômica
"""
import uuid

import pytest

from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_B = "34.028.316/0001-03"


# ── Helpers ──────────────────────────────────────────────────────────

async def criar_conta(client, headers, cnpj=CNPJ_A, razao="Metalurgica Alfa LTDA"):
    resp = await client.post(
        "/crm/contas", json={"razao_social": razao, "cnpj": cnpj}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def criar_contato(client, headers, nome="Maria Souza", **extra):
    corpo = {"nome": nome}
    corpo.update(extra)
    resp = await client.post("/crm/contatos", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Criação ──────────────────────────────────────────────────────────

class TestCriar:
    async def test_cria_contato_solto(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"])
        assert c["nome"] == "Maria Souza"
        assert c["ativo"] is True
        assert c["contas"] == []
        assert c["qtd_contas"] == 0

    async def test_cria_ja_vinculado_a_uma_conta(self, db_conn, client, usuario_adm):
        """Fluxo do botão '+' do EntityPicker dentro do formulário da conta."""
        conta = await criar_conta(client, usuario_adm["headers"])
        c = await criar_contato(
            client, usuario_adm["headers"],
            conta_id=conta["id"], cargo="Diretora de RH", principal=True,
        )
        assert c["qtd_contas"] == 1
        assert c["contas"][0]["conta_id"] == conta["id"]
        assert c["contas"][0]["cargo"] == "Diretora de RH"
        assert c["contas"][0]["principal"] is True

    async def test_nome_vazio_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contatos", json={"nome": "   "}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_email_normalizado_para_minuscula(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"], email="Maria@Empresa.COM")
        assert c["email"] == "maria@empresa.com"

    async def test_email_sem_arroba_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "email": "invalido"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_conta_inexistente_recusada(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": str(uuid.uuid4())},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_conta_invalida_nao_deixa_contato_orfao(self, db_conn, client, usuario_adm):
        """Criar + vincular é uma transação: falhou o vínculo, não sobra contato."""
        antes = await db_conn.fetchval("SELECT count(*) FROM contatos")
        await client.post(
            "/crm/contatos",
            json={"nome": "Fantasma", "conta_id": str(uuid.uuid4())},
            headers=usuario_adm["headers"],
        )
        assert await db_conn.fetchval("SELECT count(*) FROM contatos") == antes

    async def test_registra_o_autor(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"])
        autor = await db_conn.fetchval(
            "SELECT criado_por FROM contatos WHERE id = $1", uuid.UUID(c["id"])
        )
        esperado = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1", usuario_adm["email"]
        )
        assert autor == esperado


# ── N:N ──────────────────────────────────────────────────────────────

class TestVinculosNaN:
    async def test_mesmo_contato_em_duas_contas(self, db_conn, client, usuario_adm):
        """O caso que motivou o N:N: sócio de duas empresas, contador de várias."""
        c1 = await criar_conta(client, usuario_adm["headers"], CNPJ_A, "Alfa LTDA")
        c2 = await criar_conta(client, usuario_adm["headers"], CNPJ_B, "Beta SA")
        contato = await criar_contato(
            client, usuario_adm["headers"], conta_id=c1["id"], cargo="Sócio"
        )

        resp = await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": c2["id"], "cargo": "Diretor"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["qtd_contas"] == 2

    async def test_cargo_pertence_ao_vinculo_nao_a_pessoa(self, db_conn, client, usuario_adm):
        """A mesma pessoa pode ser Sócio numa empresa e Diretor em outra."""
        c1 = await criar_conta(client, usuario_adm["headers"], CNPJ_A, "Alfa LTDA")
        c2 = await criar_conta(client, usuario_adm["headers"], CNPJ_B, "Beta SA")
        contato = await criar_contato(
            client, usuario_adm["headers"], conta_id=c1["id"], cargo="Sócio"
        )
        body = (await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": c2["id"], "cargo": "Diretor"},
            headers=usuario_adm["headers"],
        )).json()

        cargos = {c["razao_social"]: c["cargo"] for c in body["contas"]}
        assert cargos == {"Alfa LTDA": "Sócio", "Beta SA": "Diretor"}

    async def test_vinculo_duplicado_recusado(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(client, usuario_adm["headers"], conta_id=conta["id"])
        resp = await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 409

    async def test_revincular_reativa_em_vez_de_recusar(self, db_conn, client, usuario_adm):
        """Alguém que saiu e voltou para a empresa não é um conflito."""
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(
            client, usuario_adm["headers"], conta_id=conta["id"], cargo="Antigo"
        )
        await client.delete(
            f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}",
            headers=usuario_adm["headers"],
        )
        resp = await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": conta["id"], "cargo": "Novo"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["contas"][0]["cargo"] == "Novo"
        assert resp.json()["qtd_contas"] == 1

    async def test_desvincular_preserva_o_contato(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(client, usuario_adm["headers"], conta_id=conta["id"])
        body = (await client.delete(
            f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}",
            headers=usuario_adm["headers"],
        )).json()
        assert body["ativo"] is True
        assert body["qtd_contas"] == 0

    async def test_desvincular_duas_vezes_404(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(client, usuario_adm["headers"], conta_id=conta["id"])
        url = f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}"
        await client.delete(url, headers=usuario_adm["headers"])
        assert (await client.delete(url, headers=usuario_adm["headers"])).status_code == 404

    async def test_conta_aparece_com_seus_contatos(self, db_conn, client, usuario_adm):
        """O detalhe da conta (Sprint 1) precisa enxergar o que a Sprint 2 criou."""
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(
            client, usuario_adm["headers"], nome="Maria",
            conta_id=conta["id"], cargo="RH", principal=True,
        )
        detalhe = (await client.get(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert len(detalhe["contatos"]) == 1
        assert detalhe["contatos"][0]["nome"] == "Maria"
        assert detalhe["contatos"][0]["cargo"] == "RH"
        assert detalhe["contatos"][0]["principal"] is True

    async def test_contato_desvinculado_some_da_conta(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(client, usuario_adm["headers"], conta_id=conta["id"])
        await client.delete(
            f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}",
            headers=usuario_adm["headers"],
        )
        detalhe = (await client.get(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert detalhe["contatos"] == []


# ── Contato principal ────────────────────────────────────────────────

class TestPrincipal:
    async def test_promover_rebaixa_o_anterior(self, db_conn, client, usuario_adm):
        """
        Sem a troca atômica, o índice único parcial rejeitaria o UPDATE e o
        usuário veria um erro de constraint ao clicar em "tornar principal".
        """
        conta = await criar_conta(client, usuario_adm["headers"])
        a = await criar_contato(
            client, usuario_adm["headers"], nome="Ana",
            conta_id=conta["id"], principal=True,
        )
        b = await criar_contato(client, usuario_adm["headers"], nome="Bruno")
        await client.post(
            f"/crm/contatos/{b['id']}/vinculos",
            json={"conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )

        resp = await client.patch(
            f"/crm/contatos/{b['id']}/vinculos/{conta['id']}",
            json={"principal": True},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200

        principais = await db_conn.fetch(
            "SELECT contato_id FROM conta_contatos WHERE conta_id = $1 AND principal",
            uuid.UUID(conta["id"]),
        )
        assert len(principais) == 1
        assert str(principais[0]["contato_id"]) == b["id"]

    async def test_vincular_ja_como_principal_rebaixa_o_anterior(
        self, db_conn, client, usuario_adm
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(
            client, usuario_adm["headers"], nome="Ana",
            conta_id=conta["id"], principal=True,
        )
        b = await criar_contato(client, usuario_adm["headers"], nome="Bruno")
        await client.post(
            f"/crm/contatos/{b['id']}/vinculos",
            json={"conta_id": conta["id"], "principal": True},
            headers=usuario_adm["headers"],
        )
        qtd = await db_conn.fetchval(
            "SELECT count(*) FROM conta_contatos WHERE conta_id = $1 AND principal",
            uuid.UUID(conta["id"]),
        )
        assert qtd == 1

    async def test_principal_e_por_conta_nao_por_pessoa(self, db_conn, client, usuario_adm):
        """A mesma pessoa pode ser principal em duas contas ao mesmo tempo."""
        c1 = await criar_conta(client, usuario_adm["headers"], CNPJ_A, "Alfa")
        c2 = await criar_conta(client, usuario_adm["headers"], CNPJ_B, "Beta")
        contato = await criar_contato(
            client, usuario_adm["headers"], conta_id=c1["id"], principal=True
        )
        body = (await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": c2["id"], "principal": True},
            headers=usuario_adm["headers"],
        )).json()
        assert all(c["principal"] for c in body["contas"])

    async def test_desvincular_limpa_a_flag_de_principal(self, db_conn, client, usuario_adm):
        """
        Se a flag ficasse, o próximo a ser promovido bateria no índice único.
        """
        conta = await criar_conta(client, usuario_adm["headers"])
        a = await criar_contato(
            client, usuario_adm["headers"], nome="Ana",
            conta_id=conta["id"], principal=True,
        )
        await client.delete(
            f"/crm/contatos/{a['id']}/vinculos/{conta['id']}",
            headers=usuario_adm["headers"],
        )
        b = await criar_contato(
            client, usuario_adm["headers"], nome="Bruno",
            conta_id=conta["id"], principal=True,
        )
        assert b["contas"][0]["principal"] is True

    async def test_vinculo_inexistente_404(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = await criar_contato(client, usuario_adm["headers"])
        resp = await client.patch(
            f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}",
            json={"principal": True},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404


# ── Duplicatas ───────────────────────────────────────────────────────

class TestDuplicatas:
    async def test_acha_por_email(self, db_conn, client, usuario_adm):
        await criar_contato(client, usuario_adm["headers"], email="maria@alfa.com")
        resp = await client.get(
            "/crm/contatos/duplicatas?email=maria@alfa.com", headers=usuario_adm["headers"]
        )
        assert len(resp.json()) == 1
        assert resp.json()[0]["motivo"] == "email"

    async def test_email_case_insensitive(self, db_conn, client, usuario_adm):
        await criar_contato(client, usuario_adm["headers"], email="maria@alfa.com")
        resp = await client.get(
            "/crm/contatos/duplicatas?email=MARIA@ALFA.COM", headers=usuario_adm["headers"]
        )
        assert len(resp.json()) == 1

    async def test_acha_por_telefone(self, db_conn, client, usuario_adm):
        await criar_contato(client, usuario_adm["headers"], telefone="11999990000")
        resp = await client.get(
            "/crm/contatos/duplicatas?telefone=11999990000", headers=usuario_adm["headers"]
        )
        assert resp.json()[0]["motivo"] == "telefone"

    async def test_traz_as_contas_do_candidato(self, db_conn, client, usuario_adm):
        """
        O nome sozinho não ajuda a decidir. Saber em qual empresa a pessoa já
        está é o que diz se é a mesma pessoa ou um homônimo.
        """
        conta = await criar_conta(client, usuario_adm["headers"], razao="Alfa LTDA")
        await criar_contato(
            client, usuario_adm["headers"], email="maria@alfa.com", conta_id=conta["id"]
        )
        resp = await client.get(
            "/crm/contatos/duplicatas?email=maria@alfa.com", headers=usuario_adm["headers"]
        )
        assert resp.json()[0]["contas"] == ["Alfa LTDA"]

    async def test_nao_bloqueia_a_criacao(self, db_conn, client, usuario_adm):
        """
        Diferente do CNPJ: e-mail e telefone corporativos são legitimamente
        compartilhados. Duplicata é sugestão, não erro.
        """
        await criar_contato(client, usuario_adm["headers"], email="contato@alfa.com")
        resp = await client.post(
            "/crm/contatos",
            json={"nome": "Outra Pessoa", "email": "contato@alfa.com"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 201

    async def test_sem_parametro_devolve_vazio(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/contatos/duplicatas", headers=usuario_adm["headers"])
        assert resp.json() == []

    async def test_inativo_nao_aparece(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"], email="maria@alfa.com")
        await client.delete(f"/crm/contatos/{c['id']}", headers=usuario_adm["headers"])
        resp = await client.get(
            "/crm/contatos/duplicatas?email=maria@alfa.com", headers=usuario_adm["headers"]
        )
        assert resp.json() == []


# ── Busca (lupa do EntityPicker) ─────────────────────────────────────

class TestBusca:
    async def test_acha_por_nome(self, db_conn, client, usuario_adm):
        await criar_contato(client, usuario_adm["headers"], nome="Maria Souza")
        resp = await client.get("/crm/contatos/busca?q=souza", headers=usuario_adm["headers"])
        assert len(resp.json()) == 1

    async def test_acha_por_email_e_telefone(self, db_conn, client, usuario_adm):
        await criar_contato(
            client, usuario_adm["headers"], email="maria@alfa.com", telefone="11999990000"
        )
        assert len((await client.get(
            "/crm/contatos/busca?q=alfa.com", headers=usuario_adm["headers"]
        )).json()) == 1
        assert len((await client.get(
            "/crm/contatos/busca?q=99999", headers=usuario_adm["headers"]
        )).json()) == 1

    async def test_marca_ja_vinculado(self, db_conn, client, usuario_adm):
        """
        O picker precisa mostrar quem já está na conta, em vez de deixar o
        usuário selecionar alguém e tomar 409 depois.
        """
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(client, usuario_adm["headers"], nome="Maria", conta_id=conta["id"])
        await criar_contato(client, usuario_adm["headers"], nome="Marina")

        resp = await client.get(
            f"/crm/contatos/busca?q=mar&conta_id={conta['id']}", headers=usuario_adm["headers"]
        )
        por_nome = {c["nome"]: c["ja_vinculado"] for c in resp.json()}
        assert por_nome == {"Maria": True, "Marina": False}

    async def test_sem_conta_id_ninguem_e_vinculado(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(client, usuario_adm["headers"], nome="Maria", conta_id=conta["id"])
        resp = await client.get("/crm/contatos/busca?q=maria", headers=usuario_adm["headers"])
        assert resp.json()[0]["ja_vinculado"] is False

    async def test_excluir_vinculados(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(client, usuario_adm["headers"], nome="Maria", conta_id=conta["id"])
        await criar_contato(client, usuario_adm["headers"], nome="Marina")
        resp = await client.get(
            f"/crm/contatos/busca?q=mar&conta_id={conta['id']}&excluir_vinculados=true",
            headers=usuario_adm["headers"],
        )
        assert [c["nome"] for c in resp.json()] == ["Marina"]

    async def test_q_obrigatorio(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/contatos/busca", headers=usuario_adm["headers"])
        assert resp.status_code == 422


# ── Listagem ─────────────────────────────────────────────────────────

class TestListagem:
    async def test_paginacao(self, db_conn, client, usuario_adm):
        for n in ["Ana", "Bruno", "Carla"]:
            await criar_contato(client, usuario_adm["headers"], nome=n)
        body = (await client.get(
            "/crm/contatos?limit=2", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 3
        assert len(body["itens"]) == 2

    async def test_filtra_por_conta(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(client, usuario_adm["headers"], nome="Ana", conta_id=conta["id"])
        await criar_contato(client, usuario_adm["headers"], nome="Bruno")
        body = (await client.get(
            f"/crm/contatos?conta_id={conta['id']}", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1

    async def test_filtra_sem_conta(self, db_conn, client, usuario_adm):
        """Contatos órfãos: criados e nunca vinculados, ou desvinculados de tudo."""
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_contato(client, usuario_adm["headers"], nome="Ana", conta_id=conta["id"])
        await criar_contato(client, usuario_adm["headers"], nome="Orfao")
        body = (await client.get(
            "/crm/contatos?sem_conta=true", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1
        assert body["itens"][0]["nome"] == "Orfao"

    async def test_aniversariantes_do_mes(self, db_conn, client, usuario_adm):
        await criar_contato(
            client, usuario_adm["headers"], nome="Marco", data_nascimento="1985-03-15"
        )
        await criar_contato(
            client, usuario_adm["headers"], nome="Julho", data_nascimento="1990-07-20"
        )
        body = (await client.get(
            "/crm/contatos?aniversariantes_mes=3", headers=usuario_adm["headers"]
        )).json()
        assert body["total"] == 1
        assert body["itens"][0]["nome"] == "Marco"

    async def test_qtd_contas_no_resumo(self, db_conn, client, usuario_adm):
        c1 = await criar_conta(client, usuario_adm["headers"], CNPJ_A, "Alfa")
        c2 = await criar_conta(client, usuario_adm["headers"], CNPJ_B, "Beta")
        contato = await criar_contato(
            client, usuario_adm["headers"], nome="Ana", conta_id=c1["id"]
        )
        await client.post(
            f"/crm/contatos/{contato['id']}/vinculos",
            json={"conta_id": c2["id"]},
            headers=usuario_adm["headers"],
        )
        body = (await client.get("/crm/contatos", headers=usuario_adm["headers"])).json()
        assert body["itens"][0]["qtd_contas"] == 2


# ── Edição e desativação ─────────────────────────────────────────────

class TestEditar:
    async def test_patch_parcial(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"], email="a@b.com")
        body = (await client.patch(
            f"/crm/contatos/{c['id']}",
            json={"telefone": "11999990000"},
            headers=usuario_adm["headers"],
        )).json()
        assert body["telefone"] == "11999990000"
        assert body["email"] == "a@b.com"

    async def test_patch_vazio_recusado(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"])
        resp = await client.patch(
            f"/crm/contatos/{c['id']}", json={}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_desativar_preserva_vinculos(self, db_conn, client, usuario_adm):
        """O histórico de quem era o contato da empresa continua legível."""
        conta = await criar_conta(client, usuario_adm["headers"])
        c = await criar_contato(client, usuario_adm["headers"], conta_id=conta["id"])
        body = (await client.delete(
            f"/crm/contatos/{c['id']}", headers=usuario_adm["headers"]
        )).json()
        assert body["ativo"] is False
        assert body["qtd_contas"] == 1

    async def test_reativar(self, db_conn, client, usuario_adm):
        c = await criar_contato(client, usuario_adm["headers"])
        await client.delete(f"/crm/contatos/{c['id']}", headers=usuario_adm["headers"])
        body = (await client.patch(
            f"/crm/contatos/{c['id']}", json={"ativo": True}, headers=usuario_adm["headers"]
        )).json()
        assert body["ativo"] is True

    async def test_404_em_inexistente(self, db_conn, client, usuario_adm):
        fake = uuid.uuid4()
        assert (await client.get(
            f"/crm/contatos/{fake}", headers=usuario_adm["headers"]
        )).status_code == 404
        assert (await client.delete(
            f"/crm/contatos/{fake}", headers=usuario_adm["headers"]
        )).status_code == 404


# ── Permissões ───────────────────────────────────────────────────────

class TestPermissoes:
    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM", "EC", "SDR", "EV", "EP"])
    async def test_todo_cargo_valido_acessa(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-ct@teste.com")
        assert (await client.get("/crm/contatos", headers=u["headers"])).status_code == 200

    @pytest.mark.parametrize("cargo", ["Gerente", "Hunter", "Farmer"])
    async def test_cargo_extinto_403(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-ct@teste.com")
        assert (await client.get("/crm/contatos", headers=u["headers"])).status_code == 403

    async def test_sem_token_401(self, db_conn, client):
        assert (await client.get("/crm/contatos")).status_code == 401
