"""
HIPO — Testes da Etapa 1 da v1.3.0: vínculo usuário ↔ colaborador.

Foco:
  - PUT  /carteira/colaboradores/{id}   — agora grava usuario_id (tri-estado)
  - GET  /carteira/usuarios-ativos      — dropdown de vínculo
  - GET  /carteira/colaboradores        — traz usuario_id / usuario_email

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).
Estes testes assumem a migration 011 aplicada (coluna usuario_id +
constraint UNIQUE uq_colaborador_usuario).
"""
import bcrypt
from uuid import uuid4


# ── Helpers de seeding ───────────────────────────────────────────

async def _seed_colaborador(db_conn, nome: str, funcao: str = "OUTROS") -> str:
    """Insere um colaborador na carteira. Retorna o UUID (str)."""
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_colaborador (nome, funcao, ativo)
        VALUES ($1, $2::carteira_funcao_enum, TRUE)
        RETURNING id
        """,
        nome, funcao,
    )
    return str(row["id"])


async def _seed_usuario(db_conn, nome: str, email: str,
                        cargo: str = "Hunter", ativo: bool = True) -> str:
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


# ── GET /usuarios-ativos ─────────────────────────────────────────

class TestUsuariosAtivos:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.get("/carteira/usuarios-ativos")
        assert resp.status_code == 401

    async def test_lista_apenas_usuarios_ativos(self, db_conn, client, usuario_adm):
        # usuario_adm já existe (ativo). Adiciona 1 ativo e 1 inativo.
        await _seed_usuario(db_conn, "Patrick Hunter", "patrick@teste.com",
                            cargo="Hunter", ativo=True)
        await _seed_usuario(db_conn, "Ex Funcionario", "ex@teste.com",
                            cargo="Farmer", ativo=False)

        resp = await client.get(
            "/carteira/usuarios-ativos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        emails = {u["email"] for u in resp.json()}
        assert "patrick@teste.com" in emails
        assert "adm@teste.com" in emails
        assert "ex@teste.com" not in emails  # inativo não aparece

    async def test_campos_retornados(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/carteira/usuarios-ativos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        for u in resp.json():
            assert set(u.keys()) == {"id", "nome", "email"}
            assert "senha_hash" not in u  # nunca vaza hash de senha


# ── GET /colaboradores — agora com vínculo ───────────────────────

class TestColaboradoresComVinculo:
    async def test_colaborador_sem_vinculo_tem_campos_nulos(
        self, db_conn, client, usuario_adm
    ):
        await _seed_colaborador(db_conn, "Sem Dono", "OUTROS")
        resp = await client.get(
            "/carteira/colaboradores",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        linha = next(c for c in resp.json() if c["nome"] == "Sem Dono")
        assert linha["usuario_id"] is None
        assert linha["usuario_email"] is None
        assert linha["usuario_nome"] is None

    async def test_colaborador_vinculado_traz_email(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Patrick H", "patrick@teste.com")
        await db_conn.execute(
            "UPDATE carteira_colaborador SET usuario_id = $1 WHERE id = $2",
            user_id, colab_id,
        )
        resp = await client.get(
            "/carteira/colaboradores",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        linha = next(c for c in resp.json() if c["nome"] == "Patrick")
        assert linha["usuario_id"] == user_id
        assert linha["usuario_email"] == "patrick@teste.com"
        assert linha["usuario_nome"] == "Patrick H"


# ── PUT /colaboradores/{id} — vínculo (tri-estado) ───────────────

class TestVincularUsuario:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.put(f"/carteira/colaboradores/{uuid4()}")
        assert resp.status_code == 401

    async def test_vincula_usuario(self, db_conn, client, usuario_adm):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Patrick H", "patrick@teste.com")

        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_id},
        )
        assert resp.status_code == 200
        assert resp.json()["usuario_id"] == user_id

        # confirma persistência no banco
        gravado = await db_conn.fetchval(
            "SELECT usuario_id FROM carteira_colaborador WHERE id = $1", colab_id
        )
        assert str(gravado) == user_id

    async def test_desvincula_com_null(self, db_conn, client, usuario_adm):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Patrick H", "patrick@teste.com")
        await db_conn.execute(
            "UPDATE carteira_colaborador SET usuario_id = $1 WHERE id = $2",
            user_id, colab_id,
        )

        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["usuario_id"] is None

        gravado = await db_conn.fetchval(
            "SELECT usuario_id FROM carteira_colaborador WHERE id = $1", colab_id
        )
        assert gravado is None

    async def test_campo_ausente_preserva_vinculo(
        self, db_conn, client, usuario_adm
    ):
        """PUT só com `funcao` (sem usuario_id) NÃO pode apagar o vínculo."""
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Patrick H", "patrick@teste.com")
        await db_conn.execute(
            "UPDATE carteira_colaborador SET usuario_id = $1 WHERE id = $2",
            user_id, colab_id,
        )

        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_FARMER"},  # usuario_id ausente de propósito
        )
        assert resp.status_code == 200
        assert resp.json()["funcao"] == "EC_FARMER"
        # vínculo intacto
        assert resp.json()["usuario_id"] == user_id
        gravado = await db_conn.fetchval(
            "SELECT usuario_id FROM carteira_colaborador WHERE id = $1", colab_id
        )
        assert str(gravado) == user_id

    async def test_usuario_ja_vinculado_retorna_409(
        self, db_conn, client, usuario_adm
    ):
        """Cardinalidade 1:1 — mesmo usuário em 2 colaboradores -> 409."""
        colab_a = await _seed_colaborador(db_conn, "Colab A", "EC_HUNTER")
        colab_b = await _seed_colaborador(db_conn, "Colab B", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Usuario X", "x@teste.com")

        # vincula ao A — ok
        r1 = await client.put(
            f"/carteira/colaboradores/{colab_a}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_id},
        )
        assert r1.status_code == 200

        # tenta vincular o MESMO usuário ao B — deve falhar
        r2 = await client.put(
            f"/carteira/colaboradores/{colab_b}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_id},
        )
        assert r2.status_code == 409
        assert "Colab A" in r2.json()["detail"]

    async def test_usuario_inexistente_retorna_400(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": str(uuid4())},
        )
        assert resp.status_code == 400

    async def test_usuario_inativo_retorna_400(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        user_inativo = await _seed_usuario(
            db_conn, "Inativo", "inativo@teste.com", ativo=False
        )
        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_inativo},
        )
        assert resp.status_code == 400

    async def test_usuario_id_malformado_retorna_400(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": "nao-eh-uuid"},
        )
        assert resp.status_code == 400

    async def test_funcao_invalida_retorna_400(
        self, db_conn, client, usuario_adm
    ):
        colab_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        resp = await client.put(
            f"/carteira/colaboradores/{colab_id}",
            headers=usuario_adm["headers"],
            json={"funcao": "CARGO_QUE_NAO_EXISTE"},
        )
        assert resp.status_code == 400

    async def test_colaborador_inexistente_retorna_404(
        self, db_conn, client, usuario_adm
    ):
        resp = await client.put(
            f"/carteira/colaboradores/{uuid4()}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER"},
        )
        assert resp.status_code == 404

    async def test_revincular_usuario_apos_desvincular(
        self, db_conn, client, usuario_adm
    ):
        """Desvincular do A deve liberar o usuário para vincular ao B."""
        colab_a = await _seed_colaborador(db_conn, "Colab A", "EC_HUNTER")
        colab_b = await _seed_colaborador(db_conn, "Colab B", "EC_HUNTER")
        user_id = await _seed_usuario(db_conn, "Usuario X", "x@teste.com")

        await client.put(
            f"/carteira/colaboradores/{colab_a}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_id},
        )
        # desvincula do A
        await client.put(
            f"/carteira/colaboradores/{colab_a}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": None},
        )
        # agora vincular ao B deve funcionar
        r = await client.put(
            f"/carteira/colaboradores/{colab_b}",
            headers=usuario_adm["headers"],
            json={"funcao": "EC_HUNTER", "usuario_id": user_id},
        )
        assert r.status_code == 200
        assert r.json()["usuario_id"] == user_id
