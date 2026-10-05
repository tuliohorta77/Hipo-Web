"""
HIPO — Universidade Corporativa: quiz depois da aula (024), com banco.

O que estes testes seguram:
  * estúdio: só a gestão escreve o quiz; 7 perguntas ou nenhuma; gabarito
    só aparece para a gestão
  * o gabarito nunca vai para quem aprende (varre o JSON inteiro)
  * aula com quiz não conclui pelo "Concluí"; o quiz só abre depois do
    tempo mínimo (as duas travas)
  * 6 de 7 aprova e conclui; 5 de 7 reprova, marca as erradas e segura a
    nova tentativa por 10 minutos
  * envio incompleto ou trocado é recusado sem gastar tentativa
  * quem concluiu antes do quiz existir continua concluído
  * a carga grava as 7 perguntas com ids fixos
"""
from __future__ import annotations

from uuid import UUID

from tests.test_uc import (
    _pdfs, destravar, estudar, nova_aula, nova_trilha, painel, publicar, s3_falso, time,  # noqa: F401
    trilha_publicada,
)


def quiz_valido(n: int = 7) -> list[dict]:
    return [
        {
            "enunciado": f"Pergunta {i}?",
            "alternativas": [
                {"texto": f"Certa {i}", "correta": True},
                {"texto": f"Errada {i}a", "correta": False},
                {"texto": f"Errada {i}b", "correta": False},
                {"texto": f"Errada {i}c", "correta": False},
            ],
        }
        for i in range(1, n + 1)
    ]


async def aula_com_quiz(client, time):
    g = time["g"]["headers"]
    _, (a1, a2) = await trilha_publicada(client, g)
    resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": quiz_valido()}, headers=g)
    assert resp.status_code == 200, resp.text
    return a1, a2


async def gabarito(conn, aula_id) -> dict[str, dict]:
    """{pergunta_id: {"certa": id, "errada": id}} lido do banco."""
    rows = await conn.fetch(
        """
        SELECT p.id AS pid, a.id AS aid, a.correta
          FROM uc_perguntas p JOIN uc_alternativas a ON a.pergunta_id = p.id
         WHERE p.aula_id = $1 ORDER BY p.ordem, a.ordem
        """,
        UUID(aula_id),
    )
    saida: dict[str, dict] = {}
    for r in rows:
        d = saida.setdefault(str(r["pid"]), {})
        d["certa" if r["correta"] else "errada"] = str(r["aid"])
    return saida


def respostas(gab: dict, erros: int) -> dict:
    out = {}
    for i, (pid, alts) in enumerate(gab.items()):
        out[pid] = alts["errada"] if i < erros else alts["certa"]
    return out


async def abrir_e_destravar(client, conn, u, aula_id):
    r = await client.get(f"/uc/aulas/{aula_id}", headers=u["headers"])
    assert r.status_code == 200, r.text
    await destravar(conn, u["id"], aula_id)


async def responder(client, u, aula_id, corpo):
    return await client.post(f"/uc/aulas/{aula_id}/quiz", json={"respostas": corpo}, headers=u["headers"])


def _tem_chave(obj, chave: str) -> bool:
    if isinstance(obj, dict):
        return chave in obj or any(_tem_chave(v, chave) for v in obj.values())
    if isinstance(obj, list):
        return any(_tem_chave(v, chave) for v in obj)
    return False


# ── Estúdio ──────────────────────────────────────────────────────────

