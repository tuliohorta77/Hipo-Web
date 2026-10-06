"""
HIPO — Scorecard da reunião: endpoints, gravação, fila do timer e Monitor.

As regras e a leitura da resposta da IA estão em test_avaliacao_roteiro.py.
Aqui o foco é a costura com o banco:

  * o estado que a tela recebe (não elegível, na fila, pronta, erro)
  * a nota valendo assim que sai, o ajuste da gestão por cima e o selo
  * a falha da IA virando coluna — e não apagando a nota que já existia
  * a fila do timer e a do backfill
  * o quadro SCORECARD e a coluna Nota no detalhe do APRE

A IA NÃO é chamada: `avaliacao_roteiro.avaliar` é trocada por uma função de
teste, como o resumo em test_crm_transcricao.
"""
import json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import pytest

from services import avaliacao_roteiro as aval
from services import coleta_avaliacao as coleta
from services import roteiro_scorecard as sc
from services.tarefa import FUSO_OPERACAO
from tests.conftest import _DB_URL, contato_do_alvo, contato_para_proxima, criar_usuario
from tests.test_crm_agenda import nova_reuniao

UTC = timezone.utc

TEXTO = (
    "[10:00] Test ADM: Bom dia! Vi que vocês abriram a unidade de Guarulhos.\n"
    "[10:02] Cliente Alfa: Temos 120 vidas e o fornecedor atrasa o ASO.\n"
    "[10:03] Test ADM: E o que te incomoda hoje no fornecedor atual?\n"
)
ENTRADAS = [
    {"inicio": None, "fim": None, "participante": "Test ADM",
     "texto": "Bom dia! Vi que vocês abriram a unidade de Guarulhos."},
    {"inicio": None, "fim": None, "participante": "Cliente Alfa",
     "texto": "Temos 120 vidas e o fornecedor atrasa o ASO."},
    {"inicio": None, "fim": None, "participante": "Test ADM",
     "texto": "E o que te incomoda hoje no fornecedor atual?"},
]

# 2+2+1+1+0+2+1+1+descartado+2 = 12
NOTAS = [2, 2, 1, 1, 0, 2, 1, 1, None, 2]


def resultado(notas=NOTAS, erro=None):
    if erro:
        return aval.Avaliacao(erro=erro)
    itens = tuple(
        aval.ItemAvaliado(
            item=n, nota=nota,
            evidencia="o que te incomoda hoje" if nota else None,
            justificativa=f"Justificativa {n}", sugestao=f"Sugestão {n}",
            descartado=None if nota is not None else "Trecho citado não foi encontrado na transcrição.",
        )
        for n, nota in enumerate(notas, start=1)
    )
    return aval.Avaliacao(
        itens=itens,
        pontos_fortes=(aval.Ponto("Usou a pesquisa", "abriram a unidade de Guarulhos"),),
        pontos_melhorar=(aval.Ponto("Faltou implicação", None, "Pergunte o custo do atraso."),),
        foco_proxima="Perguntar o custo do problema.",
        resumo="Boa abertura, diagnóstico raso.",
        modelo="modelo-teste",
        descartados=tuple(n for n, nota in enumerate(notas, start=1) if nota is None),
    )


def ligar_ia(monkeypatch, respostas=None):
    """Liga a IA de mentira. `respostas` é a fila do que cada chamada devolve."""
    fila = list(respostas or [resultado()])
    chamadas = []

    async def avaliar(texto, ctx):
        chamadas.append(ctx)
        return fila.pop(0) if len(fila) > 1 else fila[0]

    monkeypatch.setattr(aval, "configurado", lambda: True)
    monkeypatch.setattr(aval, "avaliar", avaliar)
    return chamadas


@pytest.fixture
async def base(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = (await client.post(
        "/crm/contas",
        json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": "11.222.333/0001-81"},
        headers=h,
    )).json()
    opp = (await client.post(
        "/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h,
    )).json()
    me = (await client.get("/auth/me", headers=h)).json()
    return {"h": h, "opp": opp, "uid": me["id"], "conn": db_conn}


async def reuniao(base, client, inicio=None, transcricao=True, desfecho=None):
    """Uma reunião que já aconteceu, com a transcrição pronta (por SQL)."""
    r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])
    conn = base["conn"]
    inicio = inicio or (datetime.now(UTC) - timedelta(hours=2))
    await conn.execute("UPDATE tarefas SET prazo = $2 WHERE id = $1",
                       UUID(r["tarefa_id"]), inicio)
    if desfecho:
        await conn.execute(
            "UPDATE reunioes SET desfecho = $2, desfecho_em = NOW() WHERE id = $1",
            UUID(r["id"]), desfecho,
        )
    if transcricao:
        await conn.execute(
            """
            INSERT INTO reuniao_transcricoes
                   (reuniao_id, status, texto, entradas, coletada_em)
            VALUES ($1, 'pronta', $2, $3::jsonb, NOW())
            """,
            UUID(r["id"]), TEXTO, json.dumps(ENTRADAS, ensure_ascii=False),
        )
    return r


