"""
HIPO — Testes do Commit 2a da v1.3.0: visibilidade por colaborador.

Foco:
  - GET /carteira/dashboard/hunter  — operacional vê só a linha dele
  - GET /carteira/resumo            — operacional vê KPIs só dele
  - GET /carteira/colaboradores/{id}/grupos — 403 no acesso cruzado
  - operacional sem vínculo recebe campo 'aviso'
  - admin/gestão continuam vendo tudo

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).
Assume a migration 011 aplicada (coluna usuario_id).

NOTA: /dashboard/farmer NÃO é testado para filtragem aqui — no Commit 2a
ele permanece sem filtro de propósito (o filtro do Farmer entra no 2c).
"""
import bcrypt
from uuid import uuid4


# ── Helpers de seeding ───────────────────────────────────────────

async def _seed_colaborador(db_conn, nome: str, funcao: str = "OUTROS",
                             usuario_id: str | None = None) -> str:
    """Insere um colaborador na carteira. Retorna o UUID (str)."""
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_colaborador (nome, funcao, ativo, usuario_id)
        VALUES ($1, $2::carteira_funcao_enum, TRUE, $3)
        RETURNING id
        """,
        nome, funcao, usuario_id,
    )
    return str(row["id"])


async def _seed_usuario(db_conn, nome: str, email: str,
                        cargo: str, ativo: bool = True) -> str:
    """Insere um usuário. Retorna o UUID (str)."""
    pwd_hash = bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()
    row = await db_conn.fetchrow(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        nome, email, pwd_hash, cargo, ativo,
    )
    return str(row["id"])


async def _login(client, db_conn, email: str, cargo: str) -> dict:
    """Cria um usuário com senha conhecida e devolve headers autenticados."""
    senha = "test123"
    pwd_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
    row = await db_conn.fetchrow(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, TRUE)
        RETURNING id
        """,
        f"User {cargo}", email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login", data={"username": email, "password": senha}
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {"id": str(row["id"]), "headers": {"Authorization": f"Bearer {token}"}}


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
                     colaborador_nome: str, leads_no_mes: int = 0,
                     contabilidade: str = "Contab X"):
    await db_conn.execute(
        """
        INSERT INTO carteira_cnpj (
            upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade,
            cidade_uf, parceria, tipo_cnae, colaborador_nome,
            funcao_origem, leads_no_mes
        )
        VALUES ($1, $2, $3, $4, $5, 'SP/SP', 'Parceiro',
                'CNAE Contábil', $6, 'Executivo de Contas - FR', $7)
        """,
        upload_id, id_grupo, contabilidade, cnpj, contabilidade,
        colaborador_nome, leads_no_mes,
    )


# ── DASHBOARD HUNTER — filtragem por usuário ─────────────────────

