"""
HIPO — Conta de TV (cargo Monitor): acesso SÓ ao painel do Monitor.

Cobertura:
  - modulos_do_cargo('Monitor') == {'monitor'}; Monitor fora de CARGOS_VALIDOS
  - /auth/me devolve só o módulo 'monitor'
  - /monitor/painel, /monitor/metas (GET) e /monitor/feriados liberados
  - escrita de metas e RPeR continuam barrados (requer_gestao)
  - CRM, relatórios, parceiros e telemetria barrados (403)
  - a conta de TV não aparece no seletor de envolvidos
  - validação do script criar_usuario_monitor
"""
import pytest

from routers.permissions import CARGO_MONITOR, CARGOS_VALIDOS, modulos_do_cargo
from scripts.criar_usuario_monitor import validar
from tests.conftest import criar_usuario


# ── Função pura ──────────────────────────────────────────────────

class TestModulosDoMonitor:
    def test_monitor_ve_so_o_monitor(self):
        assert modulos_do_cargo(CARGO_MONITOR) == {"monitor"}

    def test_monitor_nao_e_cargo_de_gente(self):
        assert CARGO_MONITOR not in CARGOS_VALIDOS

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_nenhum_cargo_de_gente_ganha_o_modulo_monitor(self, cargo):
        """Os demais entram no painel pelo 'crm' — sem relogin, sem assert quebrado."""
        assert "monitor" not in modulos_do_cargo(cargo)


class TestValidarScript:
    def test_aceita_login_curto_sem_arroba(self):
        validar("m1", "Monitor m1", "123456")

    @pytest.mark.parametrize("login,nome,senha", [
        ("", "Monitor", "123456"),
        ("   ", "Monitor", "123456"),
        ("m1", "", "123456"),
        ("m1", "Monitor", "12345"),
        ("x" * 151, "Monitor", "123456"),
    ])
    def test_rejeita_entrada_invalida(self, login, nome, senha):
        with pytest.raises(ValueError):
            validar(login, nome, senha)


# ── API ──────────────────────────────────────────────────────────

@pytest.fixture
async def tv(db_conn, client):
    return await criar_usuario(db_conn, client, CARGO_MONITOR, "m1")


class TestContaDeTv:
    async def test_login_curto_sem_arroba_funciona(self, tv):
        assert tv["token"]

    async def test_me_devolve_so_o_monitor(self, tv, client):
        resp = await client.get("/auth/me", headers=tv["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["cargo"] == "Monitor"
        assert body["modulos"] == ["monitor"]

    @pytest.mark.parametrize("rota", [
        "/monitor/painel",
        "/monitor/metas",
        "/monitor/feriados",
        "/monitor/detalhe/lead",
    ])
    async def test_leitura_do_monitor_liberada(self, tv, client, rota):
        resp = await client.get(rota, headers=tv["headers"])
        assert resp.status_code == 200, resp.text

    async def test_nao_edita_meta(self, tv, client):
        resp = await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 3, "metas": [{"indicador": "lead", "valor": 10}]},
            headers=tv["headers"],
        )
        assert resp.status_code == 403

    async def test_nao_cadastra_feriado(self, tv, client):
        resp = await client.post(
            "/monitor/feriados",
            json={"data": "2026-03-04", "motivo": "x"},
            headers=tv["headers"],
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize("rota", [
        "/crm/oportunidades",
        "/crm/contas",
        "/crm/tarefas",
        "/crm/agenda/tipos",
        "/crm/dominio/usuarios",
        "/crm/relatorios/salvos",
        "/crm/parceiros",
        "/rper/metas",
        "/telemetria/dia",
    ])
    async def test_resto_do_sistema_barrado(self, tv, client, rota):
        resp = await client.get(rota, headers=tv["headers"])
        assert resp.status_code == 403, f"{rota}: {resp.status_code} {resp.text}"

    async def test_tv_fora_do_seletor_de_envolvidos(self, tv, client, usuario_adm):
        resp = await client.get("/crm/dominio/usuarios", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        cargos = {u["cargo"] for u in resp.json()}
        assert "Monitor" not in cargos
        assert "ADM" in cargos
