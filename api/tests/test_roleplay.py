"""
Roleplay — rotas (banco). O Gemini e o S3 são dublados: nenhum teste
sai para a rede.

O que seguram:
  1. EV sem quiz aprovado: tela bloqueada com o motivo, e abrir dá 403;
  2. EV com quiz: termo obrigatório (409), depois abre, recebe o token e a
     tela nunca devolve a persona (o teste varre o JSON);
  3. sessão aberta impede outra (409); limite do dia (429); orçamento (402);
  4. reconexão: token novo só para o dono e com a sessão em andamento;
  5. encerrar: grava transcrição, tokens, custo, fala e áudio; é idempotente;
  6. gestão treina sem quiz, fora da média, e lê a sessão do EV; o EV não
     lê a de outra pessoa;
  7. Gemini sem saldo vira 503 com mensagem de pausa, sem criar sessão;
  8. sessão esquecida aberta vira abandonada.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from config import settings
from services import anexo as s3
from services import roleplay as regras
from services.roleplay_cenarios import CENARIOS
from tests.conftest import criar_usuario

TRILHA_EV = regras.TRILHA_ROTEIRO_POR_CARGO["EV"]
CENARIO = "ev-ferrovale-descoberta"


@pytest.fixture(autouse=True)
def gemini_e_s3_falsos(monkeypatch):
    """Token falso, S3 em memória, limites conhecidos."""
    emitidos = []

    async def emitir(setup, agora=None):
        emitidos.append(setup)
        return f"auth_tokens/falso-{len(emitidos)}"

    guardados = {}
    monkeypatch.setattr(regras, "emitir_token", emitir)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "chave-de-teste")
    monkeypatch.setattr(settings, "ROLEPLAY_LIMITE_DIA", 2)
    monkeypatch.setattr(settings, "ROLEPLAY_ORCAMENTO_MES_USD", 30.0)
    monkeypatch.setattr(s3, "disponivel", lambda: True)
    monkeypatch.setattr(s3, "subir", lambda chave, conteudo, tipo: guardados.__setitem__(chave, (conteudo, tipo)))
    monkeypatch.setattr(s3, "url_temporaria", lambda chave, nome=None: f"https://s3.teste/{chave}")
    return {"emitidos": emitidos, "guardados": guardados}


async def _id(db_conn, email):
    return await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", email)


async def _trilha(db_conn):
    await db_conn.execute(
        """
        INSERT INTO uc_trilhas (id, titulo, pilar, status)
        VALUES ($1, '02 · Roteiro do EV', 'metodo', 'publicada')
        ON CONFLICT (id) DO NOTHING
        """,
        TRILHA_EV,
    )


async def _aprovar_quiz(db_conn, usuario_id, aprovada=True):
    await _trilha(db_conn)
    await db_conn.execute(
        """
        INSERT INTO uc_tentativas_trilha (usuario_id, trilha_id, acertos, total, nota,
                                          nota_minima, aprovada, perguntas, respostas)
        VALUES ($1, $2, $3, 10, $4, 85, $5, '[]', '{}')
        """,
        usuario_id, TRILHA_EV, 9 if aprovada else 5, 90 if aprovada else 50, aprovada,
    )


async def _ev_liberado(db_conn, client, email="ev@teste.com", consentir=True):
    ev = await criar_usuario(db_conn, client, "EV", email)
    ev["id"] = await _id(db_conn, email)
    await _aprovar_quiz(db_conn, ev["id"])
    if consentir:
        r = await client.post("/carreira/roleplay/consentimento", headers=ev["headers"])
        assert r.status_code == 200, r.text
    return ev


async def _abrir(client, headers, cenario=CENARIO):
    return await client.post("/carreira/roleplay/sessoes", json={"cenario_id": cenario}, headers=headers)


def _sem_persona(obj):
    texto = json.dumps(obj, ensure_ascii=False, default=str)
    assert '"persona"' not in texto
    for c in CENARIOS.values():
        assert c["persona"][:80] not in texto


async def _encerrar(client, headers, sessao_id, dados=None, audio=True):
    dados = dados or {
        "transcricao": [
            {"quem": "executivo", "texto": "Oi Patrícia, tudo bem? Vi as vagas no LinkedIn.", "t_ms": 1000},
            {"quem": "cliente", "texto": "Tudo bem. Pode falar.", "t_ms": 4000},
        ],
        "tokens": {"audio_in": 100_000, "texto_in": 20_000, "audio_out": 4_000, "texto_out": 0, "total": 124_000},
        "duracao_s": 30, "motivo_fim": "encerrou", "reconexoes": 1, "latencia_media_ms": 820,
    }
    files = {"audio": ("roleplay.webm", b"OggS-falso-webm", "audio/webm")} if audio else None
    return await client.post(
        f"/carreira/roleplay/sessoes/{sessao_id}/encerrar",
        data={"dados": json.dumps(dados)}, files=files, headers=headers,
    )


async def test_ev_sem_quiz_ve_bloqueio_e_nao_abre(db_conn, client):
    ev = await criar_usuario(db_conn, client, "EV", "ev@teste.com")
    await _aprovar_quiz(db_conn, await _id(db_conn, "ev@teste.com"), aprovada=False)
    r = await client.get("/carreira/roleplay", headers=ev["headers"])
    assert r.status_code == 200, r.text
    tela = r.json()
    assert tela["liberado"] is False and tela["pode_treinar"] is False
    assert "Roteiro do EV" in tela["motivo"]
    assert tela["trilha_id"] == str(TRILHA_EV)
    assert len(tela["cenarios"]) == 4
    _sem_persona(tela)
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 403
    assert "quiz" in r.json()["detail"]


async def test_termo_obrigatorio_depois_abre_com_token(db_conn, client, gemini_e_s3_falsos):
    ev = await _ev_liberado(db_conn, client, consentir=False)
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["liberado"] and tela["consentimento_pendente"]
    assert tela["proximo"]["id"] == CENARIO
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 409 and "termo" in r.json()["detail"]

    assert (await client.post("/carreira/roleplay/consentimento", headers=ev["headers"])).status_code == 200
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["token"] == "auth_tokens/falso-1"
    assert corpo["ws_url"].endswith("BidiGenerateContentConstrained")
    assert corpo["cenario"]["id"] == CENARIO
    _sem_persona(corpo)
    # A persona foi para o Google, travada no token.
    setup = gemini_e_s3_falsos["emitidos"][0]
    assert CENARIOS[CENARIO]["persona"] in setup["systemInstruction"]["parts"][0]["text"]
    linha = await db_conn.fetchrow("SELECT * FROM roleplay_sessoes WHERE id = $1", UUID(corpo["sessao_id"]))
    assert linha["status"] == "iniciada" and linha["conta_media"] is True
    assert linha["cenario_versao"] == CENARIOS[CENARIO]["versao"]


async def test_cenario_de_outro_cargo_e_desconhecido(db_conn, client):
    ev = await _ev_liberado(db_conn, client)
    assert (await _abrir(client, ev["headers"], "nao-existe")).status_code == 404
    CENARIOS["sdr-teste"] = {**CENARIOS[CENARIO], "cargo": "SDR"}
    try:
        assert (await _abrir(client, ev["headers"], "sdr-teste")).status_code == 403
    finally:
        del CENARIOS["sdr-teste"]


async def test_sessao_aberta_limite_do_dia_e_orcamento(db_conn, client, monkeypatch):
    ev = await _ev_liberado(db_conn, client)
    s1 = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 409 and "andamento" in r.json()["detail"]

    assert (await _encerrar(client, ev["headers"], s1)).status_code == 200
    s2 = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    assert (await _encerrar(client, ev["headers"], s2)).status_code == 200
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 429 and "limite" in r.json()["detail"]

    monkeypatch.setattr(settings, "ROLEPLAY_LIMITE_DIA", 0)
    await db_conn.execute("UPDATE roleplay_sessoes SET custo_estimado_usd = 15")
    r = await _abrir(client, ev["headers"])
    # Mensagem neutra: custo de IA não é assunto do time operacional.
    assert r.status_code == 402 and "pausado" in r.json()["detail"]
    assert "orçamento" not in r.json()["detail"]
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["disponivel"] is False and "pausado" in tela["indisponivel_motivo"]
    assert tela["orcamento"] is None
    assert all(h["custo_estimado_usd"] is None for h in tela["historico"])


async def test_reconexao_emite_token_novo_so_para_o_dono(db_conn, client, gemini_e_s3_falsos):
    ev = await _ev_liberado(db_conn, client)
    outro = await _ev_liberado(db_conn, client, "ev2@teste.com")
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    r = await client.post(f"/carreira/roleplay/sessoes/{sid}/token", headers=ev["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["token"] == "auth_tokens/falso-2"
    assert await db_conn.fetchval("SELECT tokens_emitidos FROM roleplay_sessoes WHERE id = $1", UUID(sid)) == 2
    assert (await client.post(f"/carreira/roleplay/sessoes/{sid}/token", headers=outro["headers"])).status_code == 403

    await db_conn.execute("UPDATE roleplay_sessoes SET tokens_emitidos = $2 WHERE id = $1",
                          UUID(sid), regras.MAX_TOKENS_POR_SESSAO)
    assert (await client.post(f"/carreira/roleplay/sessoes/{sid}/token", headers=ev["headers"])).status_code == 429

    await _encerrar(client, ev["headers"], sid)
    r = await client.post(f"/carreira/roleplay/sessoes/{sid}/token", headers=ev["headers"])
    assert r.status_code == 409


async def test_encerrar_grava_tudo_e_e_idempotente(db_conn, client, gemini_e_s3_falsos):
    ev = await _ev_liberado(db_conn, client)
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    r = await _encerrar(client, ev["headers"], sid)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "encerrada" and s["motivo_fim"] == "encerrou"
    assert s["fala_executivo_pct"] == 69  # 9 palavras do executivo, 4 do cliente
    assert s["reconexoes"] == 1 and s["latencia_media_ms"] == 820
    # (100000 + 20000) * 0.75 + 4000 * 4.5 = 108000 -> US$ 0,108, gravado; o EV não vê.
    assert s["custo_estimado_usd"] is None
    assert float(await db_conn.fetchval(
        "SELECT custo_estimado_usd FROM roleplay_sessoes WHERE id = $1", UUID(sid))) == pytest.approx(0.108)
    assert s["tem_audio"] is True
    assert len(s["transcricao"]) == 2
    chave = f"roleplay/{ev['id']}/{sid}.webm"
    assert gemini_e_s3_falsos["guardados"][chave] == (b"OggS-falso-webm", "audio/webm")
    assert 0 <= s["duracao_s"] <= 30

    de_novo = await _encerrar(client, ev["headers"], sid, dados={"transcricao": []})
    assert de_novo.status_code == 200 and len(de_novo.json()["transcricao"]) == 2

    r = await client.get(f"/carreira/roleplay/sessoes/{sid}/audio", headers=ev["headers"])
    assert r.json()["url"] == f"https://s3.teste/{chave}"
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["resumo"]["sessoes_mes"] == 1 and tela["resumo"]["sessoes_hoje"] == 1
    assert tela["historico"][0]["id"] == sid
    assert next(c for c in tela["cenarios"] if c["id"] == CENARIO)["tentativas"] == 1
    assert tela["proximo"]["id"] != CENARIO


async def test_encerrar_valida_e_sem_s3_fecha_sem_audio(db_conn, client, monkeypatch):
    ev = await _ev_liberado(db_conn, client)
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    r = await client.post(f"/carreira/roleplay/sessoes/{sid}/encerrar",
                          data={"dados": "{quebrado"}, headers=ev["headers"])
    assert r.status_code == 422
    r = await _encerrar(client, ev["headers"], sid, dados={"transcricao": [{"quem": "robo", "texto": "x"}]})
    assert r.status_code == 422
    monkeypatch.setattr(s3, "disponivel", lambda: False)
    r = await _encerrar(client, ev["headers"], sid, dados={"motivo_fim": "saldo"})
    assert r.status_code == 200, r.text
    assert r.json()["tem_audio"] is False and r.json()["motivo_fim"] == "saldo"


async def test_gestao_treina_fora_da_media_e_le_a_sessao_do_ev(db_conn, client):
    ev = await _ev_liberado(db_conn, client)
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    await _encerrar(client, ev["headers"], sid)

    adm = await criar_usuario(db_conn, client, "ADM", "adm@teste.com")
    await client.post("/carreira/roleplay/consentimento", headers=adm["headers"])
    tela_adm = (await client.get("/carreira/roleplay", headers=adm["headers"])).json()
    assert tela_adm["liberado"] and tela_adm["resumo"]["limite_dia"] == 0
    # Custo de IA: só o Franqueado vê, nem o ADM.
    assert tela_adm["orcamento"] is None
    r = await _abrir(client, adm["headers"], "ev-ferrovale-completa")
    assert r.status_code == 201, r.text
    conta = await db_conn.fetchval("SELECT conta_media FROM roleplay_sessoes WHERE id = $1",
                                   UUID(r.json()["sessao_id"]))
    assert conta is False

    leitura = (await client.get("/carreira/roleplay", params={"usuario_id": str(ev["id"])},
                                headers=adm["headers"])).json()
    assert leitura["modo_leitura"] and not leitura["pode_treinar"]
    assert leitura["historico"][0]["id"] == sid
    det = await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=adm["headers"])
    assert det.status_code == 200 and det.json()["modo_leitura"] is True

    outro = await _ev_liberado(db_conn, client, "ev2@teste.com")
    assert (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=outro["headers"])).status_code == 403
    assert (await client.get("/carreira/roleplay", params={"usuario_id": str(ev["id"])},
                             headers=outro["headers"])).status_code == 403


async def test_gemini_sem_saldo_vira_503_sem_sessao(db_conn, client, monkeypatch):
    ev = await _ev_liberado(db_conn, client)

    async def recusa(setup, agora=None):
        raise regras.GeminiIndisponivel("Gemini recusou o token (429).", sem_saldo=True)

    monkeypatch.setattr(regras, "emitir_token", recusa)
    r = await _abrir(client, ev["headers"])
    assert r.status_code == 503 and "pausado" in r.json()["detail"]
    assert await db_conn.fetchval("SELECT count(*) FROM roleplay_sessoes") == 0


async def test_sem_chave_tela_explica(db_conn, client, monkeypatch):
    ev = await _ev_liberado(db_conn, client)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["disponivel"] is False and "chave" in tela["indisponivel_motivo"]


async def test_sessao_esquecida_vira_abandonada_e_libera_nova(db_conn, client):
    ev = await _ev_liberado(db_conn, client)
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    await db_conn.execute("UPDATE roleplay_sessoes SET iniciada_em = $2 WHERE id = $1",
                          UUID(sid), datetime.now(timezone.utc) - timedelta(hours=3))
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["historico"][0]["status"] == "abandonada"
    # Abandonada de ontem não conta no limite de hoje; nova sessão abre.
    await db_conn.execute("UPDATE roleplay_sessoes SET iniciada_em = iniciada_em - interval '1 day'")
    assert (await _abrir(client, ev["headers"])).status_code == 201
    # E a abandonada ainda aceita o encerramento (a gravação não se perde).
    assert (await _encerrar(client, ev["headers"], sid)).status_code == 200


# ── RP-2: avaliação ──────────────────────────────────────────────────

from services import ia  # noqa: E402
from services import roleplay_avaliacao as rav  # noqa: E402

FALAS = [
    {"quem": "executivo", "texto": "Oi Patrícia, vi que vocês ampliaram a fábrica e estão com vagas abertas de operador.", "t_ms": 1000},
    {"quem": "cliente", "texto": "Isso, estamos contratando bastante.", "t_ms": 6000},
    {"quem": "executivo", "texto": "Antes de apresentar, posso entender como funciona hoje e no final a gente decide junto o próximo passo?", "t_ms": 9000},
    {"quem": "cliente", "texto": "Pode sim.", "t_ms": 14000},
    {"quem": "executivo", "texto": "O que mais te incomoda hoje no fornecedor atual de medicina ocupacional?", "t_ms": 16000},
    {"quem": "cliente", "texto": "O ASO admissional demora de cinco a sete dias.", "t_ms": 20000},
]


def _resposta_ia(itens_nota: dict[int, tuple[int, str]]):
    itens = []
    for n in range(1, 11):
        nota, ev = itens_nota.get(n, (0, ""))
        itens.append({"item": n, "nota": nota, "evidencia": ev, "justificativa": f"j{n}", "sugestao": f"s{n}"})
    return {"content": [{"type": "tool_use", "name": "registrar_avaliacao", "input": {
        "itens": itens,
        "pontos_fortes": [{"texto": "Usou a pesquisa", "evidencia": "vi que vocês ampliaram a fábrica"}],
        "pontos_melhorar": [{"texto": "Aprofundar o custo", "evidencia": "O que mais te incomoda hoje",
                             "como_fazer": "Pergunte quanto custa a vaga parada."}],
        "foco_proxima": "Fazer pergunta de implicação.",
        "resumo": "Boa abertura, faltou implicação.",
    }}]}


@pytest.fixture
def ia_falsa(monkeypatch):
    chamadas = []
    resposta = {"corpo": _resposta_ia({
        1: (2, "vi que vocês ampliaram a fábrica e estão com vagas abertas"),
        2: (2, "posso entender como funciona hoje e no final a gente decide junto o próximo passo"),
        4: (1, "O que mais te incomoda hoje no fornecedor atual"),
        5: (2, "quanto custa um dia parado"),  # inventado: não está na transcrição
        9: (2, "objeção tratada"),             # fora do bloco de descoberta
    })}

    async def chamar(corpo):
        chamadas.append(corpo)
        if isinstance(resposta["corpo"], Exception):
            raise resposta["corpo"]
        return resposta["corpo"]

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k-teste")
    monkeypatch.setattr(rav, "chamar_ia", chamar)
    return {"chamadas": chamadas, "resposta": resposta}


async def _sessao_encerrada(db_conn, client, ev, falas=FALAS):
    sid = (await _abrir(client, ev["headers"])).json()["sessao_id"]
    r = await _encerrar(client, ev["headers"], sid, dados={"transcricao": falas, "motivo_fim": "encerrou"})
    assert r.status_code == 200, r.text
    return sid, r


async def test_encerrar_avalia_com_checagem_de_evidencia_e_nota_do_bloco(db_conn, client, ia_falsa):
    ev = await _ev_liberado(db_conn, client)
    sid, r = await _sessao_encerrada(db_conn, client, ev)
    # A tarefa em segundo plano roda antes do cliente de teste devolver.
    det = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()
    a = det["avaliacao"]
    assert a["status"] == "pronta", a
    # Bloco de descoberta: itens 1..7 contam. 1=2, 2=2, 4=1, 5 descartado (trecho
    # inventado) = 0, item 9 (fora do bloco) não entra: 5 de 14 -> 7,1/20.
    assert [i["item"] for i in a["itens"]] == [1, 2, 3, 4, 5, 6, 7]
    assert a["nota_total"] == 7.1 and a["faixa"] == "baixa"
    item5 = next(i for i in a["itens"] if i["item"] == 5)
    assert item5["nota"] is None and "não foi encontrado" in item5["descartado"]
    assert a["pontos_melhorar"][0]["como_fazer"].startswith("Pergunte")
    assert a["pode_ajustar"] is False and a["pode_reavaliar"] is False
    # A persona e o bloco foram para o coach; a transcrição no formato "[mm:ss] Nome:".
    corpo = ia_falsa["chamadas"][0]
    assert CENARIOS[CENARIO]["persona"] in corpo["system"]
    assert "[00:16] Executivo: O que mais te incomoda" in corpo["messages"][0]["content"]
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["resumo"]["media_mes"] == 7.1 and tela["resumo"]["ultimas_notas"] == [7.1]
    assert tela["historico"][0]["nota_total"] == 7.1
    assert next(c for c in tela["cenarios"] if c["id"] == CENARIO)["melhor_nota"] == 7.1


async def test_conversa_curta_nao_vira_nota(db_conn, client, ia_falsa):
    ev = await _ev_liberado(db_conn, client)
    sid, _ = await _sessao_encerrada(db_conn, client, ev, falas=FALAS[:2])
    a = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()["avaliacao"]
    assert a["status"] == "sem_conteudo" and "curta" in a["erro"]
    assert ia_falsa["chamadas"] == []
    tela = (await client.get("/carreira/roleplay", headers=ev["headers"])).json()
    assert tela["resumo"]["media_mes"] is None


async def test_falha_da_ia_vira_erro_e_o_dono_avalia_de_novo(db_conn, client, ia_falsa):
    ev = await _ev_liberado(db_conn, client)
    ia_falsa["resposta"]["corpo"] = RuntimeError("A IA respondeu HTTP 529.")
    sid, _ = await _sessao_encerrada(db_conn, client, ev)
    a = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()["avaliacao"]
    assert a["status"] == "erro" and "529" in a["erro"] and a["pode_reavaliar"] is True

    ia_falsa["resposta"]["corpo"] = _resposta_ia({1: (2, "vi que vocês ampliaram a fábrica")})
    r = await client.post(f"/carreira/roleplay/sessoes/{sid}/avaliar", headers=ev["headers"])
    assert r.status_code == 200, r.text
    a = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()["avaliacao"]
    assert a["status"] == "pronta" and a["nota_total"] == 2.9  # 2 de 14
    # Pronta: o dono não pede outra avaliação.
    assert (await client.post(f"/carreira/roleplay/sessoes/{sid}/avaliar", headers=ev["headers"])).status_code == 403


async def test_treino_anterior_ao_rp2_o_dono_avalia_agora(db_conn, client, ia_falsa):
    ev = await _ev_liberado(db_conn, client)
    sid, _ = await _sessao_encerrada(db_conn, client, ev)
    # Simula um treino gravado antes da migration 035: sem linha de avaliação.
    await db_conn.execute("DELETE FROM roleplay_avaliacoes WHERE sessao_id = $1", UUID(sid))
    det = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()
    assert det["avaliacao"] is None
    r = await client.post(f"/carreira/roleplay/sessoes/{sid}/avaliar", headers=ev["headers"])
    assert r.status_code == 200, r.text
    a = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=ev["headers"])).json()["avaliacao"]
    assert a["status"] == "pronta" and a["nota_total"] == 7.1


async def test_gestao_ajusta_valida_e_trava(db_conn, client, ia_falsa):
    ev = await _ev_liberado(db_conn, client)
    sid, _ = await _sessao_encerrada(db_conn, client, ev)
    adm = await criar_usuario(db_conn, client, "ADM", "adm@teste.com")
    url = f"/carreira/roleplay/sessoes/{sid}"

    assert (await client.patch(f"{url}/itens/5", json={"nota": 2}, headers=ev["headers"])).status_code == 403
    r = await client.patch(f"{url}/itens/5", json={"nota": 2}, headers=adm["headers"])
    assert r.status_code == 200, r.text
    a = r.json()["avaliacao"]
    assert a["nota_total"] == 10.0  # 7 de 14
    item5 = next(i for i in a["itens"] if i["item"] == 5)
    assert item5["nota"] == 2 and item5["nota_ia"] is None and item5["ajustada_por"] == "Test ADM"
    assert (await client.patch(f"{url}/itens/9", json={"nota": 2}, headers=adm["headers"])).status_code == 422
    assert (await client.patch(f"{url}/itens/5", json={"nota": 3}, headers=adm["headers"])).status_code == 422

    r = await client.patch(f"{url}/itens/5", json={"nota": None}, headers=adm["headers"])
    assert r.json()["avaliacao"]["nota_total"] == 7.1

    r = await client.post(f"{url}/validar", headers=adm["headers"])
    assert r.json()["avaliacao"]["validada"] is True and r.json()["avaliacao"]["pode_ajustar"] is False
    assert (await client.patch(f"{url}/itens/5", json={"nota": 2}, headers=adm["headers"])).status_code == 409
    assert (await client.post(f"{url}/avaliar", headers=adm["headers"])).status_code == 409
    assert (await client.post(f"{url}/validar", headers=ev["headers"])).status_code == 403
    r = await client.delete(f"{url}/validar", headers=adm["headers"])
    assert r.json()["avaliacao"]["validada"] is False


async def test_franqueado_ve_custo_e_orcamento(db_conn, client, ia_falsa):
    fr = await criar_usuario(db_conn, client, "Franqueado", "fr@teste.com")
    await client.post("/carreira/roleplay/consentimento", headers=fr["headers"])
    sid = (await _abrir(client, fr["headers"], "ev-ferrovale-completa")).json()["sessao_id"]
    await _encerrar(client, fr["headers"], sid, dados={"transcricao": FALAS, "tokens": {"audio_in": 1_000_000}})
    tela = (await client.get("/carreira/roleplay", headers=fr["headers"])).json()
    assert tela["orcamento"] == {"gasto_mes_usd": 0.75, "orcamento_mes_usd": 30.0}
    assert tela["historico"][0]["custo_estimado_usd"] == 0.75
    # Sessão da gestão: avaliada, mas fora da média.
    assert tela["resumo"]["media_mes"] is None
    a = (await client.get(f"/carreira/roleplay/sessoes/{sid}", headers=fr["headers"])).json()["avaliacao"]
    assert a["status"] == "pronta" and len(a["itens"]) == 10
