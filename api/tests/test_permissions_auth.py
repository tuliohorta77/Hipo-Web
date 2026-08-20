"""
HIPO — Testes de permissões por cargo e endpoints de auth.

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
    CARGOS_COM_PARCEIROS,
    CARGOS_GESTAO,
    CARGOS_OPERACIONAIS,
    CARGOS_VALIDOS,
    MODULOS_BASE,
    modulos_do_cargo,
    requer_modulo,
    requer_qualquer_modulo,
)
from tests.conftest import criar_usuario


# ── Função pura ──────────────────────────────────────────────────

class TestModulosDoCargo:
    @pytest.mark.parametrize("cargo", sorted(CARGOS_GESTAO))
    def test_gestao_tem_base_mais_usuarios_e_parceiros(self, cargo):
        assert modulos_do_cargo(cargo) == {"perfil", "crm", "usuarios", "parceiros", "telemetria"}

    @pytest.mark.parametrize(
        "cargo", sorted(CARGOS_OPERACIONAIS - CARGOS_COM_PARCEIROS)
    )
    def test_operacional_sem_carteira_tem_so_a_base(self, cargo):
        """SDR, EV e EP não trabalham carteira de parceiro."""
        assert modulos_do_cargo(cargo) == {"perfil", "crm"}

    @pytest.mark.parametrize(
        "cargo", sorted(CARGOS_OPERACIONAIS & CARGOS_COM_PARCEIROS)
    )
    def test_operacional_com_carteira_ganha_parceiros(self, cargo):
        """
        O EC é o único cargo operacional acima da base. Cultivar a relação
        com quem indica é trabalho dele — é a diretriz "uma tela por função"
        aplicada à permissão, não só ao layout.
        """
        assert modulos_do_cargo(cargo) == {"perfil", "crm", "parceiros"}

    def test_ec_e_o_unico_operacional_com_parceiros(self):
        """
        Guarda contra alguém liberar o módulo para SDR ou EV "só para ver".
        Se este teste cair, a decisão mudou e o doc precisa mudar junto.
        """
        assert CARGOS_OPERACIONAIS & CARGOS_COM_PARCEIROS == {"EC"}

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_parceiros_so_para_quem_trabalha_carteira(self, cargo):
        esperado = cargo in CARGOS_COM_PARCEIROS
        assert ("parceiros" in modulos_do_cargo(cargo)) is esperado

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_todo_cargo_valido_recebe_a_base(self, cargo):
        """Nenhum cargo válido pode ficar sem perfil e sem crm."""
        assert MODULOS_BASE <= modulos_do_cargo(cargo)

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_todo_cargo_valido_ve_o_crm(self, cargo):
        """
        Base compartilhada: se um cargo não visse contas, bateria em CNPJ
        duplicado sem conseguir enxergar o registro que causou o conflito.
        """
        assert "crm" in modulos_do_cargo(cargo)

    @pytest.mark.parametrize("cargo", sorted(CARGOS_OPERACIONAIS))
    def test_operacional_nao_administra_usuarios(self, cargo):
        assert "usuarios" not in modulos_do_cargo(cargo)

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

    def test_retorno_e_copia_independente(self):
        """
        modulos_do_cargo devolve conjuntos derivados de MODULOS_BASE; se
        devolvesse a própria constante, um caller que fizesse .add()
        contaminaria as permissões de todos os cargos do processo.
        """
        m = modulos_do_cargo("EC")
        m.add("invadido")
        assert "invadido" not in MODULOS_BASE
        assert "invadido" not in modulos_do_cargo("EC")


# ── /auth/me ─────────────────────────────────────────────────────

class TestAuthMe:
    async def test_me_retorna_cargo_e_modulos(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EC", "ec1@teste.com")
        resp = await client.get("/auth/me", headers=u["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "ec1@teste.com"
        assert body["cargo"] == "EC"
        assert sorted(body["modulos"]) == ["crm", "parceiros", "perfil"]

    async def test_me_franqueado_ve_usuarios(self, db_conn, client, usuario_franqueado):
        resp = await client.get("/auth/me", headers=usuario_franqueado["headers"])
        assert resp.status_code == 200
        assert sorted(resp.json()["modulos"]) == [
            "crm", "parceiros", "perfil", "telemetria", "usuarios",
        ]

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
# Exercitados contra um app descartável, com um módulo que ninguém tem
# ('financeiro', que só existe na Etapa 4). Assim os guards continuam
# cobertos independentemente de quais routers reais existem hoje.

def _app_com_guards() -> FastAPI:
    app_teste = FastAPI()

    @app_teste.get("/so-usuarios", dependencies=[Depends(requer_modulo("usuarios"))])
    async def so_usuarios():
        return {"ok": True}

    @app_teste.get("/so-crm", dependencies=[Depends(requer_modulo("crm"))])
    async def so_crm():
        return {"ok": True}

    @app_teste.get("/inexistente", dependencies=[Depends(requer_modulo("financeiro"))])
    async def inexistente():
        return {"ok": True}

    @app_teste.get(
        "/crm-ou-usuarios",
        dependencies=[Depends(requer_qualquer_modulo(["crm", "usuarios"]))],
    )
    async def crm_ou_usuarios():
        return {"ok": True}

    return app_teste


async def _get(rota: str, headers: dict):
    async with AsyncClient(
        transport=ASGITransport(app=_app_com_guards(), raise_app_exceptions=True),
        base_url="http://guards",
    ) as c:
        return await c.get(rota, headers=headers)


class TestGuards:
    async def test_operacional_bloqueado_em_modulo_de_gestao(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "SDR", "sdr-guard@teste.com")
        resp = await _get("/so-usuarios", u["headers"])
        assert resp.status_code == 403
        assert "usuarios" in resp.text

    async def test_gestao_passa_em_modulo_de_gestao(self, db_conn, client, usuario_adm):
        resp = await _get("/so-usuarios", usuario_adm["headers"])
        assert resp.status_code == 200

    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM", "EC", "SDR", "EV", "EP"])
    async def test_todo_cargo_valido_passa_no_crm(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"{cargo.lower()}-g@teste.com")
        resp = await _get("/so-crm", u["headers"])
        assert resp.status_code == 200

    async def test_cargo_extinto_bloqueado_no_crm(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Hunter", "hunter-g@teste.com")
        resp = await _get("/so-crm", u["headers"])
        assert resp.status_code == 403

    async def test_modulo_inexistente_bloqueia_ate_a_gestao(
        self, db_conn, client, usuario_adm
    ):
        """'financeiro' só entra na Etapa 4 — até lá ninguém passa."""
        resp = await _get("/inexistente", usuario_adm["headers"])
        assert resp.status_code == 403

    async def test_requer_qualquer_modulo_libera_com_um_deles(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EV", "ev-guard@teste.com")
        resp = await _get("/crm-ou-usuarios", u["headers"])
        assert resp.status_code == 200

    async def test_requer_qualquer_modulo_bloqueia_sem_nenhum(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Farmer", "farmer-guard@teste.com")
        resp = await _get("/crm-ou-usuarios", u["headers"])
        assert resp.status_code == 403

    async def test_requer_qualquer_modulo_lista_vazia_erra(self):
        with pytest.raises(ValueError):
            requer_qualquer_modulo([])
