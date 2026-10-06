"""
HIPO — Universidade Corporativa: quiz FINAL DA TRILHA (024 + 025), com banco.

O que estes testes seguram:
  * estúdio: só a gestão escreve o banco de perguntas da aula (0 a 10);
    gabarito só aparece para a gestão
  * as aulas concluem pela trava de tempo, com ou sem perguntas
  * o quiz final só abre com todas as aulas concluídas; sorteia 10 do
    banco das aulas; o gabarito nunca vai para quem aprende
  * 9 de 10 aprova e conclui a trilha; 8 de 10 reprova, diz quais
    perguntas e de qual aula, e segura a nova tentativa por 10 minutos,
    que vem com outro sorteio
  * envio incompleto, trocado ou de sorteio antigo é recusado sem gastar
    tentativa
  * a trilha só fica "Concluída" (e a próxima aula vira o quiz) pelo quiz
  * a carga grava as 7 perguntas de cada aula com ids fixos
"""
from __future__ import annotations

from uuid import UUID

from tests.test_uc import (
    _pdfs, destravar, estudar, painel, s3_falso, time,  # noqa: F401
    trilha_publicada,
)


def banco(n: int = 7, prefixo: str = "") -> list[dict]:
    return [
        {
            "enunciado": f"{prefixo}Pergunta {i}?",
            "alternativas": [
                {"texto": f"Certa {i}", "correta": True},
                {"texto": f"Errada {i}a", "correta": False},
                {"texto": f"Errada {i}b", "correta": False},
                {"texto": f"Errada {i}c", "correta": False},
            ],
        }
        for i in range(1, n + 1)
    ]


async def trilha_com_quiz(client, time, aulas=2, cargos_lista=None):
    """Trilha publicada com 7 perguntas em cada aula (14 no banco: sorteia 10)."""
    g = time["g"]["headers"]
    t, criadas = await trilha_publicada(client, g, aulas=aulas, cargos_lista=cargos_lista)
    for i, a in enumerate(criadas, start=1):
        resp = await client.put(f"/uc/estudio/aulas/{a['id']}/quiz",
                                json={"perguntas": banco(7, f"A{i} ")}, headers=g)
        assert resp.status_code == 200, resp.text
    return t, criadas


async def concluir_aulas(client, conn, u, aulas):
    for a in aulas:
        await estudar(client, conn, u, a["id"])


async def gabarito(conn) -> dict[str, dict]:
    rows = await conn.fetch(
        """
        SELECT p.id AS pid, a.id AS aid, a.correta
          FROM uc_perguntas p JOIN uc_alternativas a ON a.pergunta_id = p.id
        """,
    )
    saida: dict[str, dict] = {}
    for r in rows:
        saida.setdefault(str(r["pid"]), {})["certa" if r["correta"] else "errada"] = str(r["aid"])
    return saida


def respostas(quiz: dict, gab: dict, erros: int) -> dict:
    out = {}
    for i, p in enumerate(quiz["perguntas"]):
        alts = gab[p["id"]]
        out[p["id"]] = alts["errada"] if i < erros else alts["certa"]
    return out


async def abrir_quiz(client, u, trilha_id, **params):
    r = await client.get(f"/uc/trilhas/{trilha_id}/quiz", params=params, headers=u["headers"])
    assert r.status_code == 200, r.text
    return r.json()


async def responder(client, u, trilha_id, corpo):
    return await client.post(f"/uc/trilhas/{trilha_id}/quiz", json={"respostas": corpo}, headers=u["headers"])


def _tem_chave(obj, chave: str) -> bool:
    if isinstance(obj, dict):
        return chave in obj or any(_tem_chave(v, chave) for v in obj.values())
    if isinstance(obj, list):
        return any(_tem_chave(v, chave) for v in obj)
    return False


# ── Estúdio ──────────────────────────────────────────────────────────

