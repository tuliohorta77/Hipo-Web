"""
HIPO — Testes do router /monitor (o painel de parede).

As regras puras estao em test_monitor_regras.py. Aqui o foco e o que so
aparece com banco:

  * cada indicador saindo da MESMA fonte da tela dele (evento de fase,
    desfecho da reuniao, evento de status da venda)
  * o recorte MTD: do dia 1o ate hoje, no fuso da operacao
  * a meta proporcional aos dias uteis, descontando os feriados da tabela
  * metas e feriados: leitura para todos, escrita so para a gestao
"""
from datetime import date, datetime, timedelta

import pytest

from services import tarefa as regras_tarefa
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_B = "11.444.777/0001-61"


def em(dia: int, mes: int | None = None, hora: int = 10) -> str:
    """Um instante no fuso da operacao, no mes corrente por padrao."""
    hoje = datetime.now(regras_tarefa.FUSO_OPERACAO)
    return datetime(
        hoje.year, mes or hoje.month, dia, hora, tzinfo=regras_tarefa.FUSO_OPERACAO
    ).isoformat()


def hoje_op() -> date:
    return datetime.now(regras_tarefa.FUSO_OPERACAO).date()


def indicador(corpo, chave):
    return next(i for i in corpo["indicadores"] if i["chave"] == chave)


