"""
HIPO — Identidade da instância (entrega 046): o mesmo código atende a base da
Controller MedSeg e a da MOS.

Cobertura:
  - padrão (sem EMPRESA_* no .env) reproduz a base principal byte a byte:
    convite da agenda, nome do RPeR, assunto do e-mail, modelo da proposta
  - com EMPRESA_NOME / EMPRESA_SIGLA / PROPOSTA_MODELO_ARQUIVO, cada saída
    troca para a outra empresa
  - slug do nome de arquivo (acento, espaço, pontuação)
  - /health e /auth/me expõem a instância
  - script criar_usuario: validação e idempotência
"""
from pathlib import Path

import pytest

from config import settings
from scripts.criar_usuario import criar, validar
from services import agenda, instancia, relatorio_render, rper_render
from tests.conftest import criar_usuario


@pytest.fixture
def como_mos(monkeypatch):
    monkeypatch.setattr(settings, "EMPRESA_NOME", "MOS Medicina Ocupacional")
    monkeypatch.setattr(settings, "EMPRESA_SIGLA", "MOS")


METRICAS = {"dia": "2026-10-05", "adocao": {"pessoas_ativas": 3},
            "atividades": {"total": 12}}


# ── Padrão = base principal, como era antes ─────────────────────────────

class TestPadraoEABasePrincipal:
    def test_nome_e_sigla(self):
        assert instancia.empresa_nome() == "Controller MedSeg"
        assert instancia.empresa_sigla() == ""

    def test_convite_da_agenda(self):
        assert agenda.titulo_evento(
            razao_social="Alfa LTDA", cnpj=None, tipo_nome="Apresentação",
        ) == "Alfa LTDA | Apresentação Controller MedSeg"

    def test_assunto_do_fechamento(self):
        assert relatorio_render.assunto(METRICAS).startswith("HIPO 05/10 — ")

    def test_modelo_da_proposta(self):
        assert instancia.modelo_proposta() == instancia.MODELO_PROPOSTA_PADRAO
        assert instancia.MODELO_PROPOSTA_PADRAO.name == "proposta_modelo.pptx"

    def test_nome_vazio_no_env_cai_no_padrao(self, monkeypatch):
        """EMPRESA_NOME= (vazio) no .env não pode virar convite sem empresa."""
        monkeypatch.setattr(settings, "EMPRESA_NOME", "  ")
        assert instancia.empresa_nome() == "Controller MedSeg"


# ── Instância MOS ───────────────────────────────────────────────────────

class TestInstanciaMos:
    def test_convite_da_agenda_leva_o_nome_da_mos(self, como_mos):
        assert agenda.titulo_evento(
            razao_social="Alfa LTDA", cnpj="11222333000181", tipo_nome="Apresentação",
        ) == "Alfa LTDA 11.222.333/0001-81 | Apresentação MOS Medicina Ocupacional"

    def test_rper_com_o_nome_da_mos(self, como_mos):
        r = {"ano_novo": 2026, "mes_novo": 3}
        assert rper_render.nome_do_arquivo(r, "pptx") == (
            "RPeR_MARCO_2026_MOS_MEDICINA_OCUPACIONAL.pptx"
        )

    def test_assunto_identifica_a_base(self, como_mos):
        assert relatorio_render.assunto(METRICAS) == (
            "HIPO MOS 05/10 — 3 pessoas, 12 atividades"
        )

    def test_modelo_da_proposta_do_env(self, monkeypatch, tmp_path):
        modelo = tmp_path / "proposta_mos.pptx"
        monkeypatch.setattr(settings, "PROPOSTA_MODELO_ARQUIVO", str(modelo))
        assert instancia.modelo_proposta() == Path(modelo)


class TestSlugDoArquivo:
    @pytest.mark.parametrize("nome,esperado", [
        ("Controller MedSeg", "CONTROLLER_MEDSEG"),
        ("MOS", "MOS"),
        ("Saúde & Segurança — Ocupacional", "SAUDE_SEGURANCA_OCUPACIONAL"),
        ("  --  ", "HIPO"),
        ("", "HIPO"),
    ])
    def test_slug(self, nome, esperado):
        assert instancia.slug_arquivo(nome) == esperado


