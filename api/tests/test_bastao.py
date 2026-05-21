"""
HIPO -- Testes do módulo Bastão.

Cobre:
  - Workflow completo: Hunter cria → ADM aprova/rejeita → Hunter remove
  - Validações de regra de negócio (CNPJ inexistente, conflito de bastão ativo)
  - Permissões (Hunter não aprova; só ADM)
  - KPIs agregados
  - Lookup de contador
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
async def setup_dados(db_conn):
    """
    Cria fixtures comuns: usuários (ADM + Hunter + Farmer), 1 colaborador
    Hunter, 1 colaborador Farmer e 2 CNPJs em carteira_cnpj.
    """
    # Limpa tabelas relevantes
    await db_conn.execute("TRUNCATE carteira_bastao CASCADE")
    await db_conn.execute("TRUNCATE carteira_cnpj CASCADE")
    await db_conn.execute("TRUNCATE carteira_colaborador CASCADE")
    await db_conn.execute("DELETE FROM usuarios WHERE email LIKE 'bastao_%'")

    # Usuários
    adm_id = await db_conn.fetchval(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('Tulio ADM', 'bastao_adm@hipo.com', 'hash', 'ADM')
        RETURNING id
        """
    )
    hunter_id = await db_conn.fetchval(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('Patrick Hunter', 'bastao_hunter@hipo.com', 'hash', 'Hunter')
        RETURNING id
        """
    )
    farmer_id = await db_conn.fetchval(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('Aline Farmer', 'bastao_farmer@hipo.com', 'hash', 'Farmer')
        RETURNING id
        """
    )

    # Colaboradores
    await db_conn.execute(
        """
        INSERT INTO carteira_colaborador (nome, funcao)
        VALUES ('Patrick Hunter', 'EC_HUNTER'), ('Aline Farmer', 'EC_FARMER')
        """
    )

    # Upload base + 2 CNPJs
    upload_id = await db_conn.fetchval(
        """
        INSERT INTO carteira_upload (tipo, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ('CARTEIRA', 'teste.xlsx', 2, 2, TRUE)
        RETURNING id
        """
    )
    await db_conn.execute(
        """
        INSERT INTO carteira_cnpj (upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade, cidade_uf, colaborador_nome)
        VALUES
            ($1, 'g1', 'Grupo Teste 1', '11.111.111/0001-11', 'Contab Teste 1', 'São Paulo/SP', 'Patrick Hunter'),
            ($1, 'g2', 'Grupo Teste 2', '22.222.222/0001-22', 'Contab Teste 2', 'Guarulhos/SP', 'Patrick Hunter')
        """,
        upload_id,
    )

    return {
        "adm_id": adm_id,
        "hunter_id": hunter_id,
        "farmer_id": farmer_id,
        "hunter_nome": "Patrick Hunter",
        "farmer_nome": "Aline Farmer",
        "cnpj1": "11.111.111/0001-11",
        "cnpj2": "22.222.222/0001-22",
    }


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _token_para(client, email: str) -> str:
    """Gera um JWT pra usuário de teste (fixtura padrão usa endpoint de login)."""
    # Setup: muda senha pra valor conhecido
    # (Idealmente o conftest expõe helper. Adaptado a partir de test_clientes.py.)
    from routers.auth import _gerar_token
    return _gerar_token(email)


# ── Testes do service (sem HTTP) ──────────────────────────────