class TestEstudioBanco:
    async def test_gestao_grava_e_ve_o_gabarito(self, time, client):
        t, (a1, _a2) = await trilha_com_quiz(client, time)
        d = (await client.get(f"/uc/estudio/trilhas/{t['id']}", headers=time["g"]["headers"])).json()
        aula = next(a for a in d["aulas"] if a["id"] == a1["id"])
        assert len(aula["quiz"]) == 7
        assert aula["quiz"][0]["alternativas"][0] == {"texto": "Certa 1", "correta": True}

    async def test_banco_vai_ate_dez(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        ok = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": banco(3)}, headers=g)
        assert ok.status_code == 200 and len(ok.json()["quiz"]) == 3
        demais = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": banco(11)}, headers=g)
        assert demais.status_code == 422 and "vai até 10" in demais.json()["detail"]

    async def test_pergunta_sem_correta_422(self, time, client):
        g = time["g"]["headers"]
        _, (a1, _a2) = await trilha_publicada(client, g)
        q = banco()
        q[4]["alternativas"][0]["correta"] = False
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": q}, headers=g)
        assert resp.status_code == 422 and "Pergunta 5" in resp.json()["detail"]

    async def test_lista_vazia_tira_do_banco(self, time, client, db_conn):
        _, (a1, _a2) = await trilha_com_quiz(client, time)
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": []},
                                headers=time["g"]["headers"])
        assert resp.status_code == 200 and resp.json()["quiz"] == []
        assert await db_conn.fetchval("SELECT count(*) FROM uc_perguntas") == 7

    async def test_operacional_nao_escreve(self, time, client):
        _, (a1, _a2) = await trilha_com_quiz(client, time)
        resp = await client.put(f"/uc/estudio/aulas/{a1['id']}/quiz", json={"perguntas": []},
                                headers=time["ev"]["headers"])
        assert resp.status_code == 403


# ── Aula e trilha ────────────────────────────────────────────────────

class TestAulaComBanco:
    async def test_aula_com_perguntas_conclui_pelo_tempo(self, time, client):
        _, (a1, _a2) = await trilha_com_quiz(client, time)
        r = await estudar(client, time["conn"], time["ev"], a1["id"])
        assert r["concluida_em"] is not None
        assert r["quiz_da_trilha"] == {"perguntas": 10, "aprovado": False, "liberado": False}
        assert not _tem_chave(r, "correta")

    async def test_aula_mostra_quiz_liberado_ao_terminar_a_trilha(self, time, client):
        _, aulas = await trilha_com_quiz(client, time)
        await concluir_aulas(client, time["conn"], time["ev"], aulas)
        r = (await client.get(f"/uc/aulas/{aulas[-1]['id']}", headers=time["ev"]["headers"])).json()
        assert r["quiz_da_trilha"]["liberado"] is True

    async def test_trilha_sem_banco_nao_tem_quiz(self, time, client):
        _, aulas = await trilha_publicada(client, time["g"]["headers"])
        await concluir_aulas(client, time["conn"], time["ev"], aulas)
        p = await painel(client, time["ev"])
        assert p["outras"][0]["quiz"] is None
        assert p["outras"][0]["situacao"]["codigo"] == "concluida" or p["outras"][0]["percentual"] == 100
        r = await client.get(f"/uc/trilhas/{aulas[0]['trilha_id']}/quiz", headers=time["ev"]["headers"])
        assert r.status_code == 404

    async def test_trilha_so_conclui_com_o_quiz(self, time, client):
        t, aulas = await trilha_com_quiz(
            client, time, cargos_lista=[{"cargo": "EV", "obrigatoria": True, "prazo_dias": 30}],
        )
        await concluir_aulas(client, time["conn"], time["ev"], aulas)
        p = await painel(client, time["ev"])
        tr = p["manual"]["trilhas"][0]
        assert tr["situacao"]["codigo"] != "concluida"
        assert (tr["aulas_concluidas"], tr["percentual"]) == (2, 67)
        assert tr["quiz"] == {"perguntas": 10, "aprovado": False, "liberado": True}
        assert p["proxima"]["tipo"] == "quiz" and p["proxima"]["aula_id"] is None
        assert p["proxima"]["trilha_id"] == t["id"]
        d = (await client.get(f"/uc/trilhas/{t['id']}", headers=time["ev"]["headers"])).json()
        assert d["quiz"]["liberado"] is True and d["percentual"] == 67

        q = await abrir_quiz(client, time["ev"], t["id"])
        gab = await gabarito(time["conn"])
        r = await responder(client, time["ev"], t["id"], respostas(q, gab, 1))
        assert r.status_code == 200, r.text
        p = await painel(client, time["ev"])
        tr = p["manual"]["trilhas"][0]
        assert tr["situacao"]["codigo"] == "concluida" and tr["percentual"] == 100
        assert p["proxima"] is None


