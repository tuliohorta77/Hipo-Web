"""
HIPO — Universidade Corporativa: rotas, com banco.

As regras puras estão em test_uc_regras.py. Aqui a costura:

  * estúdio: só gestão escreve; trilha não publica vazia; vídeo vira par
  * manual da função: quem vê qual trilha, prazo, `desde` preservado
  * aula: abrir grava a abertura, a trava de tempo vale no servidor,
    concluir é idempotente, versão nova reabre a pendência
  * modo leitura da gestão não grava nada
  * materiais com o S3 dublado
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from services import uc_material
from tests.conftest import criar_usuario


# ── Cenário ──────────────────────────────────────────────────────────

async def _me(client, u):
    u["id"] = (await client.get("/auth/me", headers=u["headers"])).json()["id"]
    return u


@pytest.fixture
async def time(db_conn, client, usuario_franqueado):
    ev = await _me(client, await criar_usuario(db_conn, client, "EV", "ev-uc@teste.com"))
    sdr = await _me(client, await criar_usuario(db_conn, client, "SDR", "sdr-uc@teste.com"))
    gestao = await _me(client, usuario_franqueado)
    return {"g": gestao, "ev": ev, "sdr": sdr, "conn": db_conn}


async def nova_trilha(client, h, **extra):
    corpo = {"titulo": "Normas Regulamentadoras", "pilar": "tecnica", **extra}
    resp = await client.post("/uc/estudio/trilhas", json=corpo, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_aula(client, h, trilha_id, **extra):
    corpo = {"titulo": "NR-01", "duracao_min": 10, **extra}
    resp = await client.post(f"/uc/estudio/trilhas/{trilha_id}/aulas", json=corpo, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def publicar(client, h, trilha_id):
    resp = await client.patch(
        f"/uc/estudio/trilhas/{trilha_id}", json={"status": "publicada"}, headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def cargos(client, h, trilha_id, lista):
    resp = await client.put(
        f"/uc/estudio/trilhas/{trilha_id}/cargos", json={"cargos": lista}, headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def trilha_publicada(client, h, *, aulas=2, cargos_lista=None, **extra):
    t = await nova_trilha(client, h, **extra)
    criadas = [await nova_aula(client, h, t["id"], titulo=f"Aula {i}") for i in range(1, aulas + 1)]
    if cargos_lista is not None:
        await cargos(client, h, t["id"], cargos_lista)
    await publicar(client, h, t["id"])
    return t, criadas


async def painel(client, u, **params):
    resp = await client.get("/uc/painel", params=params, headers=u["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()


async def destravar(conn, usuario_id, aula_id, minutos=60):
    """Leva a abertura para o passado, como se a pessoa tivesse estudado."""
    await conn.execute(
        """
        UPDATE uc_progresso SET aberta_em = aberta_em - make_interval(mins => $3)
         WHERE usuario_id = $1 AND aula_id = $2
        """,
        UUID(usuario_id), UUID(aula_id), minutos,
    )


async def estudar(client, conn, u, aula_id):
    assert (await client.get(f"/uc/aulas/{aula_id}", headers=u["headers"])).status_code == 200
    await destravar(conn, u["id"], aula_id)
    resp = await client.post(f"/uc/aulas/{aula_id}/concluir", headers=u["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Estúdio: permissão e publicação ──────────────────────────────────

class TestEstudio:
    async def test_trilha_nasce_em_rascunho(self, time, client):
        t = await nova_trilha(client, time["g"]["headers"])
        assert t["status"] == "rascunho"
        assert t["pilar_rotulo"] == "Técnica"
        assert t["aulas"] == []

    async def test_operacional_nao_escreve_no_estudio(self, time, client):
        h = time["ev"]["headers"]
        resp = await client.post(
            "/uc/estudio/trilhas", json={"titulo": "X", "pilar": "tecnica"}, headers=h,
        )
        assert resp.status_code == 403
        assert "gestão" in resp.json()["detail"]
        assert (await client.get("/uc/estudio/trilhas", headers=h)).status_code == 403
        assert (await client.get("/uc/estudio/time", headers=h)).status_code == 403

    async def test_conta_de_tv_nao_entra_na_uc(self, time, client, db_conn):
        tv = await criar_usuario(db_conn, client, "Monitor", "tv-uc@teste.com")
        assert (await client.get("/uc/painel", headers=tv["headers"])).status_code == 403

    async def test_trilha_vazia_nao_publica(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        resp = await client.patch(f"/uc/estudio/trilhas/{t['id']}", json={"status": "publicada"}, headers=h)
        assert resp.status_code == 422
        assert "vazia" in resp.json()["detail"]

    async def test_trilha_com_aula_so_em_rascunho_nao_publica(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        await nova_aula(client, h, t["id"], status="rascunho")
        resp = await client.patch(f"/uc/estudio/trilhas/{t['id']}", json={"status": "publicada"}, headers=h)
        assert resp.status_code == 422

    async def test_pilar_invalido_422_em_portugues(self, time, client):
        resp = await client.post(
            "/uc/estudio/trilhas", json={"titulo": "X", "pilar": "vendas"},
            headers=time["g"]["headers"],
        )
        assert resp.status_code == 422
        assert "Pilar inválido" in resp.json()["detail"]

    async def test_aulas_numeradas_em_sequencia(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        a1 = await nova_aula(client, h, t["id"])
        a2 = await nova_aula(client, h, t["id"])
        assert (a1["ordem"], a2["ordem"]) == (1, 2)

    async def test_video_vira_provedor_e_id(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        a = await nova_aula(client, h, t["id"], video_url="https://youtu.be/dQw4w9WgXcQ")
        assert (a["video_provedor"], a["video_ref"]) == ("youtube", "dQw4w9WgXcQ")
        assert a["video_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    async def test_video_de_site_desconhecido_422(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        resp = await client.post(
            f"/uc/estudio/trilhas/{t['id']}/aulas",
            json={"titulo": "X", "video_url": "https://evil.com/x.mp4"}, headers=h,
        )
        assert resp.status_code == 422
        assert "Aceitos" in resp.json()["detail"]

    async def test_tirar_o_video_com_link_vazio(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        a = await nova_aula(client, h, t["id"], video_url="https://vimeo.com/76979871")
        resp = await client.patch(f"/uc/estudio/aulas/{a['id']}", json={"video_url": ""}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["video_provedor"] is None

    async def test_reordenar_exige_todas_as_aulas(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        a1 = await nova_aula(client, h, t["id"], titulo="Um")
        a2 = await nova_aula(client, h, t["id"], titulo="Dois")
        url = f"/uc/estudio/trilhas/{t['id']}/ordem"
        assert (await client.put(url, json={"aulas": [a1["id"]]}, headers=h)).status_code == 422
        resp = await client.put(url, json={"aulas": [a2["id"], a1["id"]]}, headers=h)
        assert resp.status_code == 200
        assert [a["titulo"] for a in resp.json()["aulas"]] == ["Dois", "Um"]

    async def test_ultima_aula_publicada_nao_volta_a_rascunho(self, time, client):
        h = time["g"]["headers"]
        t, (a1,) = await trilha_publicada(client, h, aulas=1)
        resp = await client.patch(f"/uc/estudio/aulas/{a1['id']}", json={"status": "rascunho"}, headers=h)
        assert resp.status_code == 422
        assert "última aula publicada" in resp.json()["detail"]

    async def test_cargo_repetido_ou_invalido_422(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        url = f"/uc/estudio/trilhas/{t['id']}/cargos"
        r1 = await client.put(url, json={"cargos": [{"cargo": "EV"}, {"cargo": "EV"}]}, headers=h)
        r2 = await client.put(url, json={"cargos": [{"cargo": "Monitor"}]}, headers=h)
        assert (r1.status_code, r2.status_code) == (422, 422)

    async def test_vocabulario_vem_do_servidor(self, time, client):
        resp = await client.get("/uc/estudio/vocabulario", headers=time["g"]["headers"])
        corpo = resp.json()
        assert corpo["pilares"]["metodo"] == "Método"
        assert "Monitor" not in corpo["cargos"]


# ── Quem vê o quê ────────────────────────────────────────────────────

class TestVisibilidade:
    async def test_rascunho_nao_aparece_para_ninguem_na_tela_de_aprender(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        await nova_aula(client, h, t["id"])
        p = await painel(client, time["ev"])
        assert p["manual"]["trilhas"] == [] and p["outras"] == []
        assert (await client.get(f"/uc/trilhas/{t['id']}", headers=time["ev"]["headers"])).status_code == 404

    async def test_gestao_confere_rascunho_antes_de_publicar(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        await nova_aula(client, h, t["id"], status="rascunho")
        resp = await client.get(f"/uc/trilhas/{t['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "rascunho"
        assert len(resp.json()["aulas"]) == 1

    async def test_trilha_sem_cargo_e_aberta_a_todos(self, time, client):
        t, _ = await trilha_publicada(client, time["g"]["headers"])
        for u in (time["ev"], time["sdr"]):
            p = await painel(client, u)
            assert [x["id"] for x in p["outras"]] == [t["id"]]
            assert p["manual"]["trilhas"] == []

    async def test_trilha_do_cargo_so_para_o_cargo(self, time, client):
        t, _ = await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        p_ev = await painel(client, time["ev"])
        p_sdr = await painel(client, time["sdr"])
        assert [x["id"] for x in p_ev["manual"]["trilhas"]] == [t["id"]]
        assert p_sdr["manual"]["trilhas"] == [] and p_sdr["outras"] == []
        assert (await client.get(f"/uc/trilhas/{t['id']}", headers=time["sdr"]["headers"])).status_code == 404

    async def test_trilha_opcional_do_cargo_vai_para_outras(self, time, client):
        t, _ = await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": False, "prazo_dias": 30}],
        )
        p = await painel(client, time["ev"])
        assert [x["id"] for x in p["outras"]] == [t["id"]]
        # Opcional não tem prazo, mesmo que alguém tenha mandado um.
        assert p["outras"][0]["prazo"] is None

    async def test_arquivada_some(self, time, client):
        h = time["g"]["headers"]
        t, _ = await trilha_publicada(client, h)
        await client.patch(f"/uc/estudio/trilhas/{t['id']}", json={"status": "arquivada"}, headers=h)
        p = await painel(client, time["ev"])
        assert p["outras"] == []


# ── Manual da função e prazo ─────────────────────────────────────────

class TestManual:
    async def test_prazo_conta_de_quando_virou_obrigatoria(self, time, client):
        """Quem já estava na equipe não recebe a trilha nascida atrasada."""
        await time["conn"].execute(
            "UPDATE usuarios SET created_at = NOW() - interval '400 days' WHERE id = $1",
            UUID(time["ev"]["id"]),
        )
        await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        p = await painel(client, time["ev"])
        trilha = p["manual"]["trilhas"][0]
        assert trilha["situacao"]["codigo"] == "em_dia"
        assert date.fromisoformat(trilha["prazo"]) >= date.today() + timedelta(days=29)

    async def test_atrasada_quando_o_prazo_passa(self, time, client):
        await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 10}],
        )
        p = await painel(client, time["ev"], hoje=(date.today() + timedelta(days=40)).isoformat())
        assert p["manual"]["atrasadas"] == 1
        assert p["proxima"]["motivo"] == "atrasada"

    async def test_desde_sobrevive_a_edicao_da_lista(self, time, client):
        h = time["g"]["headers"]
        await time["conn"].execute(
            "UPDATE usuarios SET created_at = NOW() - interval '400 days' WHERE id = $1",
            UUID(time["ev"]["id"]),
        )
        t, _ = await trilha_publicada(
            client, h, cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 10}],
        )
        await time["conn"].execute(
            "UPDATE uc_trilha_cargos SET desde = NOW() - interval '60 days' WHERE trilha_id = $1",
            UUID(t["id"]),
        )
        depois = await cargos(client, h, t["id"], [
            {"cargo": "EV", "obrigatoria": True, "prazo_dias": 10},
            {"cargo": "SDR", "obrigatoria": True, "prazo_dias": 10},
        ])
        desde = {c["cargo"]: c["desde"][:10] for c in depois["cargos"]}
        assert desde["EV"] != desde["SDR"]
        p = await painel(client, time["ev"])
        assert p["manual"]["trilhas"][0]["situacao"]["codigo"] == "atrasada"

    async def test_proxima_aula_e_a_primeira_da_obrigatoria(self, time, client):
        t, aulas = await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        p = await painel(client, time["ev"])
        assert p["proxima"]["aula_id"] == aulas[0]["id"]
        assert p["proxima"]["motivo"] == "obrigatoria"
        assert p["proxima"]["motivo_texto"] == "Do manual da sua função"


# ── Aula: abrir, travar, concluir ────────────────────────────────────

class TestAula:
    async def test_abrir_grava_a_abertura_uma_vez(self, time, client):
        _, (a1, _a2) = await trilha_publicada(client, time["g"]["headers"])
        h = time["ev"]["headers"]
        r1 = (await client.get(f"/uc/aulas/{a1['id']}", headers=h)).json()
        r2 = (await client.get(f"/uc/aulas/{a1['id']}", headers=h)).json()
        assert r1["aberta_em"] == r2["aberta_em"] is not None
        assert r1["segundos_para_liberar"] > 0
        assert r1["proxima"]["titulo"] == "Aula 2" and r1["anterior"] is None

    async def test_concluir_antes_do_tempo_409_dizendo_quanto_falta(self, time, client):
        _, (a1, _a2) = await trilha_publicada(client, time["g"]["headers"])
        h = time["ev"]["headers"]
        await client.get(f"/uc/aulas/{a1['id']}", headers=h)
        resp = await client.post(f"/uc/aulas/{a1['id']}/concluir", headers=h)
        assert resp.status_code == 409
        assert "faltam 5 min" in resp.json()["detail"]

    async def test_concluir_sem_ter_aberto_tambem_trava(self, time, client):
        _, (a1, _a2) = await trilha_publicada(client, time["g"]["headers"])
        resp = await client.post(f"/uc/aulas/{a1['id']}/concluir", headers=time["ev"]["headers"])
        assert resp.status_code == 409

    async def test_aula_sem_duracao_conclui_na_hora(self, time, client):
        h = time["g"]["headers"]
        t = await nova_trilha(client, h)
        a = await nova_aula(client, h, t["id"], duracao_min=None)
        await publicar(client, h, t["id"])
        resp = await client.post(f"/uc/aulas/{a['id']}/concluir", headers=time["ev"]["headers"])
        assert resp.status_code == 200
        assert resp.json()["concluida_em"] is not None

    async def test_concluir_e_idempotente_e_atualiza_o_painel(self, time, client):
        _, (a1, _a2) = await trilha_publicada(client, time["g"]["headers"])
        ev = time["ev"]
        primeira = await estudar(client, time["conn"], ev, a1["id"])
        segunda = (await client.post(f"/uc/aulas/{a1['id']}/concluir", headers=ev["headers"])).json()
        assert primeira["concluida_em"] == segunda["concluida_em"]
        p = await painel(client, ev)
        trilha = p["outras"][0]
        assert (trilha["aulas_concluidas"], trilha["percentual"]) == (1, 50)
        tecnica = next(x for x in p["pilares"] if x["pilar"] == "tecnica")
        assert tecnica["percentual"] == 50
        assert p["proxima"]["aula_titulo"] == "Aula 2"
        assert p["proxima"]["motivo"] == "em_andamento"

    async def test_trilha_completa_fica_concluida_e_sem_proxima(self, time, client):
        _, aulas = await trilha_publicada(
            client, time["g"]["headers"], aulas=1,
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        await estudar(client, time["conn"], time["ev"], aulas[0]["id"])
        p = await painel(client, time["ev"])
        assert p["manual"]["trilhas_concluidas"] == 1
        assert p["manual"]["trilhas"][0]["situacao"]["codigo"] == "concluida"
        assert p["proxima"] is None

    async def test_mudanca_relevante_reabre_para_quem_concluiu(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        await estudar(client, time["conn"], time["ev"], a1["id"])
        resp = await client.patch(
            f"/uc/estudio/aulas/{a1['id']}",
            json={"conteudo_md": "Texto novo", "mudanca_relevante": True}, headers=g,
        )
        assert resp.json()["versao"] == 2
        p = await painel(client, time["ev"])
        assert p["outras"][0]["aulas_concluidas"] == 0
        assert (p["proxima"]["aula_id"], p["proxima"]["motivo"]) == (a1["id"], "atualizada")
        aula = (await client.get(f"/uc/aulas/{a1['id']}", headers=time["ev"]["headers"])).json()
        assert aula["concluiu_versao_anterior"] is True and aula["concluida_em"] is None

    async def test_correcao_sem_mudanca_relevante_nao_reabre(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        await estudar(client, time["conn"], time["ev"], a1["id"])
        await client.patch(f"/uc/estudio/aulas/{a1['id']}", json={"titulo": "Aula 1."}, headers=g)
        p = await painel(client, time["ev"])
        assert p["outras"][0]["aulas_concluidas"] == 1

    async def test_aula_em_rascunho_nao_abre_para_quem_aprende(self, time, client):
        g = time["g"]["headers"]
        t, _ = await trilha_publicada(client, g)
        rasc = await nova_aula(client, g, t["id"], status="rascunho")
        assert (await client.get(f"/uc/aulas/{rasc['id']}", headers=time["ev"]["headers"])).status_code == 404
        trilha = (await client.get(f"/uc/trilhas/{t['id']}", headers=time["ev"]["headers"])).json()
        assert rasc["id"] not in [a["id"] for a in trilha["aulas"]]

    async def test_aula_inexistente_404(self, time, client):
        resp = await client.get(f"/uc/aulas/{uuid4()}", headers=time["ev"]["headers"])
        assert resp.status_code == 404

    async def test_aula_concluida_nao_se_apaga(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        await estudar(client, time["conn"], time["ev"], a1["id"])
        resp = await client.delete(f"/uc/estudio/aulas/{a1['id']}", headers=g)
        assert resp.status_code == 409
        assert "rascunho" in resp.json()["detail"]

    async def test_apagar_aula_fecha_o_buraco_da_ordem(self, time, client):
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a1 = await nova_aula(client, g, t["id"], titulo="Um")
        await nova_aula(client, g, t["id"], titulo="Dois")
        assert (await client.delete(f"/uc/estudio/aulas/{a1['id']}", headers=g)).status_code == 204
        detalhe = (await client.get(f"/uc/estudio/trilhas/{t['id']}", headers=g)).json()
        assert [(a["ordem"], a["titulo"]) for a in detalhe["aulas"]] == [(1, "Dois")]


# ── Modo leitura ─────────────────────────────────────────────────────

class TestModoLeitura:
    async def test_gestao_ve_a_uc_de_alguem_sem_gravar_nada(self, time, client):
        _, (a1, _a2) = await trilha_publicada(
            client, time["g"]["headers"],
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        p = await painel(client, time["g"], usuario_id=time["ev"]["id"])
        assert p["modo_leitura"] is True
        assert p["usuario"]["cargo"] == "EV"
        assert len(p["manual"]["trilhas"]) == 1
        resp = await client.get(
            f"/uc/aulas/{a1['id']}", params={"usuario_id": time["ev"]["id"]},
            headers=time["g"]["headers"],
        )
        assert resp.json()["modo_leitura"] is True
        gravados = await time["conn"].fetchval("SELECT count(*) FROM uc_progresso")
        assert gravados == 0

    async def test_operacional_nao_abre_a_uc_do_colega(self, time, client):
        resp = await client.get(
            "/uc/painel", params={"usuario_id": time["sdr"]["id"]}, headers=time["ev"]["headers"],
        )
        assert resp.status_code == 403

    async def test_pedir_a_propria_uc_por_id_nao_e_modo_leitura(self, time, client):
        p = await painel(client, time["ev"], usuario_id=time["ev"]["id"])
        assert p["modo_leitura"] is False

    async def test_time_lista_o_manual_de_cada_um(self, time, client):
        _, aulas = await trilha_publicada(
            client, time["g"]["headers"], aulas=1,
            cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        await estudar(client, time["conn"], time["ev"], aulas[0]["id"])
        linhas = (await client.get("/uc/estudio/time", headers=time["g"]["headers"])).json()
        por_nome = {l["cargo"]: l for l in linhas}
        assert por_nome["EV"]["obrigatorias_concluidas"] == 1
        assert por_nome["SDR"]["obrigatorias"] == 0


# ── Materiais (S3 dublado) ───────────────────────────────────────────

@pytest.fixture
def s3_falso(monkeypatch):
    guardados: dict[str, bytes] = {}
    monkeypatch.setattr(uc_material, "problemas", lambda: [])
    monkeypatch.setattr(uc_material, "subir", lambda chave, conteudo, tipo: guardados.__setitem__(chave, conteudo))
    monkeypatch.setattr(uc_material, "remover", lambda chave: guardados.pop(chave, None))
    monkeypatch.setattr(uc_material, "url_temporaria", lambda chave, nome=None: f"https://s3.teste/{chave}")
    return guardados


class TestMateriais:
    async def test_upload_de_pdf_e_link_assinado(self, time, client, s3_falso):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        resp = await client.post(
            f"/uc/estudio/aulas/{a1['id']}/materiais",
            files={"arquivo": ("NR-01 atualizada.pdf", b"%PDF-1.4 teste", "application/pdf")},
            headers=g,
        )
        assert resp.status_code == 201, resp.text
        mat = resp.json()
        assert mat["nome_original"] == "NR-01-atualizada.pdf"
        [chave] = s3_falso
        assert chave.startswith(f"uc/aulas/{a1['id']}/") and chave.endswith(".pdf")

        aula = (await client.get(f"/uc/aulas/{a1['id']}", headers=time["ev"]["headers"])).json()
        assert [m["id"] for m in aula["materiais"]] == [mat["id"]]
        link = await client.get(f"/uc/materiais/{mat['id']}/url", headers=time["ev"]["headers"])
        assert link.json()["url"] == f"https://s3.teste/{chave}"

    async def test_video_como_arquivo_422(self, time, client, s3_falso):
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a = await nova_aula(client, g, t["id"])
        resp = await client.post(
            f"/uc/estudio/aulas/{a['id']}/materiais",
            files={"arquivo": ("aula.mp4", b"0000", "video/mp4")}, headers=g,
        )
        assert resp.status_code == 422
        assert "link" in resp.json()["detail"]
        assert s3_falso == {}

    async def test_operacional_nao_sobe_material(self, time, client, s3_falso):
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a = await nova_aula(client, g, t["id"])
        resp = await client.post(
            f"/uc/estudio/aulas/{a['id']}/materiais",
            files={"arquivo": ("x.pdf", b"%PDF", "application/pdf")},
            headers=time["ev"]["headers"],
        )
        assert resp.status_code == 403

    async def test_material_de_trilha_invisivel_nao_assina(self, time, client, s3_falso):
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a = await nova_aula(client, g, t["id"])
        mat = (await client.post(
            f"/uc/estudio/aulas/{a['id']}/materiais",
            files={"arquivo": ("x.pdf", b"%PDF", "application/pdf")}, headers=g,
        )).json()
        resp = await client.get(f"/uc/materiais/{mat['id']}/url", headers=time["ev"]["headers"])
        assert resp.status_code == 404

    async def test_remover_tira_do_banco_e_do_bucket(self, time, client, s3_falso):
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a = await nova_aula(client, g, t["id"])
        mat = (await client.post(
            f"/uc/estudio/aulas/{a['id']}/materiais",
            files={"arquivo": ("x.pdf", b"%PDF", "application/pdf")}, headers=g,
        )).json()
        assert (await client.delete(f"/uc/estudio/materiais/{mat['id']}", headers=g)).status_code == 204
        assert s3_falso == {}

    async def test_sem_bucket_503_dizendo_o_que_falta(self, time, client, monkeypatch):
        monkeypatch.setattr(uc_material, "problemas", lambda: ["S3_BUCKET_ANEXOS não configurado"])
        g = time["g"]["headers"]
        t = await nova_trilha(client, g)
        a = await nova_aula(client, g, t["id"])
        resp = await client.post(
            f"/uc/estudio/aulas/{a['id']}/materiais",
            files={"arquivo": ("x.pdf", b"%PDF", "application/pdf")}, headers=g,
        )
        assert resp.status_code == 503
        assert "S3_BUCKET_ANEXOS" in resp.json()["detail"]


# ── Carga da trilha de NR (scripts/semear_uc_nr.py) ──────────────────

class TestCargaNr:
    async def test_carga_publica_e_entra_no_manual(self, time, client, s3_falso, tmp_path):
        from scripts import semear_uc_nr as nr
        pdf = tmp_path / "nr01.pdf"
        pdf.write_bytes(b"%PDF-1.4 norma")
        await nr._carregar(time["conn"], {"nr01": pdf}, atualizar=False, simular=False)
        p = await painel(client, time["ev"])
        [trilha] = p["manual"]["trilhas"]
        assert trilha["titulo"] == nr.TRILHA["titulo"]
        assert trilha["aulas_total"] == 6
        assert p["proxima"]["aula_titulo"] == nr.AULAS[0]["titulo"]
        aula = (await client.get(f"/uc/aulas/{nr.AULAS[0]['id']}", headers=time["ev"]["headers"])).json()
        assert [m["nome_original"] for m in aula["materiais"]] == ["NR-01-texto-oficial-atualizado-2025.pdf"]

    async def test_carga_de_novo_nao_duplica(self, time, client, s3_falso, tmp_path):
        from scripts import semear_uc_nr as nr
        pdf = tmp_path / "nr01.pdf"
        pdf.write_bytes(b"%PDF-1.4 norma")
        for _ in range(2):
            await nr._carregar(time["conn"], {"nr01": pdf}, atualizar=True, simular=False)
        assert await time["conn"].fetchval("SELECT count(*) FROM uc_aulas") == 6
        assert await time["conn"].fetchval("SELECT count(*) FROM uc_materiais") == 1
        assert len(s3_falso) == 1

    async def test_simular_nao_grava(self, time, client, s3_falso):
        from scripts import semear_uc_nr as nr
        await nr._carregar(time["conn"], {}, atualizar=False, simular=True)
        assert await time["conn"].fetchval("SELECT count(*) FROM uc_trilhas") == 0
