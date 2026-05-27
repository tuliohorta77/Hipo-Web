"""
HIPO — Testes de permissões por cargo e endpoints de auth.

Cobertura:
  - Cargo ADM/Franqueado acessa todos os módulos
  - Cargo Hunter/Farmer/EP/Gerente acessa SÓ Carteira; outros endpoints → 403
  - Cargo EV acessa 'clientes' (Vendas + Clientes), NÃO acessa Carteira
  - GET /auth/me retorna o cargo + lista de módulos
  - PUT /auth/senha troca a senha; senha errada retorna 400
  - Helper modulos_do_cargo retorna conjuntos corretos
"""
import bcrypt
import pytest

from routers.permissions import modulos_do_cargo


# ── Testes unitários da função pura ──────────────────────────────

class TestModulosDoCargo:
    def test_adm_ve_tudo(self):
        m = modulos_do_cargo("ADM")
        assert m == {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"}

    def test_franqueado_ve_tudo(self):
        m = modulos_do_cargo("Franqueado")
        assert m == {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"}

    def test_hunter_ve_so_carteira(self):
        assert modulos_do_cargo("Hunter") == {"carteira"}

    def test_farmer_ve_so_carteira(self):
        assert modulos_do_cargo("Farmer") == {"carteira"}

    def test_ep_ve_carteira_e_clientes(self):
        assert modulos_do_cargo("EP") == {"carteira", "clientes"}

    def test_gerente_ve_carteira_e_clientes(self):
        assert modulos_do_cargo("Gerente") == {"carteira", "clientes"}

    def test_ev_ve_so_clientes(self):
        # EV (Executivo de Vendas): Clientes + Vendas, SEM Contadores.
        assert modulos_do_cargo("EV") == {"clientes"}

    def test_cargos_compat_antigos_ve_so_carteira(self):
        # SDR e EC permanecem como compatibilidade (só carteira).
        assert modulos_do_cargo("SDR") == {"carteira"}
        assert modulos_do_cargo("EC") == {"carteira"}

    def test_cargo_desconhecido_nada(self):
        assert modulos_do_cargo("DesconhecidoXYZ") == set()

    def test_cargo_none_nada(self):
        assert modulos_do_cargo(None) == set()

    def test_cargo_vazio_nada(self):
        assert modulos_do_cargo("") == set()


# ── Fixtures: usuários com cargos variados ───────────────────────

_SENHA = "test123"


async def _seed_user(db_conn, client, cargo: str, email: str = None):
    """Cria usuário com o cargo, retorna token + headers."""
    email = email or f"user-{cargo.lower()}@teste.com"
    pwd_hash = bcrypt.hashpw(_SENHA.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ($1, $2, $3, $4)
        """,
        f"Test {cargo}", email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA},
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {"email": email, "cargo": cargo, "token": token,
            "headers": {"Authorization": f"Bearer {token}"}}


# ── /auth/me ─────────────────────────────────────────────────────

class TestAuthMe:
    async def test_me_retorna_cargo_e_modulos(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f1@teste.com")
        resp = await client.get("/auth/me", headers=u["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "f1@teste.com"
        assert body["cargo"] == "Farmer"
        assert body["modulos"] == ["carteira"]

    async def test_me_adm_ve_todos_modulos(self, db_conn, client, usuario_adm):
        resp = await client.get("/auth/me", headers=usuario_adm["headers"])
        body = resp.json()
        assert set(body["modulos"]) == {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"}

    async def test_me_ev_ve_so_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "EV", "ev1@teste.com")
        resp = await client.get("/auth/me", headers=u["headers"])
        body = resp.json()
        assert body["cargo"] == "EV"
        assert body["modulos"] == ["clientes"]

    async def test_me_sem_token_retorna_401(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


# ── Bloqueio de módulos ──────────────────────────────────────────

class TestBloqueioPorModulo:
    async def test_hunter_no_pex_recebe_403(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h@teste.com")
        resp = await client.get("/pex/painel", headers=u["headers"])
        assert resp.status_code == 403
        assert "carteira" in resp.text.lower() or "hunter" in resp.text.lower() or "modulo" in resp.text.lower() or "módulo" in resp.text.lower()

    async def test_farmer_no_po_recebe_403(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "ff@teste.com")
        resp = await client.get("/po/reconciliacao/ultima", headers=u["headers"])
        assert resp.status_code == 403

    async def test_ep_no_bd_recebe_403(self, db_conn, client):
        u = await _seed_user(db_conn, client, "EP", "ep@teste.com")
        resp = await client.get("/bd-ativados/resumo", headers=u["headers"])
        assert resp.status_code == 403

    async def test_gerente_no_metas_recebe_403(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Gerente", "g@teste.com")
        resp = await client.get("/metas/catalogo", headers=u["headers"])
        assert resp.status_code == 403

    async def test_ev_no_carteira_recebe_403(self, db_conn, client):
        """EV NÃO tem módulo 'carteira' — tem que bloquear."""
        u = await _seed_user(db_conn, client, "EV", "ev-block@teste.com")
        resp = await client.get(
            "/carteira/dashboard/hunter", headers=u["headers"]
        )
        assert resp.status_code == 403

    async def test_ev_no_pex_recebe_403(self, db_conn, client):
        """EV NÃO tem módulo 'pex'."""
        u = await _seed_user(db_conn, client, "EV", "ev-pex@teste.com")
        resp = await client.get("/pex/painel", headers=u["headers"])
        assert resp.status_code == 403

    async def test_ev_acessa_vendas_e_clientes(self, db_conn, client):
        """EV tem módulo 'clientes' — vendas e clientes liberados."""
        u = await _seed_user(db_conn, client, "EV", "ev-ok@teste.com")
        # Vendas é protegida por requer_modulo('clientes').
        resp = await client.get(
            "/vendas/funil-cromie/filtros", headers=u["headers"]
        )
        assert resp.status_code != 403, "EV foi bloqueado de Vendas"
        resp = await client.get("/vendas/funil", headers=u["headers"])
        assert resp.status_code != 403, "EV foi bloqueado de /vendas/funil"

    async def test_adm_passa_em_todos_modulos(self, client, usuario_adm):
        for rota in ["/pex/painel", "/po/reconciliacao/ultima", "/bd-ativados/resumo"]:
            resp = await client.get(rota, headers=usuario_adm["headers"])
            assert resp.status_code != 403, f"{rota} retornou 403 pro ADM!"

    async def test_franqueado_passa_em_todos_modulos(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Franqueado", "fq@teste.com")
        for rota in ["/pex/painel", "/po/reconciliacao/ultima", "/bd-ativados/resumo"]:
            resp = await client.get(rota, headers=u["headers"])
            assert resp.status_code != 403, f"{rota} retornou 403 pro Franqueado!"

    async def test_todos_cargos_com_carteira_acessam_carteira(self, db_conn, client):
        # Cargos que TÊM 'carteira' devem passar. EV NÃO entra nesta lista:
        # EV não tem 'carteira' (testado em test_ev_no_carteira_recebe_403).
        for cargo in ["Hunter", "Farmer", "EP", "Gerente", "Franqueado"]:
            u = await _seed_user(db_conn, client, cargo, f"u-{cargo.lower()}@teste.com")
            resp = await client.get("/carteira/dashboard/hunter", headers=u["headers"])
            assert resp.status_code != 403, f"Cargo {cargo} bloqueado da Carteira!"


# ── PUT /auth/senha ──────────────────────────────────────────────

class TestTrocarSenha:
    async def test_troca_senha_com_sucesso(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "ts1@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": _SENHA, "nova_senha": "novasenha999"},
        )
        assert resp.status_code == 200
        assert "sucesso" in resp.json()["message"].lower()

        # Login com a nova senha funciona
        resp = await client.post(
            "/auth/login",
            data={"username": u["email"], "password": "novasenha999"},
        )
        assert resp.status_code == 200

        # Login com a senha antiga falha
        resp = await client.post(
            "/auth/login",
            data={"username": u["email"], "password": _SENHA},
        )
        assert resp.status_code == 401

    async def test_senha_atual_errada_retorna_400(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "ts2@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": "errada", "nova_senha": "novasenha"},
        )
        assert resp.status_code == 400
        assert "incorreta" in resp.json()["detail"].lower()

    async def test_nova_senha_igual_atual_retorna_400(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "ts3@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": _SENHA, "nova_senha": _SENHA},
        )
        assert resp.status_code == 400

    async def test_nova_senha_muito_curta_retorna_422(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "ts4@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": _SENHA, "nova_senha": "abc"},
        )
        assert resp.status_code == 422  # Pydantic min_length=6

    async def test_sem_token_retorna_401(self, client):
        resp = await client.put(
            "/auth/senha",
            json={"senha_atual": "x", "nova_senha": "yyyyyy"},
        )
        assert resp.status_code == 401
