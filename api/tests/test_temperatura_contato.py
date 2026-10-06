"""
HIPO — Temperatura do contato (046): regra pura e o que chega na API.

Só tarefa CONCLUÍDA conta; aberta, futura e cancelada (inclui no-show) não.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services import temperatura_contato as t

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def ha(dias, tipo="ligacao"):
    return t.Interacao(tipo=tipo, concluida_em=AGORA - timedelta(days=dias))


class TestRegra:
    def test_nunca_falou_e_frio(self):
        r = t.calcular([], AGORA)
        assert (r.nivel, r.pontos, r.ultima_interacao) == ("frio", 0, None)

    def test_duas_ligacoes_na_semana_e_quente(self):
        r = t.calcular([ha(2), ha(5)], AGORA)
        assert (r.nivel, r.pontos) == ("quente", 6)

    def test_uma_reuniao_realizada_recente_e_quente(self):
        """Reunião vale o dobro: a pessoa reservou tempo para você."""
        r = t.calcular([ha(10, "reuniao")], AGORA)
        assert (r.nivel, r.pontos) == ("quente", 6)

    def test_um_contato_recente_e_morno(self):
        assert t.calcular([ha(5, "whatsapp")], AGORA).nivel == "morno"

    def test_conversa_antiga_e_fria(self):
        r = t.calcular([ha(40)], AGORA)
        assert (r.nivel, r.pontos) == ("frio", 1)

    def test_fora_da_janela_nao_pontua(self):
        r = t.calcular([ha(61), ha(90, "reuniao")], AGORA)
        assert (r.nivel, r.pontos, r.interacoes_janela) == ("frio", 0, 0)
        assert r.dias_desde_ultima == 61

    def test_muito_ponto_sem_recencia_nao_e_quente(self):
        """Três reuniões há 3 semanas e silêncio desde então: morno."""
        r = t.calcular([ha(20, "reuniao"), ha(22, "reuniao"), ha(25, "reuniao")], AGORA)
        assert r.pontos == 12
        assert r.nivel == "morno"

    def test_ultima_conhecida_antiga_aparece(self):
        antiga = AGORA - timedelta(days=120)
        r = t.calcular([], AGORA, antiga)
        assert (r.nivel, r.dias_desde_ultima) == ("frio", 120)

    def test_concluida_no_futuro_conta_como_hoje(self):
        r = t.calcular([t.Interacao("ligacao", AGORA + timedelta(days=2))], AGORA)
        assert r.dias_desde_ultima == 0 and r.pontos == 3

    @pytest.mark.parametrize("dias,peso", [(0, 3), (14, 3), (15, 2), (30, 2), (31, 1), (60, 1), (61, 0)])
    def test_faixas_de_recencia(self, dias, peso):
        assert t.peso_recencia(dias) == peso

    def test_dict_para_a_api(self):
        d = t.como_dict(t.calcular([ha(1)], AGORA))
        assert d["temperatura"] == "morno" and d["temperatura_rotulo"] == "Morno"
        assert d["interacoes_60d"] == 1


# ── Na API ───────────────────────────────────────────────────────────

CNPJ = "11.222.333/0001-81"


@pytest.fixture
async def base(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = (await client.post("/crm/contas", json={"razao_social": "Alfa LTDA", "cnpj": CNPJ}, headers=h)).json()
    ana = (await client.post("/crm/contatos", json={"nome": "Ana", "conta_id": conta["id"]}, headers=h)).json()
    opp = (await client.post("/crm/oportunidades",
                             json={"conta_id": conta["id"], "contato_id": ana["id"]}, headers=h)).json()
    uid = (await client.get("/auth/me", headers=h)).json()["id"]
    return {"h": h, "conta": conta, "ana": ana, "opp": opp, "uid": uid, "conn": db_conn}


async def tarefa(b, tipo="ligacao", concluida_ha=None, cancelada=False, futura=False):
    prazo = datetime.now(timezone.utc) + (timedelta(days=3) if futura else -timedelta(days=1))
    concluida = (datetime.now(timezone.utc) - timedelta(days=concluida_ha)) if concluida_ha is not None else None
    await b["conn"].execute(
        """
        INSERT INTO tarefas (oportunidade_id, tipo, titulo, responsavel_id, prazo,
                             contato_id, concluida_em, cancelada_em)
        VALUES ($1, $2, 'x', $3, $4, $5, $6, $7)
        """,
        uuid.UUID(b["opp"]["id"]), tipo, uuid.UUID(b["uid"]), prazo,
        uuid.UUID(b["ana"]["id"]), concluida,
        datetime.now(timezone.utc) if cancelada else None,
    )


async def temperatura_no_comite(client, b):
    r = await client.get(f"/crm/oportunidades/{b['opp']['id']}/contatos", headers=b["h"])
    assert r.status_code == 200, r.text
    return r.json()["itens"][0]


class TestNaApi:
    async def test_futura_e_cancelada_nao_esquentam(self, base, client):
        await tarefa(base, futura=True)
        await tarefa(base, "reuniao", cancelada=True)
        await tarefa(base, "ligacao")              # aberta, atrasada
        item = await temperatura_no_comite(client, base)
        assert item["temperatura"] == "frio"
        assert item["interacoes_60d"] == 0

    async def test_concluidas_recentes_esquentam(self, base, client):
        await tarefa(base, concluida_ha=1)
        await tarefa(base, "reuniao", concluida_ha=3)
        item = await temperatura_no_comite(client, base)
        assert item["temperatura"] == "quente"
        assert item["temperatura_pontos"] == 9
        assert item["dias_desde_ultima_conversa"] == 1

    async def test_ficha_da_conta_mostra_a_temperatura(self, base, client):
        await tarefa(base, "whatsapp", concluida_ha=20)
        r = await client.get(f"/crm/contas/{base['conta']['id']}", headers=base["h"])
        contato = r.json()["contatos"][0]
        assert (contato["temperatura"], contato["temperatura_pontos"]) == ("morno", 2)

    async def test_conversa_antiga_aparece_como_ultima(self, base, client):
        await tarefa(base, concluida_ha=100)
        item = await temperatura_no_comite(client, base)
        assert item["temperatura"] == "frio"
        assert item["dias_desde_ultima_conversa"] == 100