# ── Tela do quiz ─────────────────────────────────────────────────────

class TestQuizDaTrilha:
    async def test_trancado_ate_concluir_as_aulas(self, time, client):
        t, (a1, _a2) = await trilha_com_quiz(client, time)
        await estudar(client, time["conn"], time["ev"], a1["id"])
        q = await abrir_quiz(client, time["ev"], t["id"])
        assert (q["liberado"], q["aulas_pendentes"], q["perguntas"]) == (False, 1, [])
        resp = await responder(client, time["ev"], t["id"], {})
        assert resp.status_code == 409 and "a aula que falta" in resp.json()["detail"]

    async def test_sorteia_dez_cobrindo_as_aulas_sem_gabarito(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        await concluir_aulas(client, time["conn"], time["ev"], aulas)
        q = await abrir_quiz(client, time["ev"], t["id"])
        assert (q["total"], q["acertos_para_aprovar"], q["nota_minima"]) == (10, 9, 85)
        assert [p["numero"] for p in q["perguntas"]] == list(range(1, 11))
        enunciados = [p["enunciado"] for p in q["perguntas"]]
        assert sum(e.startswith("A1 ") for e in enunciados) == 5
        assert sum(e.startswith("A2 ") for e in enunciados) == 5
        assert not _tem_chave(q, "correta")
        # F5: mesmo sorteio, mesma ordem.
        assert (await abrir_quiz(client, time["ev"], t["id"]))["perguntas"] == q["perguntas"]

    async def test_nove_de_dez_aprova(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q = await abrir_quiz(client, ev, t["id"])
        r = await responder(client, ev, t["id"], respostas(q, await gabarito(conn), 1))
        assert r.status_code == 200
        d = r.json()
        assert d["aprovado"] is True and d["perguntas"] == []
        assert (d["ultima"]["acertos"], d["ultima"]["nota"]) == (9, 90)
        de_novo = await responder(client, ev, t["id"], {})
        assert de_novo.status_code == 409 and "já aprovado" in de_novo.json()["detail"]

    async def test_oito_de_dez_reprova_diz_a_aula_e_segura_dez_minutos(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q1 = await abrir_quiz(client, ev, t["id"])
        gab = await gabarito(conn)
        r = await responder(client, ev, t["id"], respostas(q1, gab, 2))
        assert r.status_code == 200
        d = r.json()
        assert d["aprovado"] is False and d["perguntas"] == []
        assert (d["ultima"]["acertos"], d["ultima"]["nota"]) == (8, 80)
        erradas = d["ultima"]["erradas"]
        assert [(e["numero"], e["aula_ordem"], e["aula_titulo"]) for e in erradas] == [
            (1, 1, "Aula 1"), (2, 1, "Aula 1"),
        ]
        # O enunciado e a alternativa MARCADA (errada); a certa não aparece.
        for e, p in zip(erradas, q1["perguntas"][:2]):
            assert e["enunciado"] == p["enunciado"]
            n = p["enunciado"].split("Pergunta ")[1].rstrip("?")
            assert e["sua_resposta"] in (f"Errada {n}a", f"Errada {n}b", f"Errada {n}c")
        assert "Certa" not in str(erradas)
        assert 590 <= d["segundos_para_refazer"] <= 600
        assert not _tem_chave(d, "correta")

        cedo = await responder(client, ev, t["id"], respostas(q1, gab, 0))
        assert cedo.status_code == 429 and "Nova tentativa em 10 min" in cedo.json()["detail"]

        await conn.execute("UPDATE uc_tentativas_trilha SET criado_em = criado_em - interval '11 minutes'")
        q2 = await abrir_quiz(client, ev, t["id"])
        assert q2["tentativas"] == 1
        assert [p["id"] for p in q2["perguntas"]] != [p["id"] for p in q1["perguntas"]]
        # Responder com o sorteio antigo não vale (nem gasta tentativa).
        velho = await responder(client, ev, t["id"], respostas(q1, gab, 0))
        assert velho.status_code == 422
        ok = await responder(client, ev, t["id"], respostas(q2, gab, 0))
        assert ok.status_code == 200 and ok.json()["aprovado"] is True
        assert ok.json()["tentativas"] == 2

    async def test_tentativa_antiga_ganha_o_texto_das_erradas(self, time, client):
        """Gravada antes da 045 (erradas só com número e aula): completa na leitura."""
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q = await abrir_quiz(client, ev, t["id"])
        await responder(client, ev, t["id"], respostas(q, await gabarito(conn), 3))
        await conn.execute(
            """UPDATE uc_tentativas_trilha SET erradas = (
                 SELECT jsonb_agg(e - 'enunciado' - 'sua_resposta') FROM jsonb_array_elements(erradas) e)"""
        )
        r = await abrir_quiz(client, ev, t["id"])
        erradas = r["ultima"]["erradas"]
        assert [e["numero"] for e in erradas] == [1, 2, 3]
        assert [e["enunciado"] for e in erradas] == [p["enunciado"] for p in q["perguntas"][:3]]
        assert all(e["sua_resposta"].startswith("Errada ") for e in erradas)
        # Pergunta apagada do banco depois: fica só o número.
        await conn.execute("DELETE FROM uc_perguntas WHERE id = $1", UUID(q["perguntas"][0]["id"]))
        r = await abrir_quiz(client, ev, t["id"])
        assert r["ultima"]["erradas"][0]["enunciado"] is None
        assert r["ultima"]["erradas"][0]["sua_resposta"] is None

    async def test_envio_incompleto_nao_gasta_tentativa(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q = await abrir_quiz(client, ev, t["id"])
        corpo = respostas(q, await gabarito(conn), 0)
        corpo.pop(q["perguntas"][9]["id"])
        resp = await responder(client, ev, t["id"], corpo)
        assert resp.status_code == 422 and "falta: 10" in resp.json()["detail"]
        assert await conn.fetchval("SELECT count(*) FROM uc_tentativas_trilha") == 0

    async def test_alternativa_de_outra_pergunta_422(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q = await abrir_quiz(client, ev, t["id"])
        gab = await gabarito(conn)
        corpo = respostas(q, gab, 0)
        p0, p1 = q["perguntas"][0]["id"], q["perguntas"][1]["id"]
        corpo[p0] = gab[p1]["certa"]
        resp = await responder(client, ev, t["id"], corpo)
        assert resp.status_code == 422
        assert await conn.fetchval("SELECT count(*) FROM uc_tentativas_trilha") == 0

    async def test_gestao_ve_em_modo_leitura_sem_perguntas(self, time, client):
        t, aulas = await trilha_com_quiz(client, time)
        ev, conn = time["ev"], time["conn"]
        await concluir_aulas(client, conn, ev, aulas)
        q = await abrir_quiz(client, ev, t["id"])
        await responder(client, ev, t["id"], respostas(q, await gabarito(conn), 4))
        r = await abrir_quiz(client, time["g"], t["id"], usuario_id=ev["id"])
        assert r["modo_leitura"] is True and r["perguntas"] == []
        assert r["ultima"]["acertos"] == 6

    async def test_colega_nao_ve_o_quiz_de_outro(self, time, client):
        t, _ = await trilha_com_quiz(client, time)
        r = await client.get(f"/uc/trilhas/{t['id']}/quiz", params={"usuario_id": time["ev"]["id"]},
                             headers=time["sdr"]["headers"])
        assert r.status_code == 403


# ── Carga ────────────────────────────────────────────────────────────

class TestCargaBanco:
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
        q = await abrir_quiz(client, time["ev"], str(TRILHA_01["id"]))
        # 4 aulas x 7 = 28 no banco; o quiz sorteia 10 e começa trancado.
        assert (q["total"], q["liberado"], q["aulas_pendentes"]) == (10, False, 4)