async def nova_conta(client, headers, cnpj=CNPJ_A, razao="Metalurgica Alfa LTDA"):
    resp = await client.post(
        "/crm/contas", json={"razao_social": razao, "cnpj": cnpj}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_oportunidade(client, headers, conta_id, **extra):
    corpo = {"conta_id": conta_id}
    corpo.update(extra)
    resp = await client.post("/crm/oportunidades", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = await nova_conta(client, h)
    me = (await client.get("/auth/me", headers=h)).json()
    return {"headers": h, "conta": conta, "usuario_id": me["id"], "db": db_conn}


async def painel(client, headers, **params):
    resp = await client.get("/monitor/painel", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── O painel ─────────────────────────────────────────────────────────

class TestPainel:
    async def test_dez_quadros_na_ordem_da_parede(self, cenario, client):
        corpo = await painel(client, cenario["headers"])
        assert [i["chave"] for i in corpo["indicadores"]] == [
            "lead", "agen", "apre", "nmrr", "ticket_medio",
            "reunioes_parceria", "agendamentos_mes", "noshow",
            "contratos", "treinamento",
        ]
        # O mes corrente, sem ninguem escolher: e a TV.
        assert corpo["ano"] == hoje_op().year
        assert corpo["mes"] == hoje_op().month
        assert corpo["atualizado_em"]

    async def test_operacional_ve_o_painel(self, db_conn, client, usuario_adm):
        """A TV fica na sala: o painel e de todo mundo."""
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-monitor@teste.com")
        resp = await client.get("/monitor/painel", headers=sdr["headers"])
        assert resp.status_code == 200

    async def test_sem_meta_o_quadro_fica_sem_carinha(self, cenario, client):
        corpo = await painel(client, cenario["headers"])
        lead = indicador(corpo, "lead")
        assert lead["meta"] is None
        assert lead["carinha"] is None
        assert lead["resultado"] == 0

    async def test_treinamento_fica_aberto(self, cenario, client):
        """Nao existe treinamento neste negocio ainda: quadro reservado."""
        t = indicador(await painel(client, cenario["headers"]), "treinamento")
        assert t["natureza"] == "aberto"
        assert t["resultado"] is None
        assert t["carinha"] is None

    async def test_ano_sem_mes_e_422(self, cenario, client):
        resp = await client.get(
            "/monitor/painel", params={"ano": 2026}, headers=cenario["headers"]
        )
        assert resp.status_code == 422


# ── Leads ────────────────────────────────────────────────────────────

class TestLead:
    async def test_conta_quem_passou_de_suspect_para_lead(self, cenario, client):
        h = cenario["headers"]
        a = await nova_oportunidade(client, h, cenario["conta"]["id"])
        b = await nova_oportunidade(client, h, cenario["conta"]["id"])
        for o in (a, b):
            resp = await client.patch(
                f"/crm/oportunidades/{o['id']}/fase", json={"fase": "lead"}, headers=h
            )
            assert resp.status_code == 200, resp.text
        # Avancar de lead para qualificacao NAO conta de novo: a pergunta e
        # quantos ENTRARAM, nao onde estao agora.
        await client.patch(
            f"/crm/oportunidades/{b['id']}/fase",
            json={"fase": "qualificacao"}, headers=h,
        )
        corpo = await painel(client, h)
        assert indicador(corpo, "lead")["resultado"] == 2

    async def test_evento_de_outro_mes_nao_entra(self, cenario, client, db_conn):
        h = cenario["headers"]
        o = await nova_oportunidade(client, h, cenario["conta"]["id"])
        await client.patch(
            f"/crm/oportunidades/{o['id']}/fase", json={"fase": "lead"}, headers=h
        )
        # Empurra o evento para o mes passado, como se tivesse acontecido la.
        await db_conn.execute(
            "UPDATE oportunidade_eventos SET criado_em = criado_em - interval '45 days'"
        )
        assert indicador(await painel(client, h), "lead")["resultado"] == 0


# ── Reunioes ─────────────────────────────────────────────────────────

class TestReunioes:
    async def _reuniao(self, client, h, opp_id, uid, dia, **extra):
        corpo = {
            "oportunidade_id": opp_id, "anfitriao_id": uid, "inicio": em(dia),
        }
        corpo.update(extra)
        resp = await client.post("/crm/agenda/reunioes", json=corpo, headers=h)
        assert resp.status_code == 201, resp.text
        return resp.json()

    async def _dia_util(self, offset=0):
        """Um dia do mes corrente que nao e fim de semana, a partir do dia 1."""
        primeiro = hoje_op().replace(day=1)
        dia = primeiro
        vistos = 0
        while True:
            if dia.weekday() < 5:
                if vistos == offset:
                    return dia.day
                vistos += 1
            dia += timedelta(days=1)

    async def test_agen_apre_e_noshow_saem_do_desfecho(self, cenario, client):
        """
        A mesma regra de desfecho da Agenda: realizada conta em APRE,
        desmarcada sai de AGEN, no-show fica nas duas contas do denominador.
        """
        h, uid = cenario["headers"], cenario["usuario_id"]
        opp = await nova_oportunidade(client, h, cenario["conta"]["id"])
        dias = [await self._dia_util(i) for i in range(3)]
        feita = await self._reuniao(client, h, opp["id"], uid, dias[0])
        nao_veio = await self._reuniao(client, h, opp["id"], uid, dias[1])
        desmarcada = await self._reuniao(client, h, opp["id"], uid, dias[2])

        await client.post(
            f"/crm/agenda/reunioes/{feita['id']}/desfecho",
            json={"desfecho": "realizada", "proxima": {
                "tipo": "ligacao", "titulo": "Retomar",
                "responsavel_id": uid, "prazo": em(28),
            }},
            headers=h,
        )
        for r, d in ((nao_veio, "no_show"), (desmarcada, "cancelada")):
            resp = await client.post(
                f"/crm/agenda/reunioes/{r['id']}/desfecho",
                json={"desfecho": d}, headers=h,
            )
            assert resp.status_code == 200, resp.text

        corpo = await painel(client, h)
        assert indicador(corpo, "apre")["resultado"] == 1
        assert indicador(corpo, "agen")["resultado"] == 2      # a desmarcada sai
        assert indicador(corpo, "agendamentos_mes")["resultado"] == 3
        # 1 no-show em 3 reunioes fechadas.
        assert indicador(corpo, "noshow")["resultado"] == 33.3

    async def test_noshow_sem_reuniao_fechada_e_indefinido(self, cenario, client):
        h, uid = cenario["headers"], cenario["usuario_id"]
        opp = await nova_oportunidade(client, h, cenario["conta"]["id"])
        await self._reuniao(client, h, opp["id"], uid, await self._dia_util(0))
        corpo = await painel(client, h)
        assert indicador(corpo, "noshow")["resultado"] is None
        assert indicador(corpo, "agen")["resultado"] == 1

    async def test_reuniao_de_parceria_vem_das_tarefas_do_parceiro(
        self, cenario, client,
    ):
        h, uid = cenario["headers"], cenario["usuario_id"]
        parceiro = await nova_conta(client, h, CNPJ_B, "Contabilidade Beta LTDA")
        await client.patch(
            f"/crm/parceiros/{parceiro['id']}", json={"eh_finder": True}, headers=h
        )
        r = await self._reuniao(
            client, h, None, uid, await self._dia_util(0), conta_id=parceiro["id"],
            oportunidade_id=None,
        )
        # So a REALIZADA conta.
        antes = await painel(client, h)
        assert indicador(antes, "reunioes_parceria")["resultado"] == 0

        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "realizada", "proxima": {
                "tipo": "ligacao", "titulo": "Retomar",
                "responsavel_id": uid, "prazo": em(28),
            }},
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        depois = await painel(client, h)
        assert indicador(depois, "reunioes_parceria")["resultado"] == 1
        # Reuniao de parceria tambem e reuniao realizada: os dois quadros
        # contam, de proposito, porque respondem perguntas diferentes.
        assert indicador(depois, "apre")["resultado"] == 1


# ── Vendas ───────────────────────────────────────────────────────────

class TestVendas:
    async def _ganhar(self, client, h, uid, conta_id, mensalidade):
        opp = await nova_oportunidade(
            client, h, conta_id, valor_mensalidade=mensalidade,
        )
        resp = await client.post(
            f"/crm/oportunidades/{opp['id']}/desfecho",
            json={
                "status": "conquistado",
                "tarefa": {
                    "tipo": "reuniao", "titulo": "Assinatura",
                    "responsavel_id": uid, "prazo": em(hoje_op().day),
                },
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        return opp

    async def test_contratos_nmrr_e_ticket_medio(self, cenario, client):
        h, uid = cenario["headers"], cenario["usuario_id"]
        await self._ganhar(client, h, uid, cenario["conta"]["id"], 1000)
        await self._ganhar(client, h, uid, cenario["conta"]["id"], 2000)
        corpo = await painel(client, h)
        assert indicador(corpo, "contratos")["resultado"] == 2
        assert indicador(corpo, "nmrr")["resultado"] == 3000
        assert indicador(corpo, "ticket_medio")["resultado"] == 1500

    async def test_sem_venda_ticket_medio_e_indefinido(self, cenario, client):
        corpo = await painel(client, cenario["headers"])
        assert indicador(corpo, "contratos")["resultado"] == 0
        assert indicador(corpo, "nmrr")["resultado"] == 0
        assert indicador(corpo, "ticket_medio")["resultado"] is None

    async def test_venda_de_outro_mes_nao_entra(self, cenario, client, db_conn):
        h, uid = cenario["headers"], cenario["usuario_id"]
        await self._ganhar(client, h, uid, cenario["conta"]["id"], 1000)
        await db_conn.execute(
            """
            UPDATE oportunidade_eventos SET criado_em = criado_em - interval '45 days'
             WHERE tipo = 'status' AND para = 'conquistado'
            """
        )
        corpo = await painel(client, h)
        assert indicador(corpo, "contratos")["resultado"] == 0
        assert indicador(corpo, "nmrr")["resultado"] == 0


# ── Meta MTD ─────────────────────────────────────────────────────────

class TestMetaMtd:
    async def test_meta_e_proporcional_e_desconta_feriado(self, cenario, client):
        """
        O painel pedido em data fixa, com a meta do mes e um feriado no meio:
        a meta de hoje sai de `meta * dia_util_atual / dias_uteis`.

        Marco/2026 comeca num domingo e tem 22 dias uteis (sem feriado
        nacional). Com o dia 4 marcado como feriado sobram 21, e o dia 10
        (terca) passa a ser o 6o dia util: 2, 3, 5, 6, 9 e 10.
        """
        h = cenario["headers"]
        resp = await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 3, "metas": [
                {"indicador": "lead", "valor": 210},
                {"indicador": "noshow", "valor": 30},
            ]},
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        await client.post(
            "/monitor/feriados",
            json={"data": "2026-03-04", "motivo": "Ponto facultativo"}, headers=h,
        )

        corpo = await painel(client, h, ano=2026, mes=3, hoje="2026-03-10")
        assert corpo["dias_uteis"] == 21
        assert corpo["dia_util_atual"] == 6
        lead = indicador(corpo, "lead")
        assert lead["meta"] == 210
        assert lead["meta_mtd"] == pytest.approx(210 * 6 / 21)
        # Zero resultado com meta definida: bravo, nao "sem carinha".
        assert lead["carinha"] == "bravo"

        # Taxa nao se proporcionaliza: a meta de no-show continua 30%.
        assert indicador(corpo, "noshow")["meta_mtd"] == 30.0

    async def test_carinha_segue_a_regua(self, cenario, client):
        h, uid = cenario["headers"], cenario["usuario_id"]
        opp = await nova_oportunidade(client, h, cenario["conta"]["id"])
        await client.patch(
            f"/crm/oportunidades/{opp['id']}/fase", json={"fase": "lead"}, headers=h
        )
        hoje = hoje_op()
        # Meta de 1 lead no mes inteiro: com 1 lead feito, o atingimento de
        # hoje passa de 110% em qualquer dia do mes.
        await client.put(
            "/monitor/metas",
            json={"ano": hoje.year, "mes": hoje.month,
                  "metas": [{"indicador": "lead", "valor": 1}]},
            headers=h,
        )
        lead = indicador(await painel(client, h), "lead")
        assert lead["carinha"] in ("feliz", "muito_feliz")
        assert lead["atingimento_mes"] == 1.0

    async def test_mes_fechado_mostra_o_mes_inteiro(self, cenario, client):
        """Painel de um mes que ja passou nao para no dia de hoje."""
        corpo = await painel(client, cenario["headers"], ano=2026, mes=1, hoje="2026-03-10")
        assert corpo["hoje"] == "2026-01-31"
        assert corpo["dia_util_atual"] == corpo["dias_uteis"]


# ── Metas ────────────────────────────────────────────────────────────

class TestMetas:
    async def test_lista_traz_todos_os_indicadores(self, cenario, client):
        corpo = (await client.get(
            "/monitor/metas", params={"ano": 2026, "mes": 5}, headers=cenario["headers"]
        )).json()
        assert len(corpo["metas"]) == 10
        assert all(m["valor"] is None for m in corpo["metas"])

    async def test_grava_e_apaga(self, cenario, client):
        h = cenario["headers"]
        corpo = (await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [{"indicador": "apre", "valor": 171}]},
            headers=h,
        )).json()
        assert next(m for m in corpo["metas"] if m["indicador"] == "apre")["valor"] == 171

        # null APAGA; zero seria "este mes nao se cobra".
        corpo = (await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [{"indicador": "apre", "valor": None}]},
            headers=h,
        )).json()
        assert next(m for m in corpo["metas"] if m["indicador"] == "apre")["valor"] is None

    async def test_indicador_invalido_e_422(self, cenario, client):
        resp = await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [{"indicador": "faturamento", "valor": 10}]},
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_copiar_do_mes_anterior_nao_sobrescreve(self, cenario, client):
        h = cenario["headers"]
        await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [
                {"indicador": "lead", "valor": 200},
                {"indicador": "apre", "valor": 100},
            ]},
            headers=h,
        )
        await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 6, "metas": [{"indicador": "lead", "valor": 300}]},
            headers=h,
        )
        corpo = (await client.post(
            "/monitor/metas/copiar", params={"ano": 2026, "mes": 6}, headers=h
        )).json()
        por_chave = {m["indicador"]: m["valor"] for m in corpo["metas"]}
        assert por_chave["lead"] == 300     # o que ja estava definido fica
        assert por_chave["apre"] == 100     # o que faltava vem do mes anterior

    async def test_operacional_le_mas_nao_grava(self, db_conn, client, usuario_adm):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-metas@teste.com")
        assert (await client.get(
            "/monitor/metas", params={"ano": 2026, "mes": 5}, headers=sdr["headers"]
        )).status_code == 200
        resp = await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [{"indicador": "lead", "valor": 1}]},
            headers=sdr["headers"],
        )
        assert resp.status_code == 403

    async def test_ec_tambem_nao_grava(self, db_conn, client, usuario_adm):
        """Metas sao da gestao: EC tem modulo de parceiros, nao a regua."""
        ec = await criar_usuario(db_conn, client, "EC", "ec-metas@teste.com")
        resp = await client.put(
            "/monitor/metas",
            json={"ano": 2026, "mes": 5, "metas": [{"indicador": "lead", "valor": 1}]},
            headers=ec["headers"],
        )
        assert resp.status_code == 403