# ── API ─────────────────────────────────────────────────────────────────

class TestApi:
    async def test_health_base_principal(self, client):
        body = (await client.get("/health")).json()
        assert body["empresa"] == "Controller MedSeg"
        assert body["instancia"] is None

    async def test_health_mos(self, client, como_mos):
        body = (await client.get("/health")).json()
        assert body["empresa"] == "MOS Medicina Ocupacional"
        assert body["instancia"] == "MOS"

    async def test_me_traz_a_instancia(self, db_conn, client, como_mos):
        u = await criar_usuario(db_conn, client, "EV", "ev-mos@teste.com")
        me = (await client.get("/auth/me", headers=u["headers"])).json()
        assert me["instancia"] == "MOS"

    async def test_me_base_principal_sem_instancia(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "EV", "ev-gru@teste.com")
        me = (await client.get("/auth/me", headers=u["headers"])).json()
        assert me["instancia"] is None


# ── Script criar_usuario ────────────────────────────────────────────────

class TestValidarCriarUsuario:
    def test_aceita(self):
        validar("tulio@mos.com.br", "Tulio", "Franqueado", "123456")

    @pytest.mark.parametrize("login,nome,cargo,senha", [
        ("", "X", "EV", "123456"),
        ("sem-arroba", "X", "EV", "123456"),
        ("a@b.com", "  ", "EV", "123456"),
        ("a@b.com", "X", "Gerente", "123456"),   # cargo extinto
        ("a@b.com", "X", "UC", "123456"),        # tem script próprio
        ("a@b.com", "X", "EV", "123"),
        ("a" * 150 + "@b.com", "X", "EV", "123456"),
    ])
    def test_recusa(self, login, nome, cargo, senha):
        with pytest.raises(ValueError):
            validar(login, nome, cargo, senha)


class TestCriarUsuario:
    async def test_cria_com_troca_de_senha_obrigatoria(self, db_conn):
        msg = await criar(db_conn, "nova@mos.com.br", "Nova", "SDR", "123456", False)
        assert msg.startswith("CRIADO")
        u = await db_conn.fetchrow(
            "SELECT cargo, ativo, precisa_trocar_senha FROM usuarios WHERE email = $1",
            "nova@mos.com.br",
        )
        assert (u["cargo"], u["ativo"], u["precisa_trocar_senha"]) == ("SDR", True, True)

    async def test_rodar_de_novo_preserva_a_senha(self, db_conn):
        await criar(db_conn, "x@mos.com.br", "X", "SDR", "123456", False)
        antes = await db_conn.fetchval("SELECT senha_hash FROM usuarios WHERE email = 'x@mos.com.br'")
        msg = await criar(db_conn, "X@MOS.com.br", "X Promovido", "EV", "outra-senha", False)
        assert "preservada" in msg
        depois = await db_conn.fetchrow(
            "SELECT senha_hash, cargo, nome FROM usuarios WHERE email = 'x@mos.com.br'"
        )
        assert depois["senha_hash"] == antes
        assert (depois["cargo"], depois["nome"]) == ("EV", "X Promovido")
        assert await db_conn.fetchval("SELECT count(*) FROM usuarios") == 1

    async def test_redefinir_senha(self, db_conn):
        await criar(db_conn, "y@mos.com.br", "Y", "EP", "123456", False)
        antes = await db_conn.fetchval("SELECT senha_hash FROM usuarios WHERE email = 'y@mos.com.br'")
        msg = await criar(db_conn, "y@mos.com.br", "Y", "EP", "nova-senha", True)
        assert "redefinida" in msg
        assert await db_conn.fetchval(
            "SELECT senha_hash FROM usuarios WHERE email = 'y@mos.com.br'"
        ) != antes