class TestDashboardHunterFiltrado:
    async def test_admin_ve_todos_os_hunters(self, db_conn, client, usuario_adm):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11", "Patrick")
        await _seed_cnpj(db_conn, upload, "C1", "22.222.222/0002-22", "Caio")

        resp = await client.get(
            "/carteira/dashboard/hunter", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        nomes = {l["nome"] for l in resp.json()["linhas"]}
        assert nomes == {"Patrick", "Caio"}

    async def test_hunter_ve_apenas_a_propria_linha(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        # Patrick vinculado ao colaborador "Patrick"
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                usuario_id=patrick["id"])
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11", "Patrick")
        await _seed_cnpj(db_conn, upload, "C1", "22.222.222/0002-22", "Caio")

        resp = await client.get(
            "/carteira/dashboard/hunter", headers=patrick["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        nomes = {l["nome"] for l in data["linhas"]}
        assert nomes == {"Patrick"}  # NÃO vê o Caio
        assert data["total"] == 1

    async def test_hunter_sem_vinculo_recebe_aviso(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        # Hunter logado, mas nenhum colaborador aponta pra ele
        hunter = await _login(client, db_conn, "novato@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11", "Patrick")

        resp = await client.get(
            "/carteira/dashboard/hunter", headers=hunter["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["linhas"] == []
        assert data["total"] == 0
        assert data["aviso"] is not None
        assert "configurada" in data["aviso"].lower()


# ── RESUMO — filtragem por usuário ───────────────────────────────

class TestResumoFiltrado:
    async def test_admin_ve_resumo_completo(self, db_conn, client, usuario_adm):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11",
                         "Patrick", leads_no_mes=3)
        await _seed_cnpj(db_conn, upload, "C1", "22.222.222/0002-22",
                         "Caio", leads_no_mes=2)

        resp = await client.get(
            "/carteira/resumo", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        # 2 grupos Hunter no total
        assert data["hunter"]["total_grupos"] == 2
        assert data["aviso"] is None

    async def test_hunter_ve_resumo_apenas_dele(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                usuario_id=patrick["id"])
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11",
                         "Patrick", leads_no_mes=3)
        await _seed_cnpj(db_conn, upload, "C1", "22.222.222/0002-22",
                         "Caio", leads_no_mes=2)

        resp = await client.get(
            "/carteira/resumo", headers=patrick["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        # só o grupo do Patrick
        assert data["hunter"]["total_grupos"] == 1
        assert data["hunter"]["leads_no_mes"] == 3  # não soma os 2 do Caio

    async def test_hunter_sem_vinculo_resumo_zerado_com_aviso(
        self, db_conn, client
    ):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        hunter = await _login(client, db_conn, "novato@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_cnpj(db_conn, upload, "P1", "11.111.111/0001-11", "Patrick")

        resp = await client.get(
            "/carteira/resumo", headers=hunter["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hunter"]["total_grupos"] == 0
        assert data["aviso"] is not None


# ── DRILLDOWN — 403 no acesso cruzado ────────────────────────────

class TestDrilldownAcessoCruzado:
    async def test_admin_acessa_qualquer_colaborador(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        resp = await client.get(
            f"/carteira/colaboradores/{colab_id}/grupos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["colaborador"]["nome"] == "Patrick"

    async def test_hunter_acessa_o_proprio_drilldown(self, db_conn, client):
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                           usuario_id=patrick["id"])
        resp = await client.get(
            f"/carteira/colaboradores/{colab_id}/grupos",
            headers=patrick["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["colaborador"]["nome"] == "Patrick"

    async def test_hunter_no_drilldown_alheio_recebe_403(self, db_conn, client):
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                usuario_id=patrick["id"])
        # colaborador de outra pessoa
        caio_id = await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")

        resp = await client.get(
            f"/carteira/colaboradores/{caio_id}/grupos",
            headers=patrick["headers"],
        )
        assert resp.status_code == 403

    async def test_hunter_sem_vinculo_no_drilldown_recebe_403(
        self, db_conn, client
    ):
        hunter = await _login(client, db_conn, "novato@teste.com", "Hunter")
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        resp = await client.get(
            f"/carteira/colaboradores/{colab_id}/grupos",
            headers=hunter["headers"],
        )
        # Sem vínculo + cargo operacional -> não tem acesso a ninguém
        assert resp.status_code == 403

    async def test_colaborador_inexistente_404_antes_do_403(
        self, db_conn, client
    ):
        """Colaborador inexistente -> 404 (independe do cargo)."""
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                usuario_id=patrick["id"])
        resp = await client.get(
            f"/carteira/colaboradores/{uuid4()}/grupos",
            headers=patrick["headers"],
        )
        assert resp.status_code == 404


# ── /grupos NÃO é filtrado (aba Outros visível a todos) ──────────

class TestGruposNaoFiltrado:
    async def test_hunter_ve_aba_outros_completa(self, db_conn, client):
        """Decisão de produto: a aba Outros é visível a todos os cargos."""
        upload = await _seed_upload(db_conn, "CARTEIRA")
        patrick = await _login(client, db_conn, "patrick@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER",
                                usuario_id=patrick["id"])
        # 2 grupos OUTROS de gente diferente (colaborador não mapeado)
        await _seed_cnpj(db_conn, upload, "X1", "33.333.333/0003-33", "Desconhecido A")
        await _seed_cnpj(db_conn, upload, "X2", "44.444.444/0004-44", "Desconhecido B")

        resp = await client.get(
            "/carteira/grupos?funcao=OUTROS", headers=patrick["headers"]
        )
        assert resp.status_code == 200
        # Hunter vê os 2 grupos OUTROS — sem filtro por usuário
        assert resp.json()["total"] == 2