def url(r, sufixo=""):
    return f"/crm/agenda/tarefas/{r['tarefa_id']}/avaliacao{sufixo}"


async def gerar(client, h, r, esperado=200):
    resp = await client.post(url(r, "/gerar"), headers=h)
    assert resp.status_code == esperado, resp.text
    return resp.json()


# ── Estado ───────────────────────────────────────────────────────────


class TestEstado:
    async def test_sem_transcricao_nao_e_elegivel(self, base, client):
        r = await reuniao(base, client, transcricao=False)
        corpo = (await client.get(url(r), headers=base["h"])).json()
        assert corpo["status"] == "nao_elegivel"
        assert "transcrição" in corpo["motivo"]
        assert corpo["pode_gerar"] is False
        assert corpo["itens"] == []

    async def test_com_transcricao_entra_na_fila(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        corpo = (await client.get(url(r), headers=base["h"])).json()
        assert corpo["status"] == "na_fila"
        assert corpo["pode_gerar"] is True
        assert corpo["nota_maxima"] == 20
        assert corpo["meta"] == 15.0

    async def test_no_show_nao_e_avaliado(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client, desfecho="no_show")
        corpo = (await client.get(url(r), headers=base["h"])).json()
        assert corpo["status"] == "nao_elegivel"
        assert "No-show" in corpo["motivo"]
        resp = await client.post(url(r, "/gerar"), headers=base["h"])
        assert resp.status_code == 409

    async def test_tarefa_que_nao_e_reuniao_e_404(self, base, client):
        tarefa = (await client.post("/crm/tarefas", json={
            "contato_id": await contato_do_alvo(client, base["h"], oportunidade_id=base["opp"]["id"]),
            "oportunidade_id": base["opp"]["id"], "tipo": "ligacao",
            "titulo": "Ligar", "responsavel_id": base["uid"],
            "prazo": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }, headers=base["h"])).json()
        resp = await client.get(
            f"/crm/agenda/tarefas/{tarefa['id']}/avaliacao", headers=base["h"],
        )
        assert resp.status_code == 404


# ── Gerar ────────────────────────────────────────────────────────────


class TestGerar:
    async def test_grava_nota_itens_e_coach(self, base, client, monkeypatch):
        chamadas = ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        corpo = await gerar(client, base["h"], r)

        assert corpo["status"] == "pronta"
        assert corpo["nota_total"] == 12
        assert corpo["faixa"] == "media"
        assert len(corpo["itens"]) == 10
        assert corpo["itens"][0]["nome"] == sc.ITENS[0].nome
        assert len(corpo["itens"][0]["criterios"]) == 3
        assert corpo["itens"][8]["nota"] is None
        assert corpo["itens"][8]["descartado"]
        assert corpo["pontos_fortes"][0]["texto"] == "Usou a pesquisa"
        assert corpo["pontos_melhorar"][0]["como_fazer"].startswith("Pergunte")
        assert corpo["foco_proxima"] == "Perguntar o custo do problema."
        assert corpo["modelo"] == "modelo-teste"
        assert corpo["vendedor_nome"] == "Test ADM"
        assert corpo["validada"] is False
        # Fala contada das falas: 10 + 9 palavras do vendedor em 28.
        assert corpo["fala_vendedor_pct"] == pytest.approx(67.9, abs=0.1)
        # O contexto que foi para a IA.
        ctx = chamadas[0]
        assert ctx["empresa"] == "Metalurgica Alfa LTDA"
        assert ctx["vendedor_responsavel"] == "Test ADM"
        assert ctx["participantes_na_transcricao"] == ["Test ADM", "Cliente Alfa"]

    async def test_erro_da_ia_vira_coluna(self, base, client, monkeypatch):
        ligar_ia(monkeypatch, [resultado(erro="A IA respondeu HTTP 529.")])
        r = await reuniao(base, client)
        corpo = await gerar(client, base["h"], r)
        assert corpo["status"] == "erro"
        assert corpo["erro"] == "A IA respondeu HTTP 529."
        assert corpo["tentativas"] == 1
        assert corpo["pode_gerar"] is True

    async def test_reavaliacao_que_falha_mantem_a_nota(self, base, client, monkeypatch):
        ligar_ia(monkeypatch, [resultado(), resultado(erro="Caiu.")])
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)
        corpo = await gerar(client, base["h"], r)
        assert corpo["status"] == "pronta"
        assert corpo["nota_total"] == 12
        assert corpo["erro"] == "Caiu."
        assert corpo["tentativas"] == 2

    async def test_reavaliacao_boa_substitui_e_limpa_o_erro(self, base, client, monkeypatch):
        ligar_ia(monkeypatch, [resultado(erro="Caiu."), resultado([2] * 10)])
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)
        corpo = await gerar(client, base["h"], r)
        assert corpo["status"] == "pronta"
        assert corpo["nota_total"] == 20
        assert corpo["faixa"] == "boa"
        assert corpo["erro"] is None

    async def test_outra_avaliacao_rodando_e_409(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        outra = await asyncpg.connect(_DB_URL)
        try:
            assert await outra.fetchval(
                "SELECT pg_try_advisory_lock(hashtext('avaliacao:' || $1::text))", r["id"],
            )
            resp = await client.post(url(r, "/gerar"), headers=base["h"])
            assert resp.status_code == 409
            assert "sendo avaliada" in resp.json()["detail"]
        finally:
            await outra.close()
        # Soltou a trava: agora vai.
        assert (await gerar(client, base["h"], r))["status"] == "pronta"

    async def test_ia_desligada_e_409(self, base, client, monkeypatch):
        monkeypatch.setattr(aval, "configurado", lambda: False)
        r = await reuniao(base, client)
        corpo = (await client.get(url(r), headers=base["h"])).json()
        assert corpo["status"] == "na_fila"
        assert corpo["pode_gerar"] is False
        assert "não está configurada" in corpo["motivo"]
        resp = await client.post(url(r, "/gerar"), headers=base["h"])
        assert resp.status_code == 409


# ── Gestão ───────────────────────────────────────────────────────────


class TestGestao:
    async def test_ajuste_vale_por_cima_da_ia_e_desfaz(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)

        resp = await client.patch(url(r, "/itens/9"), json={"nota": 2}, headers=base["h"])
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["nota_total"] == 14
        assert corpo["ajustada"] is True
        item = corpo["itens"][8]
        assert (item["nota"], item["nota_ia"], item["nota_gestor"]) == (2, None, 2)
        assert item["ajustada_por_nome"] == "Test ADM"

        corpo = (await client.patch(
            url(r, "/itens/9"), json={"nota": None}, headers=base["h"],
        )).json()
        assert corpo["nota_total"] == 12
        assert corpo["itens"][8]["nota_gestor"] is None
        assert corpo["itens"][8]["ajustada_em"] is None

    async def test_nota_fora_de_0_a_2_e_422(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)
        resp = await client.patch(url(r, "/itens/1"), json={"nota": 3}, headers=base["h"])
        assert resp.status_code == 422
        resp = await client.patch(url(r, "/itens/11"), json={"nota": 1}, headers=base["h"])
        assert resp.status_code == 409

    async def test_ajuste_sem_avaliacao_e_409(self, base, client):
        r = await reuniao(base, client)
        resp = await client.patch(url(r, "/itens/1"), json={"nota": 1}, headers=base["h"])
        assert resp.status_code == 409

    async def test_operacional_ve_mas_nao_ajusta(self, base, client, db_conn, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)
        ev = await criar_usuario(db_conn, client, "EV", "ev-scorecard@teste.com")

        corpo = (await client.get(url(r), headers=ev["headers"])).json()
        assert corpo["nota_total"] == 12
        assert corpo["pode_ajustar"] is False
        assert (await client.get(url(r), headers=base["h"])).json()["pode_ajustar"] is True

        for metodo, sufixo, corpo_req in (
            ("PATCH", "/itens/1", {"nota": 2}),
            ("POST", "/validar", None),
            ("DELETE", "/validar", None),
        ):
            resp = await client.request(metodo, url(r, sufixo), json=corpo_req,
                                        headers=ev["headers"])
            assert resp.status_code == 403, (metodo, sufixo)

    async def test_validada_nao_se_reavalia_ate_tirar_o_selo(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)

        corpo = (await client.post(url(r, "/validar"), headers=base["h"])).json()
        assert corpo["validada"] is True
        assert corpo["validada_por_nome"] == "Test ADM"
        assert corpo["pode_gerar"] is False
        await gerar(client, base["h"], r, esperado=409)

        corpo = (await client.delete(url(r, "/validar"), headers=base["h"])).json()
        assert corpo["validada"] is False
        assert (await gerar(client, base["h"], r))["status"] == "pronta"

    async def test_reavaliar_zera_ajuste_e_selo(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        await gerar(client, base["h"], r)
        await client.patch(url(r, "/itens/9"), json={"nota": 2}, headers=base["h"])
        corpo = await gerar(client, base["h"], r)
        assert corpo["nota_total"] == 12
        assert corpo["ajustada"] is False


# ── Filas do timer e do backfill ─────────────────────────────────────


class TestFilas:
    async def test_timer_pega_a_recente_sem_avaliacao(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        conn = base["conn"]
        assert await coleta.pendentes(conn) == [UUID(r["id"])]

        await coleta.avaliar(conn, UUID(r["id"]))
        assert await coleta.pendentes(conn) == []

    async def test_timer_retenta_erro_ate_o_limite(self, base, client, monkeypatch):
        ligar_ia(monkeypatch, [resultado(erro="Caiu.")])
        r = await reuniao(base, client)
        conn, rid = base["conn"], UUID(r["id"])
        for _ in range(coleta.MAX_TENTATIVAS_TIMER):
            assert await coleta.pendentes(conn) == [rid]
            await coleta.avaliar(conn, rid)
        assert await coleta.pendentes(conn) == []

    async def test_timer_retoma_aguardando_travada(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        conn, rid = base["conn"], UUID(r["id"])
        await conn.execute(
            """
            INSERT INTO reuniao_avaliacoes (reuniao_id, versao_roteiro, status, atualizado_em)
            VALUES ($1, $2, 'aguardando', NOW() - INTERVAL '30 minutes')
            """,
            rid, sc.VERSAO,
        )
        assert await coleta.pendentes(conn) == [rid]
        await conn.execute(
            "UPDATE reuniao_avaliacoes SET atualizado_em = NOW() WHERE reuniao_id = $1", rid,
        )
        assert await coleta.pendentes(conn) == []

    async def test_antiga_fica_para_o_backfill(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        velha = await reuniao(base, client, inicio=datetime.now(UTC) - timedelta(days=10))
        sem_texto = await reuniao(base, client, transcricao=False)
        conn = base["conn"]
        assert await coleta.pendentes(conn) == []

        desde = (datetime.now(FUSO_OPERACAO) - timedelta(days=20)).date()
        assert await coleta.elegiveis_desde(conn, desde) == [UUID(velha["id"])]
        assert UUID(sem_texto["id"]) not in await coleta.elegiveis_desde(conn, desde)

        await coleta.avaliar(conn, UUID(velha["id"]))
        assert await coleta.elegiveis_desde(conn, desde) == []
        assert await coleta.elegiveis_desde(conn, desde, refazer=True) == [UUID(velha["id"])]
        await coleta.validar(conn, UUID(velha["id"]), None, True)
        assert await coleta.elegiveis_desde(conn, desde, refazer=True) == []


# ── Monitor ──────────────────────────────────────────────────────────


def _fim_do_mes() -> str:
    h = datetime.now(FUSO_OPERACAO).date()
    return date(h.year, h.month, monthrange(h.year, h.month)[1]).isoformat()


def _no_mes(dia: int) -> datetime:
    h = datetime.now(FUSO_OPERACAO)
    return datetime(h.year, h.month, dia, 10, tzinfo=FUSO_OPERACAO)


class TestMonitor:
    async def test_media_no_quadro_e_nota_no_detalhe(self, base, client, monkeypatch):
        ligar_ia(monkeypatch, [resultado(NOTAS), resultado([2] * 10)])
        conn, h = base["conn"], base["h"]
        a = await reuniao(base, client, inicio=_no_mes(1), desfecho="realizada")
        b = await reuniao(base, client, inicio=_no_mes(2), desfecho="realizada")
        sem = await reuniao(base, client, inicio=_no_mes(3), desfecho="realizada",
                            transcricao=False)
        await coleta.avaliar(conn, UUID(a["id"]))     # 12
        await coleta.avaliar(conn, UUID(b["id"]))     # 20
        await coleta.validar(conn, UUID(b["id"]), None, True)

        params = {"hoje": _fim_do_mes()}
        painel = (await client.get("/monitor/painel", params=params, headers=h)).json()
        q = next(i for i in painel["indicadores"] if i["chave"] == "scorecard")
        # Media das AVALIADAS: a sem transcricao fica fora, e nao conta zero.
        assert q["resultado"] == 16.0
        assert q["meta"] == 15.0
        assert q["carinha"] == "feliz"          # 16 / 15 = 107%

        apre = (await client.get("/monitor/detalhe/apre", params=params, headers=h)).json()
        notas = {i["reuniao_id"]: (i["nota"], i["nota_status"]) for i in apre["itens"]}
        assert notas[a["id"]] == (12.0, "ia")
        assert notas[b["id"]] == (20.0, "validada")
        assert notas[sem["id"]] == (None, None)

        d = (await client.get("/monitor/detalhe/scorecard", params=params, headers=h)).json()
        assert d["resultado"] == 16.0
        assert d["tipo"] == "reunioes"
        assert "2 reuniões avaliadas" in d["resumo"]
        assert "3 realizadas" in d["resumo"]
        # Pior nota primeiro; a sem nota no fim e fora da conta.
        assert [i["reuniao_id"] for i in d["itens"]] == [a["id"], b["id"], sem["id"]]
        assert [i["conta"] for i in d["itens"]] == [True, True, False]

    async def test_meta_gravada_vence_o_padrao_e_tem_teto(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        h = base["h"]
        hoje = datetime.now(FUSO_OPERACAO).date()
        resp = await client.put("/monitor/metas", json={
            "ano": hoje.year, "mes": hoje.month,
            "metas": [{"indicador": "scorecard", "valor": 21}],
        }, headers=h)
        assert resp.status_code == 422
        resp = await client.put("/monitor/metas", json={
            "ano": hoje.year, "mes": hoje.month,
            "metas": [{"indicador": "scorecard", "valor": 12}],
        }, headers=h)
        assert resp.status_code == 200, resp.text
        meta = next(m for m in resp.json()["metas"] if m["indicador"] == "scorecard")
        assert (meta["valor"], meta["padrao"]) == (12.0, 15.0)

        painel = (await client.get("/monitor/painel", headers=h)).json()
        q = next(i for i in painel["indicadores"] if i["chave"] == "scorecard")
        assert q["meta"] == 12.0

    async def test_versao_antiga_do_roteiro_nao_entra(self, base, client, monkeypatch):
        ligar_ia(monkeypatch)
        conn, h = base["conn"], base["h"]
        a = await reuniao(base, client, inicio=_no_mes(1), desfecho="realizada")
        await coleta.avaliar(conn, UUID(a["id"]))
        await conn.execute(
            "UPDATE reuniao_avaliacoes SET versao_roteiro = '2000-01-01' WHERE reuniao_id = $1",
            UUID(a["id"]),
        )
        painel = (await client.get(
            "/monitor/painel", params={"hoje": _fim_do_mes()}, headers=h,
        )).json()
        q = next(i for i in painel["indicadores"] if i["chave"] == "scorecard")
        assert q["resultado"] is None


# ── A passada do timer ───────────────────────────────────────────────


class TestPassadaDoTimer:
    async def test_avalia_na_mesma_passada(self, base, client, monkeypatch):
        import time

        from scripts import coletar_transcricoes as script

        ligar_ia(monkeypatch)
        r = await reuniao(base, client)
        feitas = await script.avaliar_pendentes(base["conn"], time.monotonic())
        assert feitas == 1
        corpo = (await client.get(url(r), headers=base["h"])).json()
        assert corpo["status"] == "pronta"
        assert corpo["nota_total"] == 12

    async def test_orcamento_esgotado_deixa_para_a_proxima(self, base, client, monkeypatch):
        import time

        from scripts import coletar_transcricoes as script

        chamadas = ligar_ia(monkeypatch)
        await reuniao(base, client)
        inicio = time.monotonic() - script.ORCAMENTO_AVALIACAO_S - 1
        assert await script.avaliar_pendentes(base["conn"], inicio) == 0
        assert chamadas == []
        assert len(await coleta.pendentes(base["conn"])) == 1

    async def test_ia_desligada_nao_faz_nada(self, base, client, monkeypatch):
        import time

        from scripts import coletar_transcricoes as script

        monkeypatch.setattr(aval, "configurado", lambda: False)
        await reuniao(base, client)
        assert await script.avaliar_pendentes(base["conn"], time.monotonic()) == 0