# ── Feriados ─────────────────────────────────────────────────────────

class TestFeriados:
    async def test_cria_lista_e_apaga(self, cenario, client):
        h = cenario["headers"]
        criado = (await client.post(
            "/monitor/feriados",
            json={"data": "2026-06-18", "motivo": "Aniversario da cidade"}, headers=h,
        ))
        assert criado.status_code == 201, criado.text
        feriado = criado.json()

        lista = (await client.get(
            "/monitor/feriados", params={"ano": 2026}, headers=h
        )).json()
        assert [f["data"] for f in lista] == ["2026-06-18"]

        assert (await client.delete(
            f"/monitor/feriados/{feriado['id']}", headers=h
        )).status_code == 204
        assert (await client.get(
            "/monitor/feriados", params={"ano": 2026}, headers=h
        )).json() == []

    async def test_mesma_data_corrige_o_motivo(self, cenario, client):
        h = cenario["headers"]
        await client.post(
            "/monitor/feriados", json={"data": "2026-06-18", "motivo": "errado"}, headers=h
        )
        de_novo = await client.post(
            "/monitor/feriados", json={"data": "2026-06-18", "motivo": "certo"}, headers=h
        )
        assert de_novo.status_code == 201
        assert de_novo.json()["motivo"] == "certo"

    async def test_feriados_nacionais_sao_idempotentes(self, cenario, client):
        h = cenario["headers"]
        primeira = (await client.post(
            "/monitor/feriados/nacionais", params={"ano": 2026}, headers=h
        )).json()
        assert len(primeira) >= 11
        # A Pascoa de 2026 e em 5 de abril: Sexta-feira Santa cai em 3/4.
        assert "2026-04-03" in [f["data"] for f in primeira]
        segunda = (await client.post(
            "/monitor/feriados/nacionais", params={"ano": 2026}, headers=h
        )).json()
        assert len(segunda) == len(primeira)

    async def test_nacionais_nao_reescrevem_o_que_a_gestao_ajustou(
        self, cenario, client,
    ):
        h = cenario["headers"]
        await client.post(
            "/monitor/feriados",
            json={"data": "2026-12-25", "motivo": "Natal — recesso ate dia 2"},
            headers=h,
        )
        lista = (await client.post(
            "/monitor/feriados/nacionais", params={"ano": 2026}, headers=h
        )).json()
        natal = next(f for f in lista if f["data"] == "2026-12-25")
        assert natal["motivo"] == "Natal — recesso ate dia 2"

    async def test_operacional_le_mas_nao_marca(self, db_conn, client, usuario_adm):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-feriado@teste.com")
        assert (await client.get(
            "/monitor/feriados", headers=sdr["headers"]
        )).status_code == 200
        resp = await client.post(
            "/monitor/feriados",
            json={"data": "2026-06-18", "motivo": "x"}, headers=sdr["headers"],
        )
        assert resp.status_code == 403

    async def test_apagar_inexistente_e_404(self, cenario, client):
        resp = await client.delete("/monitor/feriados/999999", headers=cenario["headers"])
        assert resp.status_code == 404
