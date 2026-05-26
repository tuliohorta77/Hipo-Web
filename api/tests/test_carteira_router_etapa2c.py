"""
HIPO — Testes do Commit 2c da v1.3.0: filtragem do /dashboard/farmer.

Foco:
  - GET /carteira/dashboard/farmer — Farmer operacional vê só a linha dele
  - admin/gestão continuam vendo todos os Farmers
  - Farmer sem vínculo recebe campo 'aviso'

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).
Assume a migration 011 aplicada (coluna usuario_id).
"""
import bcrypt


# ── Helpers de seeding ───────────────────────────────────────────

async def _login(client, db_conn, nome: str, email: str, cargo: str) -> dict:
    senha = "test123"
    pwd_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
    row = await db_conn.fetchrow(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, TRUE)
        RETURNING id
        """,
        nome, email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login", data={"username": email, "password": senha}
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {"id": str(row["id"]), "headers": {"Authorization": f"Bearer {token}"}}


async def _seed_colaborador(db_conn, nome: str, funcao: str,
                            usuario_id: str | None = None) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_colaborador (nome, funcao, ativo, usuario_id)
        VALUES ($1, $2::carteira_funcao_enum, TRUE, $3)
        RETURNING id
        """,
        nome, funcao, usuario_id,
    )
    return str(row["id"])


async def _seed_upload(db_conn, tipo: str) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_upload
            (tipo, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ($1, 'seed.xlsx', 1, 1, TRUE)
        RETURNING id
        """,
        tipo,
    )
    return str(row["id"])


async def _seed_cnpj(db_conn, upload_id: str, id_grupo: str, cnpj: str,
                     colaborador_nome: str, leads_no_mes: int = 0):
    await db_conn.execute(
        """
        INSERT INTO carteira_cnpj (
            upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade,
            cidade_uf, parceria, tipo_cnae, colaborador_nome,
            funcao_origem, leads_no_mes
        )
        VALUES ($1, $2, 'Grupo', $3, 'Contab', 'SP/SP', 'Parceiro',
                'CNAE Contábil', $4, 'Executivo de Contas - FR', $5)
        """,
        upload_id, id_grupo, cnpj, colaborador_nome, leads_no_mes,
    )


# ── DASHBOARD FARMER — filtragem por usuário (Commit 2c) ─────────

class TestDashboardFarmerFiltrado:
    async def test_admin_ve_todos_os_farmers(self, db_conn, client, usuario_adm):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_colaborador(db_conn, "Jheison", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "A1", "11.111.111/0001-11", "Aline")
        await _seed_cnpj(db_conn, upload, "J1", "22.222.222/0002-22", "Jheison")

        resp = await client.get(
            "/carteira/dashboard/farmer", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        nomes = {l["nome"] for l in resp.json()["linhas"]}
        assert nomes == {"Aline", "Jheison"}

    async def test_farmer_ve_apenas_a_propria_linha(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        aline = await _login(client, db_conn, "Aline", "aline@teste.com", "Farmer")
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER",
                                usuario_id=aline["id"])
        await _seed_colaborador(db_conn, "Jheison", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "A1", "11.111.111/0001-11", "Aline")
        await _seed_cnpj(db_conn, upload, "J1", "22.222.222/0002-22", "Jheison")

        resp = await client.get(
            "/carteira/dashboard/farmer", headers=aline["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        nomes = {l["nome"] for l in data["linhas"]}
        assert nomes == {"Aline"}  # NÃO vê o Jheison
        assert data["total"] == 1

    async def test_farmer_sem_vinculo_recebe_aviso(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        novato = await _login(client, db_conn, "Novato", "novato@teste.com", "Farmer")
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "A1", "11.111.111/0001-11", "Aline")

        resp = await client.get(
            "/carteira/dashboard/farmer", headers=novato["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["linhas"] == []
        assert data["total"] == 0
        assert data["aviso"] is not None
        assert "configurada" in data["aviso"].lower()

    async def test_hunter_logado_nao_ve_farmers(self, db_conn, client):
        """Hunter (operacional) vinculado a um colab Hunter: /dashboard/farmer
        filtra pelo nome dele, que não é Farmer -> lista vazia."""
        upload = await _seed_upload(db_conn, "CARTEIRA")
        beatriz = await _login(client, db_conn, "Beatriz", "bea@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Beatriz", "EC_HUNTER",
                                usuario_id=beatriz["id"])
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "A1", "11.111.111/0001-11", "Aline")

        resp = await client.get(
            "/carteira/dashboard/farmer", headers=beatriz["headers"]
        )
        assert resp.status_code == 200
        # Beatriz é Hunter; nenhuma linha Farmer tem o nome "Beatriz"
        assert resp.json()["linhas"] == []
