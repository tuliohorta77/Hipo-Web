"""
HIPO — Testes da telemetria: captura, agregação, permissão e retenção.

Os testes de render e de fallback da IA ficam em test_relatorio_diario.py
(puros, rodam sem Postgres).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from middleware import telemetria as mw
from services import telemetria as tel
from tests.conftest import criar_usuario

# Mesmo fuso que services/telemetria.py usa para recortar o dia. Lido de lá,
# nao redigitado: duas constantes com o mesmo nome divergem no primeiro
# ajuste, e o teste passaria a medir um dia diferente do que o codigo mede.
FUSO_OPERACAO = ZoneInfo(tel.FUSO_OPERACAO)

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

def hoje_operacao() -> date:
    """
    O dia corrente no FUSO DA OPERAÇÃO — o mesmo recorte que as agregações
    usam (`AT TIME ZONE 'America/Sao_Paulo'` em services/telemetria.py).

    O `today` do módulo `date`, que estava aqui antes, devolve o dia do
    RELÓGIO DA MÁQUINA, e o runner do CI roda em UTC. Das 21h à meia-noite
    de Brasília os dois discordam: o evento era semeado no instante certo,
    mas a agregação era pedida para o dia SEGUINTE, cuja janela local ainda
    nem tinha começado — zero ações num teste que acabou de gravar cinco.
    Aconteceu num run das 00:49 UTC, e derrubou junto o teste de
    disponibilidade e o de contas criadas.

    A chamada antiga não aparece escrita neste arquivo, nem em comentário:
    o pré-voo do deploy procura por ela literalmente para impedir que volte.

    O instante semeado não precisa mudar: `now(timezone.utc)` e o mesmo
    instante em qualquer outro fuso são o MESMO ponto no tempo, e é isso que
    o timestamptz guarda. O que estava errado era só a pergunta "que dia é
    hoje".
    """
    return datetime.now(FUSO_OPERACAO).date()


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

        r = await tel.adocao(db_conn, hoje_operacao())
        assert r["acoes"] == 5
        assert r["pessoas_ativas"] == 1
        assert r["erros"] == 1
        assert r["taxa_erro_pct"] == 20.0
        assert r["por_pessoa"][0]["acoes"] == 5

    async def test_evento_de_ontem_nao_conta_hoje(self, db_conn, client):
        await criar_usuario(db_conn, client, "ADM", "on@teste.com")
        uid = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = 'on@teste.com'")
        await _semear(db_conn, uid, datetime.now(timezone.utc) - timedelta(days=2), n=3)
        assert (await tel.adocao(db_conn, hoje_operacao()))["acoes"] == 0

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
        r = await tel.adocao(db_conn, hoje_operacao())
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
        r = await tel.adocao(db_conn, hoje_operacao())
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

        r = await tel.adocao(db_conn, hoje_operacao() - timedelta(days=1))
        assert r["disponivel"] is False
        assert r["sem_acesso_hoje"] == []

    async def test_dia_com_evento_e_disponivel(self, db_conn, client):
        await criar_usuario(db_conn, client, "ADM", "ativo@teste.com")
        uid = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = 'ativo@teste.com'"
        )
        await _semear(db_conn, uid, datetime.now(timezone.utc), n=2)
        assert (await tel.adocao(db_conn, hoje_operacao()))["disponivel"] is True


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
        r = await tel.operacao(db_conn, hoje_operacao())
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


# ── Atividades e reuniões do fechamento (16/09) ─────────────────────

DIA_FIXO = date(2026, 9, 15)


def _em_sp(hora: int, minuto: int = 0, dia: date = DIA_FIXO) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=FUSO_OPERACAO)


async def _usuario(db_conn, nome: str, cargo: str, email: str):
    return await db_conn.fetchval("""
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ($1, $2, 'x', $3) RETURNING id
    """, nome, email, cargo)


async def _evento(db_conn, uid, cargo, metodo, rota, status, quando, n=1):
    for _ in range(n):
        await db_conn.execute("""
            INSERT INTO uso_eventos
                (usuario_id, cargo, metodo, rota, modulo, status, duracao_ms, criado_em)
            VALUES ($1, $2, $3, $4, 'crm', $5, 5, $6)
        """, uid, cargo, metodo, rota, status, quando)


class TestAtividades:
    async def test_so_escrita_com_sucesso_e_na_hora_de_brasilia(self, db_conn):
        uid = await _usuario(db_conn, "Kethlleen Gomes", "SDR", "k@teste.com")
        concluir = "/crm/tarefas/{tarefa_id}/concluir"
        await _evento(db_conn, uid, "SDR", "POST", concluir, 200, _em_sp(10, 5), n=3)
        await _evento(db_conn, uid, "SDR", "POST", "/crm/tarefas", 201, _em_sp(17, 40))
        await _evento(db_conn, uid, "SDR", "GET", "/crm/tarefas/kanban", 200, _em_sp(8, 46), n=50)
        await _evento(db_conn, uid, "SDR", "POST", "/crm/contatos/{contato_id}/vinculos", 409,
                      _em_sp(11))
        await _evento(db_conn, uid, "SDR", "POST", "/auth/login", 200, _em_sp(8, 46))

        r = await tel.atividades(db_conn, DIA_FIXO)
        assert r["total"] == 4
        p = r["por_pessoa"][0]
        assert p["nome"] == "Kethlleen Gomes"
        assert p["por_hora"][r["horas"].index(10)] == 3
        assert p["por_hora"][r["horas"].index(17)] == 1
        # Expediente pelo primeiro e ultimo evento de QUALQUER tipo, local.
        assert (p["entrada"], p["saida"]) == ("08:46", "17:40")
        assert {t["tipo"]: t["qtd"] for t in p["por_tipo"]} == {
            "Tarefa criada": 1, "Tarefa concluída": 3,
        }

    async def test_evento_das_22h_fica_no_dia_local(self, db_conn):
        """22h de 15/09 em Brasília é 01h de 16/09 em UTC."""
        uid = await _usuario(db_conn, "Gabriel Lira", "SDR", "g@teste.com")
        await _evento(db_conn, uid, "SDR", "POST", "/crm/tarefas", 201, _em_sp(22, 0))
        r = await tel.atividades(db_conn, DIA_FIXO)
        assert r["total"] == 1
        assert r["horas"][-1] == 22
        seguinte = await tel.atividades(db_conn, DIA_FIXO + timedelta(days=1))
        assert seguinte["total"] == 0

    async def test_quem_so_leu_aparece_com_zero(self, db_conn):
        uid = await _usuario(db_conn, "Jakeline Santana", "EV", "j@teste.com")
        await _evento(db_conn, uid, "EV", "GET", "/crm/tarefas", 200, _em_sp(9), n=10)
        r = await tel.atividades(db_conn, DIA_FIXO)
        assert r["total"] == 0
        assert r["por_pessoa"][0]["nome"] == "Jakeline Santana"
        assert r["por_pessoa"][0]["por_tipo"] == []

    async def test_dia_vazio(self, db_conn):
        r = await tel.atividades(db_conn, date(2020, 1, 1))
        assert r == {"total": 0, "horas": list(range(8, 19)),
                     "total_por_hora": [0] * 11, "por_pessoa": []}


async def _reuniao(db_conn, *, ev, sdr, conta_id, tipo_id, inicio: datetime,
                   desfecho=None, concluida=False, criado_em=None):
    tarefa_id = await db_conn.fetchval("""
        INSERT INTO tarefas (conta_id, tipo, titulo, responsavel_id, prazo,
                             concluida_em, criado_por)
        VALUES ($1, 'reuniao', 'Reunião', $2, $3, $4, $5) RETURNING id
    """, conta_id, ev, inicio, inicio + timedelta(minutes=30) if concluida else None, sdr)
    await db_conn.execute("""
        INSERT INTO reunioes (tarefa_id, duracao_min, tipo_id, agendado_por,
                              desfecho, desfecho_em, criado_por, criado_em)
        VALUES ($1, 30, $2, $3, $4, $5, $3, $6)
    """, tarefa_id, tipo_id, sdr, desfecho,
        inicio + timedelta(hours=1) if desfecho else None,
        criado_em or inicio - timedelta(days=2))


class TestReunioesDoFechamento:
    async def _base(self, db_conn):
        ev = await _usuario(db_conn, "Bruno Gonçalo", "EV", "b@teste.com")
        sdr = await _usuario(db_conn, "Kethlleen Gomes", "SDR", "k2@teste.com")
        conta = await db_conn.fetchval("""
            INSERT INTO contas (razao_social, nome_fantasia, cnpj, eh_finder, criado_por)
            VALUES ('Metalurgica Andrade Ltda', 'Metalurgica Andrade', '11222333000181',
                    TRUE, $1) RETURNING id
        """, sdr)
        tipo = await db_conn.fetchval("""
            INSERT INTO tipos_reuniao (sigla, nome, slug) VALUES ('DG', 'Diagnóstico', 'dg-t')
            RETURNING id
        """)
        return ev, sdr, conta, tipo

    async def test_desfechos_por_anfitriao(self, db_conn):
        ev, sdr, conta, tipo = await self._base(db_conn)
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(9), desfecho="realizada")
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(14), desfecho="no_show")
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(16), concluida=True)
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(17))
        # Outro dia: nao entra.
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(9, dia=DIA_FIXO + timedelta(days=1)))

        agora = datetime(2026, 9, 16, 6, 10, tzinfo=timezone.utc)
        r = await tel.reunioes(db_conn, DIA_FIXO, agora=agora)
        assert (r["total"], r["realizadas"], r["no_show"], r["pendentes"]) == (4, 2, 1, 1)
        assert r["por_anfitriao"][0]["nome"] == "Bruno Gonçalo"
        item = r["itens"][0]
        assert item["hora"] == "09:00"
        assert item["empresa"] == "Metalurgica Andrade"
        assert item["tipo"] == "DG · Diagnóstico"
        assert item["agendado_por"] == "Kethlleen Gomes"

    async def test_agendamento_conta_no_dia_em_que_foi_marcado(self, db_conn):
        ev, sdr, conta, tipo = await self._base(db_conn)
        # Marcada em 15/09 para 18/09: agendamento do dia 15, reuniao do dia 18.
        await _reuniao(db_conn, ev=ev, sdr=sdr, conta_id=conta, tipo_id=tipo,
                       inicio=_em_sp(10, dia=date(2026, 9, 18)), criado_em=_em_sp(11))
        r = await tel.reunioes(db_conn, DIA_FIXO)
        assert r["total"] == 0
        assert r["agendamentos_total"] == 1
        assert r["agendamentos_por_pessoa"][0]["nome"] == "Kethlleen Gomes"


class TestMetricasDoDiaNovosBlocos:
    async def test_payload_traz_atividades_e_reunioes(self, db_conn):
        uid = await _usuario(db_conn, "Aline Martins", "EC", "a@teste.com")
        await _evento(db_conn, uid, "EC", "POST", "/crm/tarefas", 201, _em_sp(11))
        m = await tel.metricas_do_dia(db_conn, DIA_FIXO)
        assert m["atividades"]["total"] == 1
        assert m["reunioes"]["total"] == 0

    async def test_comparativo_le_atividades_do_fechamento_anterior(self, db_conn):
        import json
        await db_conn.execute("""
            INSERT INTO relatorios_diarios (dia, metricas) VALUES ($1, $2::jsonb)
        """, DIA_FIXO - timedelta(days=1), json.dumps({
            "adocao": {"acoes": 900, "pessoas_ativas": 4},
            "operacao": {}, "atividades": {"total": 150},
            "reunioes": {"realizadas": 3},
        }))
        c = await tel.comparativo(db_conn, DIA_FIXO)
        assert c["atividades"] == 150
        assert c["reunioes_realizadas"] == 3

    async def test_comparativo_de_fechamento_antigo_nao_inventa_zero(self, db_conn):
        import json
        await db_conn.execute("""
            INSERT INTO relatorios_diarios (dia, metricas) VALUES ($1, $2::jsonb)
        """, DIA_FIXO - timedelta(days=1), json.dumps({
            "adocao": {"acoes": 900, "pessoas_ativas": 4}, "operacao": {},
        }))
        assert (await tel.comparativo(db_conn, DIA_FIXO))["atividades"] is None
