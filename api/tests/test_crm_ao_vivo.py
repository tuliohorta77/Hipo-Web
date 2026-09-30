"""
HIPO — Transcrição ao vivo: endpoints, com banco.

As regras puras estão em test_ao_vivo_regras.py. Aqui a costura:

  * quem pode ligar a captura (anfitrião, participante, gestão) e quando
  * o lote: grava, reenvio não duplica, fala vazia some, limites
  * a sessão é de quem abriu; encerrada não aceita mais texto
  * a leitura junta as sessões, mede a proporção de fala e compara com a
    transcrição do Meet quando ela já chegou

Nenhum áudio passa pelo servidor: os testes mandam texto, como o navegador.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from tests.conftest import criar_usuario
from tests.test_crm_agenda import nova_reuniao

UTC = timezone.utc


def agora():
    return datetime.now(UTC)


# ── Cenário ──────────────────────────────────────────────────────────


@pytest.fixture
async def base(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = (await client.post(
        "/crm/contas",
        json={"razao_social": "Caldeiraria Beta LTDA", "cnpj": "11.222.333/0001-81"},
        headers=h,
    )).json()
    opp = (await client.post(
        "/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h,
    )).json()
    ev = await criar_usuario(db_conn, client, "EV", "ev-aovivo@teste.com")
    ev["id"] = (await client.get("/auth/me", headers=ev["headers"])).json()["id"]
    return {"h": h, "opp": opp, "ev": ev, "conn": db_conn}


async def reuniao_agora(base, client, **extra):
    """
    Reunião do EV começando há 5 minutos. Nasce no futuro pela API (a
    agenda não aceita marcar no passado) e é trazida para agora por SQL.
    """
    r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["ev"]["id"], **extra)
    await base["conn"].execute(
        "UPDATE tarefas SET prazo = $2 WHERE id = $1",
        UUID(r["tarefa_id"]), agora() - timedelta(minutes=5),
    )
    return r


def url(r, sufixo=""):
    return f"/crm/agenda/tarefas/{r['tarefa_id']}/ao-vivo{sufixo}"


async def abrir(client, r, headers, canais=("vendedor", "cliente")):
    resp = await client.post(
        url(r), json={"canais": list(canais), "navegador": "Chrome 141"}, headers=headers,
    )
    return resp


def fala(seq, canal="vendedor", texto="bom dia", minutos=0):
    ini = agora() + timedelta(minutes=minutos, seconds=seq)
    return {
        "seq": seq, "canal": canal, "texto": texto,
        "inicio": ini.isoformat(), "fim": (ini + timedelta(seconds=2)).isoformat(),
        "confianca": 0.9,
    }


# ── Abrir ────────────────────────────────────────────────────────────


class TestAbrir:
    async def test_anfitriao_abre(self, base, client):
        r = await reuniao_agora(base, client)
        resp = await abrir(client, r, base["ev"]["headers"])
        assert resp.status_code == 201, resp.text
        s = resp.json()
        assert s["canais"] == ["vendedor", "cliente"]
        assert s["navegador"] == "Chrome 141"
        assert s["encerrada_em"] is None
        assert s["usuario_id"] == base["ev"]["id"]

    async def test_canal_repetido_vira_um(self, base, client):
        r = await reuniao_agora(base, client)
        resp = await abrir(client, r, base["ev"]["headers"], canais=("cliente", "cliente"))
        assert resp.json()["canais"] == ["cliente"]

    async def test_sem_canal_recusa(self, base, client):
        r = await reuniao_agora(base, client)
        resp = await client.post(url(r), json={"canais": []}, headers=base["ev"]["headers"])
        assert resp.status_code == 422

    async def test_canal_invalido_recusa(self, base, client):
        r = await reuniao_agora(base, client)
        resp = await client.post(url(r), json={"canais": ["sala"]}, headers=base["ev"]["headers"])
        assert resp.status_code == 422

    async def test_gestao_abre(self, base, client):
        r = await reuniao_agora(base, client)
        assert (await abrir(client, r, base["h"])).status_code == 201

    async def test_participante_abre(self, base, client):
        ep = await criar_usuario(base["conn"], client, "EP", "ep-aovivo@teste.com")
        ep_id = (await client.get("/auth/me", headers=ep["headers"])).json()["id"]
        r = await reuniao_agora(base, client, participantes=[ep_id])
        assert (await abrir(client, r, ep["headers"])).status_code == 201

    async def test_quem_nao_esta_na_reuniao_nao_abre(self, base, client):
        sdr = await criar_usuario(base["conn"], client, "SDR", "sdr-aovivo@teste.com")
        r = await reuniao_agora(base, client)
        resp = await abrir(client, r, sdr["headers"])
        assert resp.status_code == 403
        assert "anfitrião" in resp.json()["detail"]

    async def test_tarefa_que_nao_e_reuniao(self, base, client):
        resp = await client.post(
            f"/crm/agenda/tarefas/{uuid4()}/ao-vivo",
            json={"canais": ["vendedor"]}, headers=base["h"],
        )
        assert resp.status_code == 404

    async def test_cedo_demais(self, base, client):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["ev"]["id"])
        resp = await abrir(client, r, base["ev"]["headers"])
        assert resp.status_code == 422
        assert "cedo" in resp.json()["detail"]

    async def test_cancelada(self, base, client):
        r = await reuniao_agora(base, client)
        await base["conn"].execute(
            "UPDATE tarefas SET cancelada_em = NOW() WHERE id = $1", UUID(r["tarefa_id"]),
        )
        resp = await abrir(client, r, base["ev"]["headers"])
        assert resp.status_code == 422
        assert "cancelada" in resp.json()["detail"]

    async def test_presencial(self, base, client):
        r = await reuniao_agora(base, client)
        await base["conn"].execute(
            "UPDATE reunioes SET modalidade = 'presencial' WHERE id = $1", UUID(r["id"]),
        )
        resp = await abrir(client, r, base["ev"]["headers"])
        assert resp.status_code == 422

    async def test_abrir_de_novo_encerra_a_anterior_da_mesma_pessoa(self, base, client):
        r = await reuniao_agora(base, client)
        s1 = (await abrir(client, r, base["ev"]["headers"])).json()
        s2 = (await abrir(client, r, base["ev"]["headers"])).json()
        assert s1["id"] != s2["id"]
        linhas = await base["conn"].fetch(
            "SELECT id, encerrada_em FROM reuniao_sessoes_ao_vivo ORDER BY iniciada_em",
        )
        assert linhas[0]["encerrada_em"] is not None
        assert linhas[1]["encerrada_em"] is None

    async def test_sessao_de_outra_pessoa_continua_aberta(self, base, client):
        r = await reuniao_agora(base, client)
        await abrir(client, r, base["h"])
        await abrir(client, r, base["ev"]["headers"])
        abertas = await base["conn"].fetchval(
            "SELECT count(*) FROM reuniao_sessoes_ao_vivo WHERE encerrada_em IS NULL",
        )
        assert abertas == 2


# ── Lotes ────────────────────────────────────────────────────────────


class TestLotes:
    async def _sessao(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        return r, s

    async def test_grava(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0), fala(1, "cliente", "tudo bem")]},
            headers=base["ev"]["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"recebidas": 2, "gravadas": 2}

    async def test_reenvio_nao_duplica(self, base, client):
        r, s = await self._sessao(base, client)
        corpo = {"falas": [fala(0), fala(1)]}
        u = f"/crm/agenda/ao-vivo/{s['id']}/falas"
        await client.post(u, json=corpo, headers=base["ev"]["headers"])
        resp = await client.post(u, json=corpo, headers=base["ev"]["headers"])
        assert resp.json() == {"recebidas": 2, "gravadas": 0}
        assert await base["conn"].fetchval("SELECT count(*) FROM reuniao_falas_ao_vivo") == 2

    async def test_fala_vazia_some_e_espacos_colapsam(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0, texto="   "), fala(1, texto="  bom   dia ")]},
            headers=base["ev"]["headers"],
        )
        assert resp.json() == {"recebidas": 2, "gravadas": 1}
        assert await base["conn"].fetchval("SELECT texto FROM reuniao_falas_ao_vivo") == "bom dia"

    async def test_texto_longo_demais(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0, texto="a" * 2001)]},
            headers=base["ev"]["headers"],
        )
        assert resp.status_code == 422

    async def test_lote_grande_demais(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(i) for i in range(301)]},
            headers=base["ev"]["headers"],
        )
        assert resp.status_code == 422

    async def test_seq_negativo(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(-1)]},
            headers=base["ev"]["headers"],
        )
        assert resp.status_code == 422

    async def test_sessao_de_outro_usuario_e_404(self, base, client):
        r, s = await self._sessao(base, client)
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0)]}, headers=base["h"],
        )
        assert resp.status_code == 404

    async def test_sessao_inexistente_e_404(self, base, client):
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{uuid4()}/falas",
            json={"falas": [fala(0)]}, headers=base["ev"]["headers"],
        )
        assert resp.status_code == 404

    async def test_erros_acumulam(self, base, client):
        r, s = await self._sessao(base, client)
        u = f"/crm/agenda/ao-vivo/{s['id']}/falas"
        h = base["ev"]["headers"]
        await client.post(u, json={"erros": [{"canal": "cliente", "erro": "network"}]}, headers=h)
        await client.post(u, json={"erros": [{"canal": "vendedor", "erro": "audio-capture"}]}, headers=h)
        erros = await base["conn"].fetchval("SELECT erros FROM reuniao_sessoes_ao_vivo")
        erros = json.loads(erros) if isinstance(erros, str) else erros
        assert [e["erro"] for e in erros] == ["network", "audio-capture"]
        assert all(e["em"] for e in erros)


# ── Encerrar ─────────────────────────────────────────────────────────


class TestEncerrar:
    async def test_grava_o_ultimo_lote_e_fecha(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/encerrar",
            json={"falas": [fala(0), fala(1)]}, headers=base["ev"]["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["encerrada_em"] is not None
        assert resp.json()["falas"] == 2

    async def test_sem_corpo(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/encerrar", headers=base["ev"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["falas"] == 0

    async def test_encerrar_de_novo_nao_mexe_no_horario(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        u = f"/crm/agenda/ao-vivo/{s['id']}/encerrar"
        primeiro = (await client.post(u, headers=base["ev"]["headers"])).json()
        segundo = (await client.post(
            u, json={"falas": [fala(0)]}, headers=base["ev"]["headers"],
        )).json()
        assert primeiro["encerrada_em"] == segundo["encerrada_em"]
        assert segundo["falas"] == 0

    async def test_encerrada_recusa_lote(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        await client.post(f"/crm/agenda/ao-vivo/{s['id']}/encerrar", headers=base["ev"]["headers"])
        resp = await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0)]}, headers=base["ev"]["headers"],
        )
        assert resp.status_code == 409

    async def test_outro_usuario_nao_encerra(self, base, client):
        r = await reuniao_agora(base, client)
        s = (await abrir(client, r, base["ev"]["headers"])).json()
        resp = await client.post(f"/crm/agenda/ao-vivo/{s['id']}/encerrar", headers=base["h"])
        assert resp.status_code == 404


# ── Leitura ──────────────────────────────────────────────────────────


class TestLeitura:
    async def test_vazia(self, base, client):
        r = await reuniao_agora(base, client)
        d = (await client.get(url(r), headers=base["ev"]["headers"])).json()
        assert d["sessoes"] == [] and d["falas"] == []
        assert d["metricas"]["proporcao_vendedor_pct"] is None
        assert d["comparacao"] is None
        assert d["pode_capturar"] is True
        assert d["motivo_bloqueio"] is None
        assert d["empresa"] == "Caldeiraria Beta LTDA"
        assert d["duracao_min"] == 30

    async def test_quem_nao_esta_na_reuniao_ve_mas_nao_captura(self, base, client):
        sdr = await criar_usuario(base["conn"], client, "SDR", "sdr-le@teste.com")
        r = await reuniao_agora(base, client)
        resp = await client.get(url(r), headers=sdr["headers"])
        assert resp.status_code == 200
        assert resp.json()["pode_capturar"] is False

    async def test_fora_da_janela_diz_o_motivo(self, base, client):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["ev"]["id"])
        d = (await client.get(url(r), headers=base["ev"]["headers"])).json()
        assert d["pode_capturar"] is False
        assert "cedo" in d["motivo_bloqueio"]

    async def test_junta_sessoes_em_ordem_e_mede(self, base, client):
        r = await reuniao_agora(base, client)
        h = base["ev"]["headers"]
        s1 = (await abrir(client, r, h)).json()
        await client.post(
            f"/crm/agenda/ao-vivo/{s1['id']}/falas",
            json={"falas": [fala(0, "vendedor", "um dois tres", minutos=0)]}, headers=h,
        )
        s2 = (await abrir(client, r, h)).json()
        await client.post(
            f"/crm/agenda/ao-vivo/{s2['id']}/falas",
            json={"falas": [
                fala(0, "cliente", "quatro", minutos=2),
                fala(1, "vendedor", "antes", minutos=-1),
            ]},
            headers=h,
        )
        d = (await client.get(url(r), headers=h)).json()
        assert [f["texto"] for f in d["falas"]] == ["antes", "um dois tres", "quatro"]
        assert len(d["sessoes"]) == 2
        assert d["sessoes"][0]["encerrada_em"] is not None
        assert d["sessoes"][0]["falas"] == 1
        assert d["sessoes"][0]["usuario_nome"] == "Test EV"
        assert d["metricas"] == {
            "falas": 3, "palavras_vendedor": 4, "palavras_cliente": 1,
            "palavras_total": 5, "proporcao_vendedor_pct": 80,
        }

    async def test_compara_com_o_meet_pelas_falas_e_nao_pelo_texto_com_nomes(self, base, client):
        r = await reuniao_agora(base, client)
        h = base["ev"]["headers"]
        s = (await abrir(client, r, h)).json()
        await client.post(
            f"/crm/agenda/ao-vivo/{s['id']}/falas",
            json={"falas": [fala(0, "vendedor", "bom dia"), fala(1, "cliente", "temos 120 vidas")]},
            headers=h,
        )
        entradas = [
            {"inicio": agora().isoformat(), "fim": None, "participante": "Test EV",
             "texto": "Bom dia, tudo bem?"},
            {"inicio": agora().isoformat(), "fim": None, "participante": "Cliente",
             "texto": "Temos 120 vidas."},
        ]
        await base["conn"].execute(
            """
            INSERT INTO reuniao_transcricoes (reuniao_id, status, entradas, texto, coletada_em)
            VALUES ($1, 'pronta', $2::jsonb, $3, NOW())
            """,
            UUID(r["id"]), json.dumps(entradas),
            "[09:00] Test EV: Bom dia, tudo bem?\n[09:01] Cliente: Temos 120 vidas.",
        )
        d = (await client.get(url(r), headers=h)).json()
        # 7 palavras nas falas do Meet (sem hora e sem nome); o ao vivo
        # perdeu "tudo bem".
        assert d["comparacao"] == {
            "palavras_meet": 7, "palavras_ao_vivo": 5, "cobertura_pct": 71,
        }

    async def test_meet_ainda_aguardando_nao_compara(self, base, client):
        r = await reuniao_agora(base, client)
        await base["conn"].execute(
            "INSERT INTO reuniao_transcricoes (reuniao_id, status) VALUES ($1, 'aguardando')",
            UUID(r["id"]),
        )
        d = (await client.get(url(r), headers=base["ev"]["headers"])).json()
        assert d["comparacao"] is None

    async def test_tarefa_que_nao_e_reuniao(self, base, client):
        resp = await client.get(f"/crm/agenda/tarefas/{uuid4()}/ao-vivo", headers=base["h"])
        assert resp.status_code == 404
