"""
HIPO — Conta da UC (cargo UC): acesso SÓ à Universidade Corporativa.

Cobertura:
  - modulos_do_cargo('UC') == {'uc'}; UC fora de CARGOS_VALIDOS
  - /auth/me devolve só o módulo 'uc'
  - painel, trilha, aula e conclusão liberados
  - vê TODAS as trilhas publicadas, inclusive as de manual de outro cargo,
    e nenhuma como obrigatória; rascunho continua invisível
  - estúdio, CRM, Monitor, RPeR, parceiros e telemetria barrados (403)
  - não abre a UC de outra pessoa (modo leitura é da gestão)
  - fora do seletor de envolvidos, da visão do time e dos ausentes
  - cargo UC não pode ser posto no manual de uma trilha
  - validação do script criar_usuario_uc
"""
from datetime import date, timedelta

import pytest

from routers.permissions import (
    CARGO_UC,
    CARGOS_DE_TELA,
    CARGOS_VALIDOS,
    modulos_do_cargo,
)
from scripts.criar_usuario_uc import validar
from services import telemetria
from tests.conftest import criar_usuario
from tests.test_uc import (
    _me,
    cargos,
    estudar,
    nova_aula,
    nova_trilha,
    painel,
    trilha_publicada,
)


# ── Função pura ──────────────────────────────────────────────────

class TestModulosDaUc:
    def test_uc_ve_so_a_uc(self):
        assert modulos_do_cargo(CARGO_UC) == {"uc"}

    def test_uc_nao_e_cargo_de_operacao(self):
        assert CARGO_UC not in CARGOS_VALIDOS
        assert CARGO_UC in CARGOS_DE_TELA

    @pytest.mark.parametrize("cargo", sorted(CARGOS_VALIDOS))
    def test_nenhum_cargo_de_gente_ganha_o_modulo_uc(self, cargo):
        """Os demais entram na UC pelo 'crm' — sem relogin, sem assert quebrado."""
        assert "uc" not in modulos_do_cargo(cargo)


class TestValidarScript:
    def test_aceita_email(self):
        validar("marcelod@controllermedseg.com.br", "Marcelo", "123456")

    @pytest.mark.parametrize("login,nome,senha", [
        ("", "Marcelo", "123456"),
        ("   ", "Marcelo", "123456"),
        ("m@x.com", "", "123456"),
        ("m@x.com", "Marcelo", "12345"),
        ("x" * 151, "Marcelo", "123456"),
    ])
    def test_rejeita_entrada_invalida(self, login, nome, senha):
        with pytest.raises(ValueError):
            validar(login, nome, senha)


# ── API ──────────────────────────────────────────────────────────

@pytest.fixture
async def aluno(db_conn, client):
    return await _me(client, await criar_usuario(db_conn, client, CARGO_UC, "aluno-uc@teste.com"))


@pytest.fixture
async def gestao(client, usuario_franqueado):
    return await _me(client, usuario_franqueado)


class TestContaDaUc:
    async def test_me_devolve_so_a_uc(self, aluno, client):
        body = (await client.get("/auth/me", headers=aluno["headers"])).json()
        assert body["cargo"] == "UC"
        assert body["modulos"] == ["uc"]

    async def test_ve_todas_as_publicadas_nenhuma_obrigatoria(self, aluno, gestao, client):
        h = gestao["headers"]
        do_sdr, _ = await trilha_publicada(
            client, h, titulo="Manual do SDR",
            cargos_lista=[{"cargo": "SDR", "obrigatoria": True, "prazo_dias": 30}],
        )
        aberta, _ = await trilha_publicada(client, h, titulo="Aberta a todos")
        rascunho = await nova_trilha(client, h, titulo="Rascunho")
        await nova_aula(client, h, rascunho["id"])

        p = await painel(client, aluno)
        assert p["manual"]["trilhas"] == []
        ids = {t["id"] for t in p["outras"]}
        assert ids == {do_sdr["id"], aberta["id"]}
        assert p["proxima"] is not None
        assert p["modo_leitura"] is False
        assert p["pode_editar_conteudo"] is False

        resp = await client.get(f"/uc/trilhas/{rascunho['id']}", headers=aluno["headers"])
        assert resp.status_code == 404

    async def test_assiste_e_conclui_aula(self, aluno, gestao, client, db_conn):
        t, aulas = await trilha_publicada(
            client, gestao["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        resp = await client.get(f"/uc/trilhas/{t['id']}", headers=aluno["headers"])
        assert resp.status_code == 200, resp.text
        estado = await estudar(client, db_conn, aluno, aulas[0]["id"])
        assert estado["concluida_em"] is not None

        p = await painel(client, aluno)
        assert p["outras"][0]["aulas_concluidas"] == 1

    async def test_nao_abre_a_uc_de_outra_pessoa(self, aluno, gestao, client):
        resp = await client.get(
            "/uc/painel", params={"usuario_id": gestao["id"]}, headers=aluno["headers"],
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize("rota", [
        "/uc/estudio/trilhas",
        "/uc/estudio/time",
        "/crm/oportunidades",
        "/crm/contas",
        "/crm/tarefas",
        "/crm/dominio/usuarios",
        "/crm/relatorios/salvos",
        "/crm/parceiros",
        "/monitor/painel",
        "/rper/metas",
        "/telemetria/dia",
    ])
    async def test_resto_do_sistema_barrado(self, aluno, client, rota):
        resp = await client.get(rota, headers=aluno["headers"])
        assert resp.status_code == 403, f"{rota}: {resp.status_code} {resp.text}"

    async def test_fora_do_seletor_de_envolvidos(self, aluno, client, usuario_adm):
        resp = await client.get("/crm/dominio/usuarios", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        cargos_vistos = {u["cargo"] for u in resp.json()}
        assert "UC" not in cargos_vistos
        assert "ADM" in cargos_vistos

    async def test_fora_da_visao_do_time(self, aluno, gestao, client):
        resp = await client.get("/uc/estudio/time", headers=gestao["headers"])
        assert resp.status_code == 200, resp.text
        assert aluno["id"] not in {p["id"] for p in resp.json()}

    async def test_cargo_uc_nao_entra_no_manual(self, gestao, client):
        h = gestao["headers"]
        t = await nova_trilha(client, h)
        resp = await client.put(
            f"/uc/estudio/trilhas/{t['id']}/cargos",
            json={"cargos": [{"cargo": "UC"}]}, headers=h,
        )
        assert resp.status_code == 422
        await cargos(client, h, t["id"], [])

    async def test_nao_conta_como_ausente(self, aluno, usuario_adm, db_conn):
        # Um evento qualquer torna a medição "disponível"; o dia seguinte não
        # tem acesso de ninguém, então toda pessoa da operação é ausente.
        await db_conn.execute(
            "INSERT INTO uso_eventos (metodo, rota, status, duracao_ms) VALUES ('GET', '/x', 200, 1)"
        )
        resumo = await telemetria.adocao(db_conn, date.today() + timedelta(days=1))
        cargos_ausentes = {a["cargo"] for a in resumo["sem_acesso_hoje"]}
        assert "ADM" in cargos_ausentes
        assert "UC" not in cargos_ausentes
