"""
HIPO — Testes de permissões por cargo e endpoints de auth.

Consolida o que antes estava espalhado em test_permissions.py,
test_permissions_auth.py e test_permissions_sdr.py.

Cobertura:
  - modulos_do_cargo devolve o conjunto certo para cada cargo canônico
  - cargos extintos (Gerente, Hunter, Farmer) não recebem módulo nenhum
  - GET /auth/me devolve cargo + módulos
  - PUT /auth/senha troca a senha; erros retornam 400/422
  - requer_modulo e requer_qualquer_modulo bloqueiam e liberam corretamente
"""
import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient, ASGITransport

from routers.permissions import (
    CARGOS_GESTAO,
    CARGOS_OPERACIONAIS,
    CARGOS_VALIDOS,
    modulos_do_cargo,
    requer_modulo,
    requer_qualquer_modulo,
)
from tests.conftest import criar_usuario


# ── Função pura ──────────────────────────────────────────────────

class TestModulosDoCargo:
    def test_franqueado_tem_perfil_e_usuarios(self):
        assert modulos_do_cargo("Franqueado") == {"perfil", "usuarios"}

    def test_adm_tem_perfil_e_usuarios(self):
        assert modulos_do_cargo("ADM") == {"perfil", "usuarios"}

    @pytest.mark.parametrize("cargo", sorted(CARGOS_OPERACIONAIS))
    def test_operacional_tem_so_perfil(self, cargo):
        assert modulos_do_cargo(cargo) == {"perfil"}

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_todo_cargo_valido_tem_perfil(self, cargo):
        """Nenhum cargo válido pode ficar sem módulo — senão não usa o sistema."""
        assert "perfil" in modulos_do_cargo(cargo)

    @pytest.mark.parametrize("cargo", ["Gerente", "Hunter", "Farmer"])
    def test_cargos_extintos_nao_tem_modulo(self, cargo):
        """Gerente saiu; Hunter e Farmer foram fundidos em EC."""
        assert modulos_do_cargo(cargo) == set()

    def test_cargo_desconhecido_nada(self):
        assert modulos_do_cargo("DesconhecidoXYZ") == set()

    def test_cargo_none_nada(self):
        assert modulos_do_cargo(None) == set()

    def test_cargo_vazio_nada(self):
        assert modulos_do_cargo("") == set()

    def test_gestao_e_operacional_nao_se_sobrepoem(self):
        assert CARGOS_GESTAO & CARGOS_OPERACIONAIS == set()


# ── /auth/me ─────────────────────────────────────────────────────

class TestAuthMe:
    async def test_me_retorna_cargo_e_modulos(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ec1@teste.com")
        resp = await client.get("/auth/me", headers=u["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "ec1@teste.com"
        assert body["cargo"] == "EC"
        assert body["modulos"] == ["perfil"]

    async def test_me_franqueado_ve_usuarios(self, db_conn, client, usuario_franqueado):
        resp = await client.get("/auth/me", headers=usuario_franqueado["headers"])
        assert resp.status_code == 200
        assert sorted(resp.json()["modulos"]) == ["perfil", "usuarios"]

    async def test_me_cargo_extinto_sem_modulos(self, db_conn, client):
        """Usuário que sobrou com cargo Gerente loga mas não vê nada."""
        u = await criar_usuario(db_conn, client, "Gerente", "ex-gerente@teste.com")
        resp = await client.get("/auth/me", headers=u["headers"])
        assert resp.status_code == 200
        assert resp.json()["modulos"] == []

    async def test_me_sem_token_retorna_401(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


# ── PUT /auth/senha ──────────────────────────────────────────────

class TestTrocarSenha:
    async def test_troca_senha_com_sucesso(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ts1@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": u["senha"], "nova_senha": "novasenha999"},
        )
        assert resp.status_code == 200
        assert "sucesso" in resp.json()["message"].lower()

        resp = await client.post(
            "/auth/login",
            data={"username": u["email"], "password": "novasenha999"},
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/auth/login",
            data={"username": u["email"], "password": u["senha"]},
        )
        assert resp.status_code == 401

    async def test_senha_atual_errada_retorna_400(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ts2@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": "errada", "nova_senha": "novasenha"},
        )
        assert resp.status_code == 400
        assert "incorreta" in resp.json()["detail"].lower()

    async def test_nova_senha_igual_atual_retorna_400(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ts3@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": u["senha"], "nova_senha": u["senha"]},
        )
        assert resp.status_code == 400

    async def test_nova_senha_muito_curta_retorna_422(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ts4@teste.com")
        resp = await client.put(
            "/auth/senha",
            headers=u["headers"],
            json={"senha_atual": u["senha"], "nova_senha": "abc"},
        )
        assert resp.status_code == 422  # Pydantic min_length=6

    async def test_sem_token_retorna_401(self, client):
        resp = await client.put(
            "/auth/senha",
            json={"senha_atual": "x", "nova_senha": "yyyyyy"},
        )
        assert resp.status_code == 401


# ── Guards de módulo ─────────────────────────────────────────────
#
# Nenhum router protegido existe na Sprint 0, então os guards são
# exercitados contra um app descartável. Assim a cobertura de
# requer_modulo / requer_qualquer_modulo não fica órfã até a Sprint 1.

def _app_com_guards() -> FastAPI:
    app_teste = FastAPI()

    @app_teste.get("/so-usuarios", dependencies=[Depends(requer_modulo("usuarios"))])
    async def so_usuarios():
        return {"ok": True}

    @app_teste.get("/so-crm", dependencies=[Depends(requer_modulo("crm"))])
    async def so_crm():
        return {"ok": True}

    @app_teste.get(
        "/perfil-ou-usuarios",
        dependencies=[Depends(requer_qualquer_modulo(["perfil", "usuarios"]))],
    )
    async def perfil_ou_usuarios():
        return {"ok": True}

    return app_teste


class TestGuards:
    async def test_operacional_bloqueado_em_modulo_de_gestao(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "SDR", "sdr-guard@teste.com")
        async with AsyncClient(
            transport=ASGITransport(app=_app_com_guards(), raise_app_exceptions=True),
            base_url="http://guards",
        ) as c:
            resp = await c.get("/so-usuarios", headers=u["headers"])
        assert resp.status_code == 403
        assert "usuarios" in resp.text

    async def test_gestao_passa_em_modulo_de_gestao(self, db_conn, client, usuario_adm):
        async with AsyncClient(
            transport=ASGITransport(app=_app_com_guards(), raise_app_exceptions=True),
            base_url="http://guards",
        ) as c:
            resp = await c.get("/so-usuarios", headers=usuario_adm["headers"])
        assert resp.status_code == 200

    async def test_modulo_inexistente_bloqueia_todo_mundo(self, db_conn, client, usuario_adm):
        """'crm' só entra na Sprint 1 — até lá ninguém passa."""
        async with AsyncClient(
            transport=ASGITransport(app=_app_com_guards(), raise_app_exceptions=True),
            base_url="http://guards",
        ) as c:
            resp = await c.get("/so-crm", headers=usuario_adm["headers"])
        assert resp.status_code == 403

    async def test_requer_qualquer_modulo_libera_com_um_deles(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EV", "ev-guard@teste.com")
        async with AsyncClient(
            transport=ASGITransport(app=_app_com_guards(), raise_app_exceptions=True),
            base_url="http://guards",
        ) as c:
            resp = await c.get("/perfil-ou-usuarios", headers=u["headers"])
        assert resp.status_code == 200

    async def test_requer_qualquer_modulo_lista_vazia_erra(self):
        with pytest.raises(ValueError):
            requer_qualquer_modulo([])