class TestEstudioQuiz:
    async def test_gestao_grava_e_ve_o_gabarito(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        t = (await client.get(f"/uc/estudio/trilhas/{a1['trilha_id']}", headers=time["g"]["headers"])).json()
        aula = next(a for a in t["aulas"] if a["id"] == a1["id"])
        assert len(aula["quiz"]) == 7 and aula["nota_minima"] == 85
        assert aula["quiz"][0]["alternativas"][0] == {"texto": "Certa 1", "correta": True}

    async def test_quiz_precisa_de_sete_perguntas(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": quiz_valido(3)}, headers=g)
        assert resp.status_code == 422
        assert "precisa de exatamente 7" in resp.json()["detail"]

    async def test_pergunta_sem_correta_422(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        q = quiz_valido()
        q[4]["alternativas"][0]["correta"] = False
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": q}, headers=g)
        assert resp.status_code == 422
        assert "Pergunta 5" in resp.json()["detail"]

    async def test_lista_vazia_tira_o_quiz(self, time, client, db_conn):
        a1, _ = await aula_com_quiz(client, time)
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": []},
                                headers=time["g"]["headers"])
        assert resp.status_code == 200 and resp.json()["quiz"] == []
        assert await db_conn.fetchval("SELECT count(*) FROM uc_alternativas") == 0

    async def test_operacional_nao_escreve_quiz(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": []},
                                headers=time["ev"]["headers"])
        assert resp.status_code == 403


# ── Quem aprende ─────────────────────────────────────────────────────

class TestQuiz:
    async def test_gabarito_nunca_vai_para_quem_aprende(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        r = (await client.get(f"/uc/aulas/{a1['id']}", headers=time["ev"]["headers"])).json()
        quiz = r["quiz"]
        assert quiz["total"] == 7 and quiz["nota_minima"] == 85 and quiz["acertos_para_aprovar"] == 6
        assert [p["numero"] for p in quiz["perguntas"]] == list(range(1, 8))
        assert not _tem_chave(r, "correta")

    async def test_ordem_das_alternativas_nao_muda_no_f5(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        h = time["ev"]["headers"]
        r1 = (await client.get(f"/uc/aulas/{a1['id']}", headers=h)).json()["quiz"]
        r2 = (await client.get(f"/uc/aulas/{a1['id']}", headers=h)).json()["quiz"]
        assert r1["perguntas"] == r2["perguntas"]

    async def test_aula_sem_quiz_vem_com_quiz_nulo(self, time, client):
        _a1, a2 = await aula_com_quiz(client, time)
        r = (await client.get(f"/uc/aulas/{a2['id']}", headers=time["ev"]["headers"])).json()
        assert r["quiz"] is None

    async def test_concluir_aula_com_quiz_409(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev = time["ev"]
        await abrir_e_destravar(client, time["conn"], ev, a1["id"])
        resp = await client.post(f"/uc/aulas/{a1['id']}/concluir", headers=ev["headers"])
        assert resp.status_code == 409
        assert "conclui pelo quiz" in resp.json()["detail"]

    async def test_quiz_so_abre_depois_do_tempo_minimo(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev = time["ev"]
        await client.get(f"/uc/aulas/{a1['id']}", headers=ev["headers"])
        gab = await gabarito(time["conn"], a1["id"])
        resp = await responder(client, ev, a1["id"], respostas(gab, 0))
        assert resp.status_code == 409
        assert "O quiz abre em 5 min" in resp.json()["detail"]
        assert await time["conn"].fetchval("SELECT count(*) FROM uc_tentativas") == 0

    async def test_seis_de_sete_aprova_e_conclui(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev = time["ev"]
        await abrir_e_destravar(client, time["conn"], ev, a1["id"])
        gab = await gabarito(time["conn"], a1["id"])
        resp = await responder(client, ev, a1["id"], respostas(gab, 1))
        assert resp.status_code == 200, resp.text
        r = resp.json()
        assert r["concluida_em"] is not None
        assert r["quiz"]["aprovado"] is True
        assert (r["quiz"]["ultima"]["acertos"], r["quiz"]["ultima"]["nota"]) == (6, 85)
        p = await painel(client, ev)
        assert p["outras"][0]["aulas_concluidas"] == 1
        # Concluída: não há o que refazer.
        again = await responder(client, ev, a1["id"], respostas(gab, 0))
        assert again.status_code == 409 and "já concluída" in again.json()["detail"]

    async def test_cinco_de_sete_reprova_marca_erradas_e_segura_dez_minutos(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await abrir_e_destravar(client, conn, ev, a1["id"])
        gab = await gabarito(conn, a1["id"])
        resp = await responder(client, ev, a1["id"], respostas(gab, 2))
        assert resp.status_code == 200
        r = resp.json()
        assert r["concluida_em"] is None
        ultima = r["quiz"]["ultima"]
        assert (ultima["acertos"], ultima["nota"], ultima["aprovada"]) == (5, 71, False)
        assert ultima["erradas"] == list(gab)[:2]
        assert 590 <= r["quiz"]["segundos_para_refazer"] <= 600
        assert not _tem_chave(r, "correta")

        cedo = await responder(client, ev, a1["id"], respostas(gab, 0))
        assert cedo.status_code == 429
        assert "Nova tentativa em 10 min" in cedo.json()["detail"]

        await conn.execute("UPDATE uc_tentativas SET criado_em = criado_em - interval '11 minutes'")
        depois = await responder(client, ev, a1["id"], respostas(gab, 0))
        assert depois.status_code == 200
        assert depois.json()["concluida_em"] is not None
        assert depois.json()["quiz"]["tentativas"] == 2

    async def test_envio_incompleto_nao_gasta_tentativa(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await abrir_e_destravar(client, conn, ev, a1["id"])
        gab = await gabarito(conn, a1["id"])
        corpo = respostas(gab, 0)
        corpo.pop(list(gab)[6])
        resp = await responder(client, ev, a1["id"], corpo)
        assert resp.status_code == 422
        assert "falta: 7" in resp.json()["detail"]
        assert await conn.fetchval("SELECT count(*) FROM uc_tentativas") == 0

    async def test_alternativa_de_outra_pergunta_422(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await abrir_e_destravar(client, conn, ev, a1["id"])
        gab = await gabarito(conn, a1["id"])
        pids = list(gab)
        corpo = respostas(gab, 0)
        corpo[pids[0]] = gab[pids[1]]["certa"]
        resp = await responder(client, ev, a1["id"], corpo)
        assert resp.status_code == 422
        assert await conn.fetchval("SELECT count(*) FROM uc_tentativas") == 0

    async def test_aula_sem_quiz_recusa_envio(self, time, client):
        _a1, a2 = await aula_com_quiz(client, time)
        resp = await responder(client, time["ev"], a2["id"], {})
        assert resp.status_code == 409

    async def test_quem_concluiu_antes_do_quiz_continua_concluido(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        await estudar(client, time["conn"], time["ev"], a1["id"])
        await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": quiz_valido()}, headers=g)
        r = (await client.get(f"/uc/aulas/{a1['id']}", headers=time["ev"]["headers"])).json()
        assert r["concluida_em"] is not None
        resp = await client.post(f"/uc/aulas/{a1['id']}/concluir", headers=time["ev"]["headers"])
        assert resp.status_code == 200

    async def test_gestao_ve_o_resultado_em_modo_leitura_sem_gravar(self, time, client):
        a1, _ = await aula_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await abrir_e_destravar(client, conn, ev, a1["id"])
        gab = await gabarito(conn, a1["id"])
        await responder(client, ev, a1["id"], respostas(gab, 3))
        r = (await client.get(f"/uc/aulas/{a1['id']}", params={"usuario_id": ev["id"]},
                              headers=time["g"]["headers"])).json()
        assert r["modo_leitura"] is True
        assert r["quiz"]["ultima"]["acertos"] == 4
        assert not _tem_chave(r, "correta")


# ── Carga ────────────────────────────────────────────────────────────

class TestCargaQuiz:
    async def test_carga_grava_sete_perguntas_com_ids_fixos(self, time, client, s3_falso, tmp_path):
        from scripts import semear_uc
        from scripts.uc_conteudo import TRILHA_01, TRILHAS
        conn = time["conn"]
        await semear_uc.carregar(conn, _pdfs(tmp_path), atualizar=True, simular=False)
        ids1 = {r["id"] for r in await conn.fetch("SELECT id FROM uc_perguntas")}
        await semear_uc.carregar(conn, _pdfs(tmp_path), atualizar=True, simular=False)
        ids2 = {r["id"] for r in await conn.fetch("SELECT id FROM uc_perguntas")}
        total_aulas = sum(len(t["aulas"]) for t in TRILHAS)
        assert ids1 == ids2 and len(ids1) == 7 * total_aulas
        assert await conn.fetchval("SELECT count(*) FROM uc_alternativas WHERE correta") == 7 * total_aulas
        assert await conn.fetchval("SELECT min(nota_minima) FROM uc_aulas") == 85
        aula = TRILHA_01["aulas"][0]
        r = (await client.get(f"/uc/aulas/{aula['id']}", headers=time["ev"]["headers"])).json()
        assert [p["enunciado"] for p in r["quiz"]["perguntas"]] == [q["enunciado"] for q in aula["quiz"]]
