"""
HIPO — Testes do router /crm/contas.

Cobre as três decisões que dão identidade ao módulo:
  1. CNPJ como chave de negócio, com 409 informativo na duplicata
  2. vendedor derivado das oportunidades ativas (nunca coluna)
  3. base compartilhada: todo cargo válido enxerga todas as contas
"""
import uuid

import pytest

from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_A_DIGITOS = "11222333000181"
CNPJ_B = "34.028.316/0001-03"
CNPJ_C = "47.960.950/0001-21"


# ── Helpers ──────────────────────────────────────────────────────────

def payload_conta(cnpj=CNPJ_A, **extra):
    base = {"razao_social": "Metalurgica Alfa LTDA", "cnpj": cnpj}
    base.update(extra)
    return base


async def criar_conta(client, headers, **kwargs):
    resp = await client.post("/crm/contas", json=payload_conta(**kwargs), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def criar_oportunidade(db_conn, conta_id, status="ativa", fase="lead",
                             ev_id=None, temperatura=50):
    """
    Insere oportunidade direto no banco — o router dela só existe na Sprint 3.
    Serve para exercitar o LATERAL do vendedor derivado.
    """
    numero = f"OPP-TEST-{uuid.uuid4().hex[:8]}"
    fase_desfecho = "negociacao" if fase == "finalizado" else None
    temp = temperatura if status == "ativa" else None
    opp_id = await db_conn.fetchval(
        """
        INSERT INTO oportunidades
            (numero, conta_id, fase, status, fase_desfecho, temperatura)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        numero, conta_id, fase, status, fase_desfecho, temp,
    )
    if ev_id:
        await db_conn.execute(
            "INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel)"
            " VALUES ($1, $2, 'EV')",
            opp_id, ev_id,
        )
    return opp_id


# ── Criação ──────────────────────────────────────────────────────────

class TestCriarConta:
    async def test_cria_e_normaliza_cnpj(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        assert conta["cnpj"] == CNPJ_A_DIGITOS
        assert conta["cnpj_formatado"] == CNPJ_A
        assert conta["ativo"] is True
        assert conta["eh_finder"] is False

    async def test_cnpj_sem_pontuacao_funciona_igual(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A_DIGITOS)
        assert conta["cnpj"] == CNPJ_A_DIGITOS

    async def test_cnpj_invalido_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(cnpj="11222333000182"),
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_cnpj_de_digitos_repetidos_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(cnpj="00000000000000"),
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_razao_social_vazia_recusada(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json={"razao_social": "   ", "cnpj": CNPJ_A},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_uf_normalizada_para_maiuscula(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"], uf="sp")
        assert conta["uf"] == "SP"

    async def test_uf_invalida_recusada(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(uf="SPX"),
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_cep_aceita_pontuacao_e_guarda_digitos(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"], cep="07020-020")
        assert conta["cep"] == "07020020"

    async def test_vertical_inexistente_recusada(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(vertical_id=99999),
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_num_funcionarios_negativo_recusado(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(num_funcionarios=-1),
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422


class TestCnpjDuplicado:
    async def test_duplicata_devolve_409(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/contas", json=payload_conta(), headers=usuario_adm["headers"]
        )
        assert resp.status_code == 409

    async def test_409_traz_a_conta_existente_no_payload(self, db_conn, client, usuario_adm):
        """
        Sem o id no corpo, o usuário bate num erro sobre um registro que não
        consegue enxergar — e cadastra a empresa de novo com outro documento.
        """
        original = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            "/crm/contas",
            json=payload_conta(razao_social="Outro Nome SA"),
            headers=usuario_adm["headers"],
        )
        detalhe = resp.json()["detail"]
        assert detalhe["erro"] == "cnpj_duplicado"
        assert detalhe["conta_id"] == original["id"]
        assert detalhe["razao_social"] == "Metalurgica Alfa LTDA"

    async def test_duplicata_detectada_mesmo_com_pontuacao_diferente(
        self, db_conn, client, usuario_adm
    ):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A_DIGITOS)
        resp = await client.post(
            "/crm/contas", json=payload_conta(cnpj=CNPJ_A), headers=usuario_adm["headers"]
        )
        assert resp.status_code == 409

    async def test_conta_inativa_tambem_bloqueia_o_cnpj(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.delete(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        resp = await client.post(
            "/crm/contas", json=payload_conta(), headers=usuario_adm["headers"]
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["ativo"] is False


# ── Vendedor derivado ────────────────────────────────────────────────

class TestVendedorDerivado:
    async def test_sem_oportunidade_a_lista_vem_vazia(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        assert conta["vendedores"] == []
        assert conta["qtd_oportunidades_ativas"] == 0

    async def test_oportunidade_ativa_traz_o_ev(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV", "ev-derivado@teste.com")
        ev_id = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev["email"])
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(db_conn, conta["id"], ev_id=ev_id)

        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        assert resp.json()["vendedores"] == ["Test EV"]

    async def test_oportunidade_suspensa_nao_conta(self, db_conn, client, usuario_adm):
        """Decidido: só status='ativa' alimenta o vendedor da conta."""
        ev = await criar_usuario(db_conn, client, "EV", "ev-susp@teste.com")
        ev_id = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev["email"])
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(db_conn, conta["id"], status="suspensa", ev_id=ev_id)

        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        assert resp.json()["vendedores"] == []

    async def test_oportunidade_finalizada_nao_conta(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV", "ev-fim@teste.com")
        ev_id = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev["email"])
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(
            db_conn, conta["id"], status="conquistado", fase="finalizado", ev_id=ev_id
        )

        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        assert resp.json()["vendedores"] == []

    async def test_duas_oportunidades_trazem_os_dois_evs(self, db_conn, client, usuario_adm):
        ev1 = await criar_usuario(db_conn, client, "EV", "ev1-multi@teste.com")
        ev2 = await criar_usuario(db_conn, client, "EV", "ev2-multi@teste.com")
        id1 = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev1["email"])
        id2 = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev2["email"])
        # Nomes distintos de propósito: o agregado é DISTINCT por nome, então
        # dois "Test EV" colapsariam em um e o teste passaria por engano.
        await db_conn.execute("UPDATE usuarios SET nome = 'Ana Vendas' WHERE id = $1", id1)
        await db_conn.execute("UPDATE usuarios SET nome = 'Bruno Vendas' WHERE id = $1", id2)

        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(db_conn, conta["id"], ev_id=id1)
        await criar_oportunidade(db_conn, conta["id"], ev_id=id2)

        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        body = resp.json()
        assert sorted(body["vendedores"]) == ["Ana Vendas", "Bruno Vendas"]
        assert body["qtd_oportunidades_ativas"] == 2

    async def test_mesmo_ev_em_duas_oportunidades_nao_duplica(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV", "ev-dup@teste.com")
        ev_id = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ev["email"])
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(db_conn, conta["id"], ev_id=ev_id)
        await criar_oportunidade(db_conn, conta["id"], ev_id=ev_id)

        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        assert resp.json()["vendedores"] == ["Test EV"]

    async def test_oportunidade_sem_ev_conta_mas_nao_traz_vendedor(
        self, db_conn, client, usuario_adm
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await criar_oportunidade(db_conn, conta["id"])
        resp = await client.get(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        body = resp.json()
        assert body["vendedores"] == []
        assert body["qtd_oportunidades_ativas"] == 1


# ── Busca (lupa do EntityPicker) ─────────────────────────────────────

class TestBusca:
    async def test_acha_por_trecho_da_razao_social(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"])
        resp = await client.get("/crm/contas/busca?q=alfa", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_busca_ignora_caixa(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"])
        resp = await client.get("/crm/contas/busca?q=METALURGICA", headers=usuario_adm["headers"])
        assert len(resp.json()) == 1

    async def test_acha_por_cnpj_com_pontuacao(self, db_conn, client, usuario_adm):
        """O usuário cola o CNPJ como está no documento, com pontos e barra."""
        await criar_conta(client, usuario_adm["headers"])
        resp = await client.get(
            f"/crm/contas/busca?q={CNPJ_A}", headers=usuario_adm["headers"]
        )
        assert len(resp.json()) == 1

    async def test_acha_por_cnpj_parcial(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"])
        resp = await client.get("/crm/contas/busca?q=11222333", headers=usuario_adm["headers"])
        assert len(resp.json()) == 1

    async def test_acha_por_nome_fantasia(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], nome_fantasia="Alfa Metais")
        resp = await client.get("/crm/contas/busca?q=Metais", headers=usuario_adm["headers"])
        assert len(resp.json()) == 1

    async def test_conta_inativa_aparece_na_busca(self, db_conn, client, usuario_adm):
        """
        Se ela não aparecesse, quem procurasse o CNPJ dela bateria em 409 sem
        conseguir achar o registro.
        """
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.delete(f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"])
        resp = await client.get("/crm/contas/busca?q=alfa", headers=usuario_adm["headers"])
        assert len(resp.json()) == 1
        assert resp.json()[0]["ativo"] is False

    async def test_apenas_finders_filtra(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(
            client, usuario_adm["headers"], cnpj=CNPJ_B,
            razao_social="Contabilidade Beta", eh_finder=True,
        )
        resp = await client.get(
            "/crm/contas/busca?q=a&apenas_finders=true", headers=usuario_adm["headers"]
        )
        assert all(c["eh_finder"] for c in resp.json())
        assert len(resp.json()) == 1

    async def test_sem_resultado_devolve_lista_vazia(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/contas/busca?q=zzzzzz", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_q_obrigatorio(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/contas/busca", headers=usuario_adm["headers"])
        assert resp.status_code == 422


# ── Listagem e filtros ───────────────────────────────────────────────

class TestListagem:
    async def test_lista_com_total_e_paginacao(self, db_conn, client, usuario_adm):
        for cnpj in (CNPJ_A, CNPJ_B, CNPJ_C):
            await criar_conta(client, usuario_adm["headers"], cnpj=cnpj)
        resp = await client.get("/crm/contas?limit=2", headers=usuario_adm["headers"])
        body = resp.json()
        assert body["total"] == 3
        assert len(body["itens"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 0

    async def test_offset_avanca(self, db_conn, client, usuario_adm):
        for cnpj in (CNPJ_A, CNPJ_B, CNPJ_C):
            await criar_conta(client, usuario_adm["headers"], cnpj=cnpj)
        resp = await client.get("/crm/contas?limit=2&offset=2", headers=usuario_adm["headers"])
        assert len(resp.json()["itens"]) == 1

    async def test_filtra_por_uf(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A, uf="SP")
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B, uf="RJ")
        resp = await client.get("/crm/contas?uf=SP", headers=usuario_adm["headers"])
        assert resp.json()["total"] == 1

    async def test_filtra_por_eh_finder(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B, eh_finder=True)
        resp = await client.get("/crm/contas?eh_finder=true", headers=usuario_adm["headers"])
        assert resp.json()["total"] == 1

    async def test_filtra_por_ativo(self, db_conn, client, usuario_adm):
        c1 = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)
        await client.delete(f"/crm/contas/{c1['id']}", headers=usuario_adm["headers"])
        resp = await client.get("/crm/contas?ativo=false", headers=usuario_adm["headers"])
        assert resp.json()["total"] == 1

    async def test_filtra_sem_oportunidade_ativa(self, db_conn, client, usuario_adm):
        """Este é o filtro que o KPI 'sem oportunidade aberta' aciona."""
        com = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)
        await criar_oportunidade(db_conn, com["id"])
        resp = await client.get(
            "/crm/contas?sem_oportunidade_ativa=true", headers=usuario_adm["headers"]
        )
        assert resp.json()["total"] == 1

    async def test_filtra_sem_vertical(self, db_conn, client, usuario_adm):
        """Filtro que o KPI 'Sem vertical' aciona por drilldown."""
        vertical = (await client.post(
            "/crm/dominio/verticais", json={"nome": "Metalúrgica"},
            headers=usuario_adm["headers"],
        )).json()
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A,
                          vertical_id=vertical["id"])
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)

        resp = await client.get(
            "/crm/contas?sem_vertical=true", headers=usuario_adm["headers"]
        )
        assert resp.json()["total"] == 1

    async def test_sem_vertical_bate_com_o_resumo(self, db_conn, client, usuario_adm):
        vertical = (await client.post(
            "/crm/dominio/verticais", json={"nome": "Saúde"},
            headers=usuario_adm["headers"],
        )).json()
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A,
                          vertical_id=vertical["id"])
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_C)

        resumo = (await client.get(
            "/crm/contas/resumo", headers=usuario_adm["headers"]
        )).json()
        lista = (await client.get(
            "/crm/contas?sem_vertical=true", headers=usuario_adm["headers"]
        )).json()
        assert resumo["sem_vertical"] == lista["total"] == 2

    async def test_busca_textual_na_listagem(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(
            client, usuario_adm["headers"], cnpj=CNPJ_B, razao_social="Padaria Beta"
        )
        resp = await client.get("/crm/contas?q=padaria", headers=usuario_adm["headers"])
        assert resp.json()["total"] == 1

    async def test_ordenacao_desc(self, db_conn, client, usuario_adm):
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A, razao_social="AAA")
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B, razao_social="ZZZ")
        resp = await client.get(
            "/crm/contas?ordenar_por=razao_social&desc=true", headers=usuario_adm["headers"]
        )
        assert resp.json()["itens"][0]["razao_social"] == "ZZZ"

    async def test_ordenar_por_invalido_recusado(self, db_conn, client, usuario_adm):
        """Whitelist de colunas — a alternativa seria interpolar SQL do cliente."""
        resp = await client.get(
            "/crm/contas?ordenar_por=cnpj;DROP", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_limit_acima_do_maximo_recusado(self, db_conn, client, usuario_adm):
        resp = await client.get("/crm/contas?limit=9999", headers=usuario_adm["headers"])
        assert resp.status_code == 422


# ── Resumo (KPIs) ────────────────────────────────────────────────────

class TestResumo:
    async def test_contadores_basicos(self, db_conn, client, usuario_adm):
        c1 = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B, eh_finder=True)
        await client.delete(f"/crm/contas/{c1['id']}", headers=usuario_adm["headers"])

        body = (await client.get("/crm/contas/resumo", headers=usuario_adm["headers"])).json()
        assert body["total"] == 2
        assert body["ativas"] == 1
        assert body["inativas"] == 1
        assert body["finders"] == 1

    async def test_sem_oportunidade_ativa_bate_com_o_filtro(self, db_conn, client, usuario_adm):
        com = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)
        await criar_oportunidade(db_conn, com["id"])

        resumo = (await client.get("/crm/contas/resumo", headers=usuario_adm["headers"])).json()
        lista = (await client.get(
            "/crm/contas?sem_oportunidade_ativa=true", headers=usuario_adm["headers"]
        )).json()
        assert resumo["sem_oportunidade_ativa"] == lista["total"] == 1

    async def test_banco_vazio_nao_quebra(self, db_conn, client, usuario_adm):
        body = (await client.get("/crm/contas/resumo", headers=usuario_adm["headers"])).json()
        assert body["total"] == 0
        assert body["por_vertical"] == []


# ── Edição e desativação ─────────────────────────────────────────────

class TestEditar:
    async def test_patch_parcial_preserva_o_resto(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"], cidade="Guarulhos")
        resp = await client.patch(
            f"/crm/contas/{conta['id']}",
            json={"telefone": "1130001000"},
            headers=usuario_adm["headers"],
        )
        body = resp.json()
        assert body["telefone"] == "1130001000"
        assert body["cidade"] == "Guarulhos"

    async def test_patch_nao_altera_cnpj(self, db_conn, client, usuario_adm):
        """CNPJ fora do schema de edição: trocar CNPJ é outra empresa."""
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.patch(
            f"/crm/contas/{conta['id']}",
            json={"cnpj": CNPJ_B, "razao_social": "Novo Nome"},
            headers=usuario_adm["headers"],
        )
        assert resp.json()["cnpj"] == CNPJ_A_DIGITOS
        assert resp.json()["razao_social"] == "Novo Nome"

    async def test_patch_vazio_recusado(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.patch(
            f"/crm/contas/{conta['id']}", json={}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_patch_em_conta_inexistente_404(self, db_conn, client, usuario_adm):
        resp = await client.patch(
            f"/crm/contas/{uuid.uuid4()}",
            json={"telefone": "1130001000"},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404

    async def test_desativar_e_reativar(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        assert (await client.delete(
            f"/crm/contas/{conta['id']}", headers=usuario_adm["headers"]
        )).json()["ativo"] is False
        assert (await client.patch(
            f"/crm/contas/{conta['id']}", json={"ativo": True}, headers=usuario_adm["headers"]
        )).json()["ativo"] is True

    async def test_desativar_inexistente_404(self, db_conn, client, usuario_adm):
        resp = await client.delete(
            f"/crm/contas/{uuid.uuid4()}", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 404

    async def test_obter_inexistente_404(self, db_conn, client, usuario_adm):
        resp = await client.get(f"/crm/contas/{uuid.uuid4()}", headers=usuario_adm["headers"])
        assert resp.status_code == 404


# ── Histórico (timeline da visão 360) ────────────────────────────────

class TestHistorico:
    async def test_conta_nova_tem_o_evento_de_criacao(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico", headers=usuario_adm["headers"]
        )).json()
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "conta_criada"
        assert eventos[0]["usuario"] == "Test ADM"

    async def test_vinculo_de_contato_entra_na_timeline(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": conta["id"], "cargo": "RH"},
            headers=usuario_adm["headers"],
        )
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico", headers=usuario_adm["headers"]
        )).json()
        tipos = [e["tipo"] for e in eventos]
        assert "contato_vinculado" in tipos
        vinculo = next(e for e in eventos if e["tipo"] == "contato_vinculado")
        assert vinculo["titulo"] == "Maria"
        assert vinculo["detalhe"] == "RH"

    async def test_desvincular_muda_o_tipo_do_evento(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        contato = (await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )).json()
        await client.delete(
            f"/crm/contatos/{contato['id']}/vinculos/{conta['id']}",
            headers=usuario_adm["headers"],
        )
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico", headers=usuario_adm["headers"]
        )).json()
        assert "contato_desvinculado" in [e["tipo"] for e in eventos]

    async def test_evento_de_oportunidade_entra_na_timeline(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        opp_id = await criar_oportunidade(db_conn, conta["id"])
        await db_conn.execute(
            """
            INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para)
            VALUES ($1, 'fase', 'lead', 'qualificacao')
            """,
            opp_id,
        )
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico", headers=usuario_adm["headers"]
        )).json()
        fase = next(e for e in eventos if e["tipo"] == "oportunidade_fase")
        assert fase["detalhe"] == "lead -> qualificacao"

    async def test_ordenado_do_mais_recente_para_o_mais_antigo(
        self, db_conn, client, usuario_adm
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            "/crm/contatos",
            json={"nome": "Maria", "conta_id": conta["id"]},
            headers=usuario_adm["headers"],
        )
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico", headers=usuario_adm["headers"]
        )).json()
        quandos = [e["quando"] for e in eventos]
        assert quandos == sorted(quandos, reverse=True)

    async def test_conta_inexistente_404(self, db_conn, client, usuario_adm):
        resp = await client.get(
            f"/crm/contas/{uuid.uuid4()}/historico", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 404

    async def test_respeita_o_limit(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        for n in ["A", "B", "C"]:
            await client.post(
                "/crm/contatos",
                json={"nome": n, "conta_id": conta["id"]},
                headers=usuario_adm["headers"],
            )
        eventos = (await client.get(
            f"/crm/contas/{conta['id']}/historico?limit=2", headers=usuario_adm["headers"]
        )).json()
        assert len(eventos) == 2


# ── Permissões ───────────────────────────────────────────────────────

class TestPermissoes:
    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM", "EC", "SDR", "EV", "EP"])
    async def test_todo_cargo_valido_enxerga_contas(self, db_conn, client, cargo):
        """
        Base compartilhada. Se um cargo não visse, bateria em CNPJ duplicado
        sem conseguir achar o registro que causou o conflito.
        """
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-crm@teste.com")
        resp = await client.get("/crm/contas", headers=u["headers"])
        assert resp.status_code == 200

    @pytest.mark.parametrize("cargo", ["Gerente", "Hunter", "Farmer"])
    async def test_cargo_extinto_recebe_403(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-ext@teste.com")
        resp = await client.get("/crm/contas", headers=u["headers"])
        assert resp.status_code == 403

    async def test_sem_token_401(self, db_conn, client):
        resp = await client.get("/crm/contas")
        assert resp.status_code == 401

    async def test_criacao_registra_o_autor(self, db_conn, client, usuario_adm):
        conta = await criar_conta(client, usuario_adm["headers"])
        autor = await db_conn.fetchval(
            "SELECT criado_por FROM contas WHERE id = $1", uuid.UUID(conta["id"])
        )
        esperado = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1", usuario_adm["email"]
        )
        assert autor == esperado
