"""
HIPO — CRM: carteira de parceiros (Sprint 6).

As regras puras (taxas, situação, períodos) já têm testes em
test_parceiro_regras.py. Aqui o foco é o que só aparece com banco: os
agregados por parceiro, o recorte de período, a trilha de eventos, a
transferência em massa e o guard do módulo novo.

`hoje` é parâmetro de query nos endpoints justamente para estes testes: sem
ele, um teste de "dormente" passaria hoje e falharia daqui a três meses.
"""
import pytest

from tests.conftest import criar_usuario

CNPJ_PARCEIRO = "11.111.111/0001-91"
CNPJ_PARCEIRO_2 = "22.222.222/0001-91"
CNPJ_PARCEIRO_3 = "33.333.333/0001-91"
CNPJ_CLIENTE = "44.444.444/0001-91"
CNPJ_CLIENTE_2 = "55.555.555/0001-91"
CNPJ_CLIENTE_3 = "66.666.666/0001-91"

HOJE = "2026-08-12"


# ── Helpers ──────────────────────────────────────────────────────────

async def nova_conta(client, headers, cnpj, razao):
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


async def novo_motivo(client, headers, tipo, nome):
    resp = await client.post(
        f"/crm/dominio/motivos/{tipo}", json={"nome": nome}, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def desfechar(client, headers, oportunidade_id, status_final, motivo_id=None):
    corpo = {"status": status_final}
    if motivo_id is not None:
        corpo["motivo_desfecho_id"] = motivo_id
    resp = await client.post(
        f"/crm/oportunidades/{oportunidade_id}/desfecho", json=corpo, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def id_do_usuario(db_conn, email):
    return str(await db_conn.fetchval(
        "SELECT id FROM usuarios WHERE email = $1", email
    ))


async def marcar_parceiro(client, headers, conta_id, ec_id=None):
    corpo = {"eh_finder": True}
    if ec_id is not None:
        corpo["ec_responsavel_id"] = ec_id
    resp = await client.patch(
        f"/crm/parceiros/{conta_id}", json=corpo, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def envelhecer_indicacao(db_conn, oportunidade_id, dias):
    """Empurra a criação da oportunidade para trás, para testar período."""
    await db_conn.execute(
        "UPDATE oportunidades SET criado_em = NOW() - ($1 || ' days')::interval "
        "WHERE id = $2::uuid",
        str(dias), oportunidade_id,
    )


# ── Permissão ────────────────────────────────────────────────────────

class TestPermissao:
    """
    O módulo 'parceiros' é o primeiro fora de MODULOS_BASE que um cargo
    operacional recebe. Se o guard cair, SDR e EV passam a ver e mexer na
    carteira de quem não é deles.
    """

    @pytest.mark.parametrize("cargo", ["SDR", "EV", "EP"])
    async def test_operacional_sem_carteira_recebe_403(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-parc@teste.com")
        resp = await client.get("/crm/parceiros/resumo", headers=u["headers"])
        assert resp.status_code == 403

    @pytest.mark.parametrize("cargo", ["EC", "ADM", "Franqueado"])
    async def test_quem_trabalha_carteira_entra(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-parc@teste.com")
        resp = await client.get("/crm/parceiros/resumo", headers=u["headers"])
        assert resp.status_code == 200

    async def test_cargo_extinto_recebe_403(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Gerente", "ger-parc@teste.com")
        resp = await client.get("/crm/parceiros", headers=u["headers"])
        assert resp.status_code == 403


# ── Marcar e desmarcar ───────────────────────────────────────────────

class TestMarcacao:
    async def test_marcar_a_mao_poe_na_carteira(self, db_conn, client, usuario_adm):
        """
        Marcar antes da primeira indicação é o que permite prospectar um
        contador novo. Sem isso a tela só mostra parceiro que já deu fruto —
        e quem ainda não deu é justamente quem precisa de ação.
        """
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        body = await marcar_parceiro(client, usuario_adm["headers"], conta["id"])
        assert body["eh_finder"] is True
        assert body["indicacoes"] == 0
        assert body["situacao"] == "sem_indicacao"

        lista = (await client.get(
            "/crm/parceiros", headers=usuario_adm["headers"]
        )).json()
        assert lista["total"] == 1

    async def test_marcar_registra_evento(self, db_conn, client, usuario_adm):
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        body = await marcar_parceiro(client, usuario_adm["headers"], conta["id"])
        assert [e["tipo"] for e in body["eventos"]] == ["marcado"]

    async def test_desmarcar_limpa_o_responsavel(self, db_conn, client, usuario_adm):
        """
        Não é gentileza com o CHECK do banco: manter o dono de uma parceria
        que deixou de existir faria a carteira dele contar um parceiro que
        não é mais parceiro.
        """
        ec = await criar_usuario(db_conn, client, "EC", "ec-desmarca@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        await marcar_parceiro(client, usuario_adm["headers"], conta["id"], ec_id)

        resp = await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"eh_finder": False},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["eh_finder"] is False
        assert body["ec_responsavel_id"] is None
        assert "removido" in [e["tipo"] for e in body["eventos"]]

        no_banco = await db_conn.fetchrow(
            "SELECT eh_finder, ec_responsavel_id FROM contas WHERE id = $1::uuid",
            conta["id"],
        )
        assert no_banco["eh_finder"] is False
        assert no_banco["ec_responsavel_id"] is None

    async def test_desmarcado_sai_da_lista(self, db_conn, client, usuario_adm):
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        await marcar_parceiro(client, usuario_adm["headers"], conta["id"])
        await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"eh_finder": False},
            headers=usuario_adm["headers"],
        )
        lista = (await client.get(
            "/crm/parceiros", headers=usuario_adm["headers"]
        )).json()
        assert lista["total"] == 0

    async def test_indicar_liga_o_parceiro_sozinho(self, db_conn, client, usuario_adm):
        """
        Comportamento herdado da Sprint 3: usar uma conta como finder marca
        eh_finder automaticamente. A tela de parceiros precisa enxergar isso
        sem ninguém ter marcado nada à mão.
        """
        parceiro = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        cliente = await nova_conta(
            client, usuario_adm["headers"], CNPJ_CLIENTE, "Metalurgica Beta"
        )
        await nova_oportunidade(
            client, usuario_adm["headers"], cliente["id"],
            finder_conta_id=parceiro["id"],
        )
        lista = (await client.get(
            "/crm/parceiros", headers=usuario_adm["headers"]
        )).json()
        assert lista["total"] == 1
        assert lista["itens"][0]["id"] == parceiro["id"]
        assert lista["itens"][0]["indicacoes"] == 1

    async def test_patch_vazio_recusado(self, db_conn, client, usuario_adm):
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        resp = await client.patch(
            f"/crm/parceiros/{conta['id']}", json={}, headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_conta_que_nao_e_parceira_da_404_no_get(
        self, db_conn, client, usuario_adm
    ):
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_CLIENTE, "Metalurgica Beta"
        )
        resp = await client.get(
            f"/crm/parceiros/{conta['id']}", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 404
        assert "não é um parceiro" in resp.json()["detail"]


# ── EC responsável ───────────────────────────────────────────────────

class TestResponsavel:
    async def test_atribuir_troca_e_remover_geram_eventos(
        self, db_conn, client, usuario_adm
    ):
        """
        A trilha é o que responde "de quem era essa carteira em março". Esse
        dado não dá para reconstruir depois, então ou grava na hora ou nunca.
        """
        a = await criar_usuario(db_conn, client, "EC", "ec-a@teste.com")
        b = await criar_usuario(db_conn, client, "EC", "ec-b@teste.com")
        a_id = await id_do_usuario(db_conn, a["email"])
        b_id = await id_do_usuario(db_conn, b["email"])

        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        await marcar_parceiro(client, usuario_adm["headers"], conta["id"], a_id)

        await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"ec_responsavel_id": b_id}, headers=usuario_adm["headers"],
        )
        body = (await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"ec_responsavel_id": None}, headers=usuario_adm["headers"],
        )).json()

        tipos = [e["tipo"] for e in body["eventos"]]
        # Ordem decrescente por data.
        assert tipos == ["removido", "transferido", "atribuido", "marcado"]
        assert body["ec_responsavel_id"] is None

    async def test_atribuir_de_novo_o_mesmo_nao_gera_evento(
        self, db_conn, client, usuario_adm
    ):
        """Salvar sem mudar nada não é história. Sem esta guarda, a trilha
        enche de linhas que não contam nada."""
        ec = await criar_usuario(db_conn, client, "EC", "ec-mesmo@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        await marcar_parceiro(client, usuario_adm["headers"], conta["id"], ec_id)
        body = (await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"ec_responsavel_id": ec_id}, headers=usuario_adm["headers"],
        )).json()
        assert [e["tipo"] for e in body["eventos"]] == ["atribuido", "marcado"]

    @pytest.mark.parametrize("cargo", ["SDR", "EV", "EP"])
    async def test_cargo_que_nao_trabalha_carteira_e_recusado(
        self, db_conn, client, usuario_adm, cargo
    ):
        """
        Sem esta validação a tela deixaria pendurar a carteira num SDR, e o
        filtro "parceiros do EC" nunca mais fecharia com a realidade. CHECK
        de banco não enxerga cargo — a regra tem que estar aqui.
        """
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-resp@teste.com")
        uid = await id_do_usuario(db_conn, u["email"])
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        resp = await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"eh_finder": True, "ec_responsavel_id": uid},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "não trabalha carteira" in resp.json()["detail"]

    async def test_usuario_inativo_nao_recebe_carteira(
        self, db_conn, client, usuario_adm
    ):
        ec = await criar_usuario(db_conn, client, "EC", "ec-inativo@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        await db_conn.execute(
            "UPDATE usuarios SET ativo = FALSE WHERE id = $1::uuid", ec_id
        )
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_PARCEIRO, "Contabilidade Alfa"
        )
        resp = await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"eh_finder": True, "ec_responsavel_id": ec_id},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "inativo" in resp.json()["detail"]

    async def test_conta_comum_nao_pode_ter_responsavel(
        self, db_conn, client, usuario_adm
    ):
        """O CHECK ck_contas_ec_so_parceiro existe no banco, mas quem tem que
        explicar em português é a API."""
        ec = await criar_usuario(db_conn, client, "EC", "ec-so-parc@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_CLIENTE, "Metalurgica Beta"
        )
        resp = await client.patch(
            f"/crm/parceiros/{conta['id']}",
            json={"ec_responsavel_id": ec_id},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422
        assert "Só parceiro" in resp.json()["detail"]

    async def test_o_banco_tambem_recusa(self, db_conn, client, usuario_adm):
        """Última linha de defesa: mesmo escrevendo direto no banco."""
        import asyncpg
        ec = await criar_usuario(db_conn, client, "EC", "ec-check@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_CLIENTE, "Metalurgica Beta"
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                "UPDATE contas SET ec_responsavel_id = $1::uuid WHERE id = $2::uuid",
                ec_id, conta["id"],
            )


# ── Métricas ─────────────────────────────────────────────────────────

class TestMetricas:
    async def test_conta_indicacoes_por_desfecho(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        c1 = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        c2 = await nova_conta(client, h, CNPJ_CLIENTE_2, "Cliente Dois")
        c3 = await nova_conta(client, h, CNPJ_CLIENTE_3, "Cliente Tres")
        m_perda = await novo_motivo(client, h, "perda", "Preço")
        m_canc = await novo_motivo(client, h, "cancelamento", "Lead errado")

        ganha = await nova_oportunidade(
            client, h, c1["id"], finder_conta_id=parceiro["id"], valor_mensalidade=1000
        )
        perdida = await nova_oportunidade(
            client, h, c2["id"], finder_conta_id=parceiro["id"], valor_mensalidade=500
        )
        cancelada = await nova_oportunidade(
            client, h, c3["id"], finder_conta_id=parceiro["id"], valor_mensalidade=300
        )
        await desfechar(client, h, ganha["id"], "conquistado")
        await desfechar(client, h, perdida["id"], "perdido", m_perda["id"])
        await desfechar(client, h, cancelada["id"], "cancelado", m_canc["id"])

        body = (await client.get(
            f"/crm/parceiros/{parceiro['id']}", headers=h
        )).json()
        assert body["indicacoes"] == 3
        assert body["convertidas"] == 1
        assert body["perdidas"] == 1
        assert body["canceladas"] == 1
        assert body["em_aberto"] == 0
        assert float(body["ticket_indicado"]) == 1800.0
        assert float(body["ticket_convertido"]) == 1000.0

    async def test_conversao_ignora_cancelado_e_aberto(
        self, db_conn, client, usuario_adm
    ):
        """
        1 ganha + 1 perdida + 1 cancelada + 1 em aberto = 50%, não 25%.
        Cancelado é erro nosso; em aberto ainda não é resultado.
        """
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        c1 = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        c2 = await nova_conta(client, h, CNPJ_CLIENTE_2, "Cliente Dois")
        c3 = await nova_conta(client, h, CNPJ_CLIENTE_3, "Cliente Tres")
        m_perda = await novo_motivo(client, h, "perda", "Preço")
        m_canc = await novo_motivo(client, h, "cancelamento", "Lead errado")

        ganha = await nova_oportunidade(client, h, c1["id"], finder_conta_id=parceiro["id"])
        perdida = await nova_oportunidade(client, h, c2["id"], finder_conta_id=parceiro["id"])
        cancelada = await nova_oportunidade(client, h, c3["id"], finder_conta_id=parceiro["id"])
        # A quarta fica em aberto, na mesma conta de outra ja usada nao da:
        # cada oportunidade precisa de conta, mas a mesma conta pode ter varias.
        await nova_oportunidade(client, h, c1["id"], finder_conta_id=parceiro["id"])

        await desfechar(client, h, ganha["id"], "conquistado")
        await desfechar(client, h, perdida["id"], "perdido", m_perda["id"])
        await desfechar(client, h, cancelada["id"], "cancelado", m_canc["id"])

        body = (await client.get(f"/crm/parceiros/{parceiro['id']}", headers=h)).json()
        assert body["indicacoes"] == 4
        assert body["taxa_conversao"] == 0.5
        assert body["taxa_cancelamento"] == 0.25

    async def test_sem_nada_fechado_a_conversao_e_nula(
        self, db_conn, client, usuario_adm
    ):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        await nova_oportunidade(client, h, cliente["id"], finder_conta_id=parceiro["id"])
        body = (await client.get(f"/crm/parceiros/{parceiro['id']}", headers=h)).json()
        assert body["taxa_conversao"] is None
        assert body["taxa_cancelamento"] == 0.0

    async def test_periodo_recorta_as_metricas(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        c1 = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        antiga = await nova_oportunidade(
            client, h, c1["id"], finder_conta_id=parceiro["id"]
        )
        await nova_oportunidade(client, h, c1["id"], finder_conta_id=parceiro["id"])
        await envelhecer_indicacao(db_conn, antiga["id"], 200)

        sempre = (await client.get(f"/crm/parceiros/{parceiro['id']}", headers=h)).json()
        assert sempre["indicacoes"] == 2

        recente = (await client.get(
            f"/crm/parceiros/{parceiro['id']}?periodo=90d", headers=h
        )).json()
        assert recente["indicacoes"] == 1

    async def test_situacao_nao_e_recortada_pelo_periodo(
        self, db_conn, client, usuario_adm
    ):
        """
        Regressão da armadilha central desta tela: se a última indicação
        também fosse filtrada pelo período, um parceiro de anos apareceria
        como 'sem indicação' toda vez que alguém olhasse 90 dias.
        """
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        c1 = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        antiga = await nova_oportunidade(
            client, h, c1["id"], finder_conta_id=parceiro["id"]
        )
        await envelhecer_indicacao(db_conn, antiga["id"], 200)

        body = (await client.get(
            f"/crm/parceiros/{parceiro['id']}?periodo=90d", headers=h
        )).json()
        assert body["indicacoes"] == 0
        assert body["situacao"] == "dormente"
        assert body["ultima_indicacao_em"] is not None

    async def test_situacoes_pelo_tempo(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        opp = await nova_oportunidade(client, h, cliente["id"], finder_conta_id=parceiro["id"])

        for dias, esperado in ((10, "ativo"), (120, "esfriando"), (300, "dormente")):
            await envelhecer_indicacao(db_conn, opp["id"], dias)
            body = (await client.get(f"/crm/parceiros/{parceiro['id']}", headers=h)).json()
            assert body["situacao"] == esperado, f"{dias} dias"

    async def test_periodo_invalido_recusado(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/crm/parceiros?periodo=decada", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422


# ── Listagem e filtros ───────────────────────────────────────────────

class TestListagem:
    async def test_so_parceiro_aparece(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await nova_conta(client, h, CNPJ_CLIENTE, "Metalurgica Beta")
        await marcar_parceiro(client, h, parceiro["id"])
        body = (await client.get("/crm/parceiros", headers=h)).json()
        assert [i["razao_social"] for i in body["itens"]] == ["Contabilidade Alfa"]

    async def test_filtra_sem_ec(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        ec = await criar_usuario(db_conn, client, "EC", "ec-filtro@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        com = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        sem = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        await marcar_parceiro(client, h, com["id"], ec_id)
        await marcar_parceiro(client, h, sem["id"])

        body = (await client.get("/crm/parceiros?sem_ec=true", headers=h)).json()
        assert body["total"] == 1
        assert body["itens"][0]["razao_social"] == "Contabilidade Beta"

    async def test_filtra_por_ec(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        ec = await criar_usuario(db_conn, client, "EC", "ec-dono@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        dele = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        outro = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        await marcar_parceiro(client, h, dele["id"], ec_id)
        await marcar_parceiro(client, h, outro["id"])

        body = (await client.get(
            f"/crm/parceiros?ec_responsavel_id={ec_id}", headers=h
        )).json()
        assert body["total"] == 1
        assert body["itens"][0]["ec_responsavel_nome"] == "Test EC"

    async def test_filtra_por_situacao(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        ativo = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        parado = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        await nova_oportunidade(client, h, cliente["id"], finder_conta_id=ativo["id"])
        velha = await nova_oportunidade(
            client, h, cliente["id"], finder_conta_id=parado["id"]
        )
        await envelhecer_indicacao(db_conn, velha["id"], 300)

        body = (await client.get("/crm/parceiros?situacao=dormente", headers=h)).json()
        assert body["total"] == 1
        assert body["itens"][0]["razao_social"] == "Contabilidade Beta"

    async def test_situacao_invalida_recusada(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/crm/parceiros?situacao=morno", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_busca_por_razao_social(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        a = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        b = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Escritorio Beta")
        await marcar_parceiro(client, h, a["id"])
        await marcar_parceiro(client, h, b["id"])
        body = (await client.get("/crm/parceiros?q=Escritorio", headers=h)).json()
        assert body["total"] == 1

    async def test_total_conta_depois_do_filtro_de_situacao(
        self, db_conn, client, usuario_adm
    ):
        """
        O filtro de situação roda em Python. Se o `total` viesse de um
        count() no SQL, a paginação mostraria "3 parceiros" com um item na
        tela — o clássico total que não bate com a lista.
        """
        h = usuario_adm["headers"]
        for cnpj, nome in (
            (CNPJ_PARCEIRO, "Alfa"), (CNPJ_PARCEIRO_2, "Beta"), (CNPJ_PARCEIRO_3, "Gama")
        ):
            conta = await nova_conta(client, h, cnpj, f"Contabilidade {nome}")
            await marcar_parceiro(client, h, conta["id"])
        body = (await client.get(
            "/crm/parceiros?situacao=sem_indicacao", headers=h
        )).json()
        assert body["total"] == 3
        assert len(body["itens"]) == 3

    async def test_ordenacao_invalida_recusada(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/crm/parceiros?ordenar_por=cor_favorita", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422

    async def test_ordena_por_situacao_poe_atencao_na_frente(
        self, db_conn, client, usuario_adm
    ):
        h = usuario_adm["headers"]
        ativo = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Ativa")
        nunca = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Nova")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        await nova_oportunidade(client, h, cliente["id"], finder_conta_id=ativo["id"])
        await marcar_parceiro(client, h, nunca["id"])

        body = (await client.get("/crm/parceiros?ordenar_por=situacao", headers=h)).json()
        assert [i["situacao"] for i in body["itens"]] == ["sem_indicacao", "ativo"]


# ── Indicações (drilldown) ───────────────────────────────────────────

class TestIndicacoes:
    async def test_lista_as_oportunidades_indicadas(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        outro = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        minha = await nova_oportunidade(
            client, h, cliente["id"], finder_conta_id=parceiro["id"]
        )
        await nova_oportunidade(client, h, cliente["id"], finder_conta_id=outro["id"])

        body = (await client.get(
            f"/crm/parceiros/{parceiro['id']}/indicacoes", headers=h
        )).json()
        assert [i["id"] for i in body] == [minha["id"]]
        assert body[0]["conta_razao_social"] == "Cliente Um"

    async def test_traz_finalizadas_junto(self, db_conn, client, usuario_adm):
        """A leitura aqui é "o que esse parceiro me deu" — o que virou nada
        faz parte da resposta."""
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        opp = await nova_oportunidade(
            client, h, cliente["id"], finder_conta_id=parceiro["id"]
        )
        await desfechar(client, h, opp["id"], "conquistado")
        body = (await client.get(
            f"/crm/parceiros/{parceiro['id']}/indicacoes", headers=h
        )).json()
        assert len(body) == 1
        assert body[0]["status"] == "conquistado"

    async def test_respeita_o_periodo(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        parceiro = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        velha = await nova_oportunidade(
            client, h, cliente["id"], finder_conta_id=parceiro["id"]
        )
        await envelhecer_indicacao(db_conn, velha["id"], 200)
        body = (await client.get(
            f"/crm/parceiros/{parceiro['id']}/indicacoes?periodo=90d", headers=h
        )).json()
        assert body == []

    async def test_conta_comum_da_404(self, db_conn, client, usuario_adm):
        conta = await nova_conta(
            client, usuario_adm["headers"], CNPJ_CLIENTE, "Cliente Um"
        )
        resp = await client.get(
            f"/crm/parceiros/{conta['id']}/indicacoes", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 404


# ── Transferência de carteira ────────────────────────────────────────

class TestTransferencia:
    async def test_move_a_carteira_inteira(self, db_conn, client, usuario_adm):
        """
        A pendência que o doc mandava resolver antes da Sprint 6 ir a
        produção. Sem ação em massa, desligar um EC com 40 parceiros vira 40
        cliques — e o que acontece na prática é que ninguém faz.
        """
        h = usuario_adm["headers"]
        sai = await criar_usuario(db_conn, client, "EC", "ec-sai@teste.com")
        fica = await criar_usuario(db_conn, client, "EC", "ec-fica@teste.com")
        sai_id = await id_do_usuario(db_conn, sai["email"])
        fica_id = await id_do_usuario(db_conn, fica["email"])

        for cnpj, nome in ((CNPJ_PARCEIRO, "Alfa"), (CNPJ_PARCEIRO_2, "Beta")):
            conta = await nova_conta(client, h, cnpj, f"Contabilidade {nome}")
            await marcar_parceiro(client, h, conta["id"], sai_id)

        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": sai_id, "para_usuario_id": fica_id},
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["transferidos"] == 2

        lista = (await client.get(
            f"/crm/parceiros?ec_responsavel_id={fica_id}", headers=h
        )).json()
        assert lista["total"] == 2

    async def test_grava_um_evento_por_parceiro(self, db_conn, client, usuario_adm):
        """O lote não é a unidade de história: o que interessa depois é a
        trilha de cada parceiro."""
        h = usuario_adm["headers"]
        sai = await criar_usuario(db_conn, client, "EC", "ec-sai@teste.com")
        fica = await criar_usuario(db_conn, client, "EC", "ec-fica@teste.com")
        sai_id = await id_do_usuario(db_conn, sai["email"])
        fica_id = await id_do_usuario(db_conn, fica["email"])

        conta = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await marcar_parceiro(client, h, conta["id"], sai_id)
        await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": sai_id, "para_usuario_id": fica_id},
            headers=h,
        )
        body = (await client.get(f"/crm/parceiros/{conta['id']}", headers=h)).json()
        assert [e["tipo"] for e in body["eventos"]] == [
            "transferido", "atribuido", "marcado"
        ]
        assert body["eventos"][0]["de_nome"] == "Test EC"
        assert body["eventos"][0]["para_nome"] == "Test EC"

    async def test_transfere_so_os_escolhidos(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        sai = await criar_usuario(db_conn, client, "EC", "ec-sai@teste.com")
        fica = await criar_usuario(db_conn, client, "EC", "ec-fica@teste.com")
        sai_id = await id_do_usuario(db_conn, sai["email"])
        fica_id = await id_do_usuario(db_conn, fica["email"])

        a = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        b = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        await marcar_parceiro(client, h, a["id"], sai_id)
        await marcar_parceiro(client, h, b["id"], sai_id)

        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={
                "de_usuario_id": sai_id, "para_usuario_id": fica_id,
                "conta_ids": [a["id"]],
            },
            headers=h,
        )
        assert resp.json()["transferidos"] == 1
        restante = (await client.get(
            f"/crm/parceiros?ec_responsavel_id={sai_id}", headers=h
        )).json()
        assert restante["total"] == 1
        assert restante["itens"][0]["razao_social"] == "Contabilidade Beta"

    async def test_distribui_os_orfaos(self, db_conn, client, usuario_adm):
        """
        `de_usuario_id` nulo é "os parceiros sem responsável". É o que permite
        usar a mesma tela para zerar o KPI 'sem EC', e não só para esvaziar a
        carteira de quem está saindo.
        """
        h = usuario_adm["headers"]
        ec = await criar_usuario(db_conn, client, "EC", "ec-recebe@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await marcar_parceiro(client, h, conta["id"])

        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": None, "para_usuario_id": ec_id},
            headers=h,
        )
        assert resp.json()["transferidos"] == 1
        body = (await client.get(f"/crm/parceiros/{conta['id']}", headers=h)).json()
        assert body["ec_responsavel_id"] == ec_id
        assert body["eventos"][0]["tipo"] == "atribuido"

    async def test_esvaziar_a_carteira_e_valido(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        ec = await criar_usuario(db_conn, client, "EC", "ec-esvazia@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        conta = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await marcar_parceiro(client, h, conta["id"], ec_id)

        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": ec_id, "para_usuario_id": None},
            headers=h,
        )
        assert resp.json()["transferidos"] == 1
        body = (await client.get(f"/crm/parceiros/{conta['id']}", headers=h)).json()
        assert body["ec_responsavel_id"] is None
        assert body["eventos"][0]["tipo"] == "removido"

    async def test_origem_igual_destino_recusado(self, db_conn, client, usuario_adm):
        ec = await criar_usuario(db_conn, client, "EC", "ec-mesmo@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": ec_id, "para_usuario_id": ec_id},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_destino_com_cargo_errado_recusado(self, db_conn, client, usuario_adm):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-destino@teste.com")
        sdr_id = await id_do_usuario(db_conn, sdr["email"])
        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={"de_usuario_id": None, "para_usuario_id": sdr_id},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_carteira_vazia_nao_e_erro(self, db_conn, client, usuario_adm):
        a = await criar_usuario(db_conn, client, "EC", "ec-vazio-a@teste.com")
        b = await criar_usuario(db_conn, client, "EC", "ec-vazio-b@teste.com")
        resp = await client.post(
            "/crm/parceiros/carteira/transferir",
            json={
                "de_usuario_id": await id_do_usuario(db_conn, a["email"]),
                "para_usuario_id": await id_do_usuario(db_conn, b["email"]),
            },
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json() == {"transferidos": 0, "conta_ids": []}


# ── Resumo ───────────────────────────────────────────────────────────

class TestResumo:
    async def test_banco_vazio(self, db_conn, client, usuario_adm):
        body = (await client.get(
            "/crm/parceiros/resumo", headers=usuario_adm["headers"]
        )).json()
        assert body["parceiros"] == 0
        assert body["sem_ec"] == 0
        assert body["taxa_conversao"] is None
        assert len(body["por_situacao"]) == 4

    async def test_conta_parceiros_e_orfaos(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        ec = await criar_usuario(db_conn, client, "EC", "ec-resumo@teste.com")
        ec_id = await id_do_usuario(db_conn, ec["email"])
        com = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        sem = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        await marcar_parceiro(client, h, com["id"], ec_id)
        await marcar_parceiro(client, h, sem["id"])

        body = (await client.get("/crm/parceiros/resumo", headers=h)).json()
        assert body["parceiros"] == 2
        assert body["sem_ec"] == 1

    async def test_carteira_por_ec_so_lista_quem_tem(
        self, db_conn, client, usuario_adm
    ):
        """A lista existe para comparar carteiras, não para mostrar todo
        mundo com zero."""
        h = usuario_adm["headers"]
        com = await criar_usuario(db_conn, client, "EC", "ec-com@teste.com")
        await criar_usuario(db_conn, client, "EC", "ec-sem@teste.com")
        com_id = await id_do_usuario(db_conn, com["email"])
        conta = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await marcar_parceiro(client, h, conta["id"], com_id)

        body = (await client.get("/crm/parceiros/resumo", headers=h)).json()
        assert len(body["por_ec"]) == 1
        assert body["por_ec"][0]["parceiros"] == 1

    async def test_taxa_geral_agrega_todos(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        p1 = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        p2 = await nova_conta(client, h, CNPJ_PARCEIRO_2, "Contabilidade Beta")
        cliente = await nova_conta(client, h, CNPJ_CLIENTE, "Cliente Um")
        m_perda = await novo_motivo(client, h, "perda", "Preço")

        ganha = await nova_oportunidade(client, h, cliente["id"], finder_conta_id=p1["id"])
        perdida = await nova_oportunidade(client, h, cliente["id"], finder_conta_id=p2["id"])
        await desfechar(client, h, ganha["id"], "conquistado")
        await desfechar(client, h, perdida["id"], "perdido", m_perda["id"])

        body = (await client.get("/crm/parceiros/resumo", headers=h)).json()
        assert body["indicacoes"] == 2
        assert body["convertidas"] == 1
        assert body["taxa_conversao"] == 0.5

    async def test_por_situacao_cobre_as_quatro(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        conta = await nova_conta(client, h, CNPJ_PARCEIRO, "Contabilidade Alfa")
        await marcar_parceiro(client, h, conta["id"])
        body = (await client.get("/crm/parceiros/resumo", headers=h)).json()
        mapa = {s["situacao"]: s["quantidade"] for s in body["por_situacao"]}
        assert mapa["sem_indicacao"] == 1
        assert mapa["ativo"] == 0