class TestServiceBastao:

    async def test_lookup_contador_existente(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        info = await svc.buscar_contador_por_cnpj(db_conn, d["cnpj1"])
        assert info["cnpj_contador"] == d["cnpj1"]
        assert info["contabilidade"] == "Contab Teste 1"

    async def test_lookup_aceita_cnpj_sem_mascara(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        info = await svc.buscar_contador_por_cnpj(db_conn, "11111111000111")
        assert info["cnpj_contador"] == d["cnpj1"]

    async def test_lookup_contador_inexistente(self, db_conn, setup_dados):
        from services import bastao as svc
        await setup_dados
        with pytest.raises(svc.ContadorNaoEncontrado):
            await svc.buscar_contador_por_cnpj(db_conn, "99.999.999/0001-99")

    async def test_criar_bastao_pendente(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        row = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"],
            farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"],
            data_parceria=date(2026, 5, 1),
            leads_iniciais=2,
            criado_por=d["hunter_id"],
        )
        assert row["status"] == "PENDENTE"
        assert row["leads_iniciais"] == 2
        assert row["hunter_nome"] == d["hunter_nome"]

    async def test_criar_bastao_conflito_unico(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        with pytest.raises(svc.CnpjJaTemBastaoAtivo):
            await svc.criar_bastao(
                db_conn,
                hunter_nome="Outro Hunter", farmer_nome=d["farmer_nome"],
                cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 2),
                leads_iniciais=3, criado_por=d["hunter_id"],
            )

    async def test_criar_bastao_cnpj_inexistente(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        with pytest.raises(svc.ContadorNaoEncontrado):
            await svc.criar_bastao(
                db_conn,
                hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
                cnpj_contador="00.000.000/0000-00",
                data_parceria=date(2026, 5, 1), leads_iniciais=0,
                criado_por=d["hunter_id"],
            )

    async def test_aprovar_bastao(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        aprovado = await svc.aprovar_bastao(db_conn, b["id"], d["adm_id"])
        assert aprovado["status"] == "APROVADO"
        assert aprovado["validado_por"] == d["adm_id"]
        assert aprovado["validado_em"] is not None

    async def test_aprovar_bastao_inexistente(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        with pytest.raises(svc.BastaoNaoEncontrado):
            await svc.aprovar_bastao(db_conn, uuid.uuid4(), d["adm_id"])

    async def test_aprovar_duas_vezes_falha(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        await svc.aprovar_bastao(db_conn, b["id"], d["adm_id"])
        with pytest.raises(svc.TransicaoInvalida):
            await svc.aprovar_bastao(db_conn, b["id"], d["adm_id"])

    async def test_rejeitar_exige_motivo(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        with pytest.raises(svc.TransicaoInvalida):
            await svc.rejeitar_bastao(db_conn, b["id"], d["adm_id"], "")
        # Com motivo OK
        rej = await svc.rejeitar_bastao(db_conn, b["id"], d["adm_id"], "Não está apto")
        assert rej["status"] == "REJEITADO"
        assert rej["motivo_rejeicao"] == "Não está apto"

    async def test_remover_proprio_bastao(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        removido = await svc.remover_bastao(db_conn, b["id"], d["hunter_nome"])
        assert removido["status"] == "REMOVIDO"
        assert removido["removido_em"] is not None

    async def test_remover_bastao_de_outro_falha(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        with pytest.raises(svc.TransicaoInvalida):
            await svc.remover_bastao(db_conn, b["id"], "Outro Hunter")

    async def test_apos_remover_pode_criar_outro(self, db_conn, setup_dados):
        """Removeu → unique partial libera o CNPJ pra novo bastão."""
        from services import bastao as svc
        d = await setup_dados
        b1 = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        await svc.remover_bastao(db_conn, b1["id"], d["hunter_nome"])
        # Agora o CNPJ está livre — outro Hunter pode reivindicar
        b2 = await svc.criar_bastao(
            db_conn,
            hunter_nome="Outro Hunter", farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 6, 1),
            leads_iniciais=1, criado_por=d["hunter_id"],
        )
        assert b2["status"] == "PENDENTE"

    async def test_kpis_do_hunter(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        # Cria 2 bastões — aprova 1, deixa 1 pendente
        b1 = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=3, criado_por=d["hunter_id"],
        )
        await svc.aprovar_bastao(db_conn, b1["id"], d["adm_id"])
        await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj2"], data_parceria=date(2026, 5, 2),
            leads_iniciais=5, criado_por=d["hunter_id"],
        )

        kpis = await svc.kpis_do_hunter(db_conn, d["hunter_nome"])
        assert kpis["total_passados"] == 1
        assert kpis["pendentes"] == 1
        assert kpis["leads_iniciais_soma"] == 3  # só do aprovado

    async def test_listar_bastoes_pendentes_apenas(self, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b1 = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        b2 = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj2"], data_parceria=date(2026, 5, 2),
            leads_iniciais=1, criado_por=d["hunter_id"],
        )
        await svc.aprovar_bastao(db_conn, b1["id"], d["adm_id"])

        pendentes = await svc.listar_bastoes_pendentes(db_conn)
        ids = {p["id"] for p in pendentes}
        assert b2["id"] in ids
        assert b1["id"] not in ids


# ── Testes HTTP (router) ──────────────────────────────────────

class TestRouterBastao:

    async def test_hunter_cria_bastao_via_http(self, client, db_conn, setup_dados):
        d = await setup_dados
        token = await _token_para(client, "bastao_hunter@hipo.com")
        r = await client.post(
            "/carteira/bastoes",
            json={
                "farmer_nome": d["farmer_nome"],
                "cnpj_contador": d["cnpj1"],
                "data_parceria": "2026-05-01",
                "leads_iniciais": 2,
            },
            headers=_auth_header(token),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "PENDENTE"

    async def test_hunter_nao_pode_aprovar(self, client, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        token = await _token_para(client, "bastao_hunter@hipo.com")
        r = await client.patch(
            f"/carteira/bastoes/{b['id']}/aprovar",
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    async def test_adm_aprova_via_http(self, client, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        b = await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        token = await _token_para(client, "bastao_adm@hipo.com")
        r = await client.patch(
            f"/carteira/bastoes/{b['id']}/aprovar",
            headers=_auth_header(token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "APROVADO"

    async def test_lookup_contador_via_http(self, client, db_conn, setup_dados):
        d = await setup_dados
        token = await _token_para(client, "bastao_hunter@hipo.com")
        r = await client.get(
            f"/carteira/bastoes/contador/{d['cnpj1']}",
            headers=_auth_header(token),
        )
        assert r.status_code == 200
        assert r.json()["cnpj_contador"] == d["cnpj1"]

    async def test_lookup_contador_404(self, client, setup_dados):
        await setup_dados
        token = await _token_para(client, "bastao_hunter@hipo.com")
        r = await client.get(
            "/carteira/bastoes/contador/99.999.999/0001-99",
            headers=_auth_header(token),
        )
        assert r.status_code == 404

    async def test_meus_bastoes_filtra_pelo_usuario(self, client, db_conn, setup_dados):
        from services import bastao as svc
        d = await setup_dados
        # Hunter cria 1, "Outro Hunter" cria 1 (mas Outro Hunter não tem usuário)
        await svc.criar_bastao(
            db_conn,
            hunter_nome=d["hunter_nome"], farmer_nome=d["farmer_nome"],
            cnpj_contador=d["cnpj1"], data_parceria=date(2026, 5, 1),
            leads_iniciais=2, criado_por=d["hunter_id"],
        )
        token = await _token_para(client, "bastao_hunter@hipo.com")
        r = await client.get("/carteira/bastoes/meus", headers=_auth_header(token))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["hunter_nome"] == d["hunter_nome"]
