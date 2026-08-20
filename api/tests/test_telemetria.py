"""
HIPO — Testes da telemetria: captura, agregação, permissão e retenção.

Os testes de render e de fallback da IA ficam em test_relatorio_diario.py
(puros, rodam sem Postgres).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from middleware import telemetria as mw
from services import telemetria as tel
from tests.conftest import criar_usuario

pytestmark = pytest.mark.anyio


# ── Helpers puros ────────────────────────────────────────────────────

class TestModuloDaRota:
    def test_primeiro_segmento(self):
        assert mw.modulo_da_rota("/crm/parceiros/resumo") == "crm"
        assert mw.modulo_da_rota("/auth/login") == "auth"
        assert mw.modulo_da_rota("/telemetria/dia") == "telemetria"

    def test_raiz_e_vazio_viram_none(self):
        assert mw.modulo_da_rota("/") is None
        assert mw.modulo_da_rota("") is None

    def test_trunca_em_40(self):
        assert len(mw.modulo_da_rota("/" + "x" * 80)) == 40


class TestEmailDoToken:
    def test_sem_header(self):
        assert mw.email_do_token(None) is None
        assert mw.email_do_token("") is None

    def test_esquema_errado(self):
        assert mw.email_do_token("Basic abc") is None

    def test_token_lixo_nao_levanta(self):
        """Token inválido vira request anônima, nunca 500."""
        assert mw.email_do_token("Bearer nao-e-um-jwt") is None

    async def test_token_valido(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "ADM", "mw-adm@teste.com")
        assert mw.email_do_token(f"Bearer {u['token']}") == "mw-adm@teste.com"


class TestBuffer:
    async def test_descarta_acima_do_limite_sem_estourar(self):
        b = mw.BufferTelemetria(limite=3, lote=1000)
        for _ in range(10):
            await b.registrar(("a@b.c", "GET", "/x", "x", 200, 1, datetime.now(timezone.utc)))
        assert len(b) == 3
        assert b.descartados == 7

    async def test_descarregar_vazio_devolve_zero(self):
        assert await mw.BufferTelemetria().descarregar() == 0


# ── Captura ponta a ponta ────────────────────────────────────────────

class TestCaptura:
    async def test_request_autenticada_vira_evento(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Franqueado", "cap@teste.com")
        await client.get("/crm/contas", headers=u["headers"])
        await mw.buffer.descarregar()

        linha = await db_conn.fetchrow("""
            SELECT e.rota, e.metodo, e.status, e.modulo, e.cargo, u.email
            FROM uso_eventos e JOIN usuarios u ON u.id = e.usuario_id
            WHERE u.email = 'cap@teste.com' AND e.rota = '/crm/contas'
        """)
        assert linha is not None
        assert linha["metodo"] == "GET"
        assert linha["status"] == 200
        assert linha["modulo"] == "crm"
        assert linha["cargo"] == "Franqueado"

    async def test_grava_template_e_nao_o_path_com_id(self, db_conn, client):
        """
        O id do cliente não pode vazar para a tabela de log. É a regra que
        justifica guardar rota em vez de path.
        """
        u = await criar_usuario(db_conn, client, "ADM", "tpl@teste.com")
        conta_id = "11111111-1111-1111-1111-111111111111"
        await client.get(f"/crm/contas/{conta_id}", headers=u["headers"])
        await mw.buffer.descarregar()

        rotas = [r["rota"] for r in await db_conn.fetch("SELECT rota FROM uso_eventos")]
        assert not any(conta_id in r for r in rotas), f"id vazou para o log: {rotas}"
        assert any("{" in r for r in rotas), f"esperava template com chaves: {rotas}"

    async def test_health_nao_e_capturado(self, db_conn, client):
        await client.get("/health")
        await mw.buffer.descarregar()
        assert await db_conn.fetchval(
            "SELECT count(*) FROM uso_eventos WHERE rota = '/health'"
        ) == 0

    async def test_request_sem_token_entra_como_anonima(self, db_conn, client):
        await client.get("/crm/contas")
        await mw.buffer.descarregar()
        assert await db_conn.fetchval(
            "SELECT count(*) FROM uso_eventos WHERE usuario_id IS NULL"
        ) >= 1

    async def test_erro_e_registrado_com_o_status(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "SDR", "err@teste.com")
        # SDR não tem o módulo 'parceiros' → 403.
        await client.get("/crm/parceiros/resumo", headers=u["headers"])
        await mw.buffer.descarregar()
        assert await db_conn.fetchval(
            "SELECT count(*) FROM uso_eventos WHERE status = 403"
        ) >= 1


# ── Agregações ───────────────────────────────────────────────────────

async def _semear(db_conn, usuario_id, quando: datetime, n: int = 1,
                  rota: str = "/crm/contas", status: int = 200, ms: int = 10):
    for _ in range(n):
        await db_conn.execute("""
            INSERT INTO uso_eventos
                (usuario_id, cargo, metodo, rota, modulo, status, duracao_ms, criado_em)
            VALUES ($1, 'ADM', 'GET', $2, 'crm', $3, $4, $5)
        """, usuario_id, rota, status, ms, quando)


class TestAdocao:
    async def test_dia_vazio_devolve_zeros(self, db_conn):
        r = await tel.adocao(db_conn, date(2020, 1, 1))
        assert r["acoes"] == 0
        assert r["pessoas_ativas"] == 0
        assert r["taxa_erro_pct"] is None

    async def test_conta_acoes_pessoas_e_erros(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "ADM", "ag@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'ag@teste.com'")
        hoje = datetime.now(timezone.utc)

        await _semear(db_conn, uid, hoje, n=4)
        await _semear(db_conn, uid, hoje, n=1, status=422)

        r = await tel.adocao(db_conn, date.today())
        assert r["acoes"] == 5
        assert r["pessoas_ativas"] == 1
        assert r["erros"] == 1
        assert r["taxa_erro_pct"] == 20.0
        assert r["por_pessoa"][0]["acoes"] == 5

    async def test_evento_de_ontem_nao_conta_hoje(self, db_conn, client):
        await criar_usuario(db_conn, client, "ADM", "on@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'on@teste.com'")
        await _semear(db_conn, uid, datetime.now(timezone.utc) - timedelta(days=2), n=3)
        assert (await tel.adocao(db_conn, date.today()))["acoes"] == 0

    async def test_quem_nao_usou_aparece_na_lista(self, db_conn, client):
        # Precisa de PELO MENOS um evento no dia. Sem nenhum, a telemetria é
        # considerada indisponível e a lista de ausentes sai vazia de propósito
        # — ver TestTelemetriaIndisponivel logo abaixo.
        await criar_usuario(db_conn, client, "ADM", "usou@teste.com")
        uid = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = 'usou@teste.com'"
        )
        await _semear(db_conn, uid, datetime.now(timezone.utc), n=1)

        await criar_usuario(db_conn, client, "EV", "sumiu@teste.com")
        r = await tel.adocao(db_conn, date.today())
        assert r["disponivel"] is True
        assert "sumiu@teste.com" not in [p["nome"] for p in r["por_pessoa"]]
        assert any(a["cargo"] == "EV" for a in r["sem_acesso_hoje"])


class TestTelemetriaIndisponivel:
    """
    Telemetria ausente não é telemetria zerada.

    Mesma regra de taxa_conversao em services/parceiro.py: 0% e "ainda não dá
    para saber" são coisas diferentes. Sem esta distinção, todo dia anterior à
    entrada do middleware fecharia acusando a equipe inteira de não ter
    acessado o sistema — inclusive dias em que dezenas de tarefas foram
    criadas, o que o próprio relatório mostraria no bloco de operação, duas
    seções abaixo.
    """

    async def test_sem_nenhum_evento_a_telemetria_e_indisponivel(self, db_conn, client):
        await criar_usuario(db_conn, client, "EV", "ninguem@teste.com")
        r = await tel.adocao(db_conn, date.today())
        assert r["disponivel"] is False
        assert r["sem_acesso_hoje"] == []

    async def test_dia_anterior_ao_primeiro_evento_e_indisponivel(self, db_conn, client):
        # O caso real: middleware entrou hoje, o fechamento de ontem roda
        # amanhã e não pode afirmar ausência de quem não estava sendo medido.
        await criar_usuario(db_conn, client, "ADM", "primeiro@teste.com")
        uid = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = 'primeiro@teste.com'"
        )
        await _semear(db_conn, uid, datetime.now(timezone.utc), n=1)

        r = await tel.adocao(db_conn, date.today() - timedelta(days=1))
        assert r["disponivel"] is False
        assert r["sem_acesso_hoje"] == []

    async def test_dia_com_evento_e_disponivel(self, db_conn, client):
        await criar_usuario(db_conn, client, "ADM", "ativo@teste.com")
        uid = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = 'ativo@teste.com'"
        )
        await _semear(db_conn, uid, datetime.now(timezone.utc), n=2)
        assert (await tel.adocao(db_conn, date.today()))["disponivel"] is True


class TestOperacao:
    async def test_dia_vazio(self, db_conn):
        r = await tel.operacao(db_conn, date(2020, 1, 1))
        assert r["oportunidades_criadas"] == 0
        assert r["carteira_parceiros"] == 0

    async def test_conta_parceiro_da_carteira(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Franqueado", "op@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'op@teste.com'")
        await db_conn.execute("""
            INSERT INTO contas (razao_social, cnpj, eh_finder, criado_por)
            VALUES ('Parceira Teste', '11222333000181', TRUE, $1)
        """, uid)
        r = await tel.operacao(db_conn, date.today())
        assert r["carteira_parceiros"] == 1
        assert r["parceiros_sem_ec"] == 1
        assert r["contas_criadas"] == 1


class TestRetencao:
    async def test_apaga_so_o_que_passou_do_prazo(self, db_conn, client):
        await criar_usuario(db_conn, client, "ADM", "ret@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'ret@teste.com'")
        agora = datetime.now(timezone.utc)
        await _semear(db_conn, uid, agora, n=2)
        await _semear(db_conn, uid, agora - timedelta(days=100), n=3)

        apagados = await tel.aplicar_retencao(db_conn, 90)
        assert apagados == 3
        assert await db_conn.fetchval("SELECT count(*) FROM uso_eventos") == 2

    async def test_zero_dias_nao_apaga_nada(self, db_conn, client):
        """
        Guarda contra variável de ambiente mal preenchida: retenção 0 não pode
        significar 'apague tudo, inclusive o dia que estou fechando'.
        """
        await criar_usuario(db_conn, client, "ADM", "ret0@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'ret0@teste.com'")
        await _semear(db_conn, uid, datetime.now(timezone.utc), n=2)
        assert await tel.aplicar_retencao(db_conn, 0) == 0
        assert await db_conn.fetchval("SELECT count(*) FROM uso_eventos") == 2


# ── Permissão e endpoints ────────────────────────────────────────────

class TestPermissaoTelemetria:
    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM"])
    async def test_gestao_acessa(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"tg-{cargo}@teste.com")
        resp = await client.get("/telemetria/dia", headers=u["headers"])
        assert resp.status_code == 200

    @pytest.mark.parametrize("cargo", ["EC", "SDR", "EV", "EP"])
    async def test_operacional_bloqueado(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo, f"to-{cargo}@teste.com")
        resp = await client.get("/telemetria/dia", headers=u["headers"])
        assert resp.status_code == 403

    async def test_sem_token_401(self, db_conn, client):
        assert (await client.get("/telemetria/dia")).status_code == 401


class TestEndpoints:
    async def test_dia_ao_vivo(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "ADM", "ep1@teste.com")
        body = (await client.get("/telemetria/dia", headers=u["headers"])).json()
        assert body["origem"] == "ao_vivo"
        assert "adocao" in body["metricas"] and "operacao" in body["metricas"]

    async def test_dia_com_fechamento_devolve_o_congelado(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "ADM", "ep2@teste.com")
        await db_conn.execute("""
            INSERT INTO relatorios_diarios (dia, metricas, narrativa)
            VALUES ($1, '{"dia":"2026-01-02","adocao":{"acoes":99},"operacao":{}}'::jsonb,
                    'texto da ia')
        """, date(2026, 1, 2))
        body = (await client.get("/telemetria/dia?data=2026-01-02",
                                 headers=u["headers"])).json()
        assert body["origem"] == "fechamento"
        assert body["metricas"]["adocao"]["acoes"] == 99
        assert body["narrativa"] == "texto da ia"

    async def test_relatorio_inexistente_404(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "ADM", "ep3@teste.com")
        resp = await client.get("/telemetria/relatorios/2019-05-05", headers=u["headers"])
        assert resp.status_code == 404

    async def test_lista_de_relatorios(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Franqueado", "ep4@teste.com")
        await db_conn.execute("""
            INSERT INTO relatorios_diarios (dia, metricas)
            VALUES ('2026-01-03', '{"adocao":{"acoes":5},"operacao":{}}'::jsonb)
        """)
        body = (await client.get("/telemetria/relatorios", headers=u["headers"])).json()
        assert body["total"] == 1
        assert body["itens"][0]["acoes"] == 5
