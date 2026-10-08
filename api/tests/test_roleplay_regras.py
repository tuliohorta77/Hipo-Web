"""
Roleplay — regras puras (sem banco, sem rede). Rodam no pytest local.

O que seguram:
  * liberação: EV só com quiz aprovado; gestão sempre e fora da média;
    cargo sem cenário não libera;
  * limites do dia e do orçamento, com o status certo (429 / 402);
  * encerramento: transcrição, tokens, motivo, duração e áudio validados;
  * custo e % de fala;
  * a persona e as regras fixas vão no setup do token, e o setup trava
    transcrição, compressão e retomada;
  * cenários: ids e campos consistentes, nenhum sem persona.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services import roleplay as r
from services.roleplay_cenarios import CENARIOS, REGRAS_FIXAS, cenarios_do_cargo, montar_instrucao

AGORA = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


class TestLiberacao:
    def test_ev_sem_quiz_nao_libera_e_aponta_a_trilha(self):
        lib = r.liberacao("EV", quiz_aprovado=False)
        assert not lib.liberado
        assert "Roteiro do EV" in lib.motivo
        assert lib.trilha_id == r.TRILHA_ROTEIRO_POR_CARGO["EV"]

    def test_ev_com_quiz_libera_e_conta_media(self):
        lib = r.liberacao("EV", quiz_aprovado=True)
        assert lib.liberado and lib.conta_media and lib.motivo is None

    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM"])
    def test_gestao_libera_sem_quiz_e_fica_fora_da_media(self, cargo):
        lib = r.liberacao(cargo, quiz_aprovado=False)
        assert lib.liberado and not lib.conta_media

    @pytest.mark.parametrize("cargo", ["SDR", "EC", "EP", "UC", None])
    def test_cargo_sem_cenario_nao_libera(self, cargo):
        lib = r.liberacao(cargo, quiz_aprovado=True)
        assert not lib.liberado
        assert "cargo" in lib.motivo


class TestLimites:
    def test_limite_do_dia(self):
        with pytest.raises(r.RoleplayInvalido) as e:
            r.checar_limites(sessoes_hoje=2, limite_dia=2, gasto_mes_usd=0,
                             orcamento_mes_usd=30, gestao=False)
        assert e.value.status == 429

    def test_gestao_nao_tem_limite_do_dia(self):
        r.checar_limites(sessoes_hoje=9, limite_dia=2, gasto_mes_usd=0,
                         orcamento_mes_usd=30, gestao=True)

    def test_orcamento_vale_para_todos(self):
        with pytest.raises(r.RoleplayInvalido) as e:
            r.checar_limites(sessoes_hoje=0, limite_dia=2, gasto_mes_usd=30.0,
                             orcamento_mes_usd=30, gestao=True)
        assert e.value.status == 402

    def test_zero_desliga_limite_e_orcamento(self):
        r.checar_limites(sessoes_hoje=50, limite_dia=0, gasto_mes_usd=999,
                         orcamento_mes_usd=0, gestao=False)

    def test_limite_abandono(self):
        assert r.limite_abandono(AGORA, 55) == AGORA - timedelta(minutes=85)


class TestEncerramento:
    def test_transcricao_limpa_turnos(self):
        t = r.validar_transcricao([
            {"quem": "executivo", "texto": "  Oi,   Patrícia ", "t_ms": 1200},
            {"quem": "cliente", "texto": "", "t_ms": 1500},
            {"quem": "cliente", "texto": "Oi!", "t_ms": "x"},
        ])
        assert t == [
            {"quem": "executivo", "texto": "Oi, Patrícia", "t_ms": 1200},
            {"quem": "cliente", "texto": "Oi!", "t_ms": 0},
        ]

    def test_transcricao_recusa_falante_desconhecido(self):
        with pytest.raises(r.RoleplayInvalido):
            r.validar_transcricao([{"quem": "sistema", "texto": "x"}])

    def test_transcricao_corta_texto_longo(self):
        t = r.validar_transcricao([{"quem": "cliente", "texto": "a" * 9000}])
        assert len(t[0]["texto"]) == r.MAX_TEXTO_TURNO

    def test_transcricao_formato_invalido(self):
        with pytest.raises(r.RoleplayInvalido):
            r.validar_transcricao("texto solto")
        assert r.validar_transcricao(None) == []

    def test_tokens_normalizados(self):
        t = r.normalizar_tokens({"audio_in": "100", "audio_out": -5, "lixo": 7, "total": None})
        assert t == {"audio_in": 100, "texto_in": 0, "audio_out": 0, "texto_out": 0, "total": 0}
        assert r.normalizar_tokens("nao e json")["audio_in"] == 0

    def test_custo_estimado(self):
        tokens = {"audio_in": 145_588, "texto_in": 63_866, "audio_out": 5_461, "texto_out": 0}
        # (145588 + 63866) * 0.75 + 5461 * 4.50 = 181665 -> US$ 0,1817
        assert r.custo_estimado("gemini-3.8-live", tokens) == Decimal("0.1817")
        assert r.custo_estimado("modelo-novo", tokens) == Decimal("0.1817")

    def test_fala_do_executivo(self):
        t = [{"quem": "executivo", "texto": "um dois tres"}, {"quem": "cliente", "texto": "quatro"}]
        assert r.fala_executivo_pct(t) == 75
        assert r.fala_executivo_pct([]) is None

    def test_motivo(self):
        assert r.validar_motivo(None) == "encerrou"
        assert r.validar_motivo("SALDO") == "saldo"
        with pytest.raises(r.RoleplayInvalido):
            r.validar_motivo("cansei")

    def test_duracao_nunca_passa_do_relogio_do_servidor(self):
        inicio = AGORA - timedelta(minutes=10)
        assert r.duracao_s(inicio, AGORA, 9999, 55) == 600
        assert r.duracao_s(inicio, AGORA, 300, 55) == 300
        assert r.duracao_s(inicio, AGORA, None, 55) == 600
        longe = AGORA - timedelta(hours=3)
        assert r.duracao_s(longe, AGORA, None, 55) == 55 * 60 + 120

    def test_audio(self):
        assert r.validar_audio("audio/webm;codecs=opus", 1000) == ".webm"
        with pytest.raises(r.RoleplayInvalido):
            r.validar_audio("video/mp4", 1000)
        with pytest.raises(r.RoleplayInvalido):
            r.validar_audio("audio/webm", 0)
        with pytest.raises(r.RoleplayInvalido):
            r.validar_audio("audio/webm", r.MAX_AUDIO_BYTES + 1)

    def test_chave_do_audio_so_de_ids(self):
        assert r.chave_audio("u1", "s1", ".webm") == "roleplay/u1/s1.webm"

    def test_inteiro(self):
        assert r.validar_inteiro("12.6", "x") == 13
        assert r.validar_inteiro(None, "x") is None
        assert r.validar_inteiro(-4, "x") == 0
        with pytest.raises(r.RoleplayInvalido):
            r.validar_inteiro("abc", "x")


class TestProximo:
    def test_primeiro_bloco_nao_feito_depois_a_completa(self):
        cen = cenarios_do_cargo("EV")
        ids = [k for k, _ in cen]
        assert r.proximo_cenario(cen, set()) == ids[0]
        blocos = {k for k, c in cen if c["formato"] == "bloco"}
        completa = next(k for k, c in cen if c["formato"] == "completa")
        assert r.proximo_cenario(cen, blocos) == completa
        assert r.proximo_cenario(cen, set(ids)) == ids[0]
        assert r.proximo_cenario([], set()) is None


class TestSetupDoToken:
    def test_setup_trava_persona_transcricao_compressao_e_retomada(self):
        c = CENARIOS["ev-ferrovale-descoberta"]
        s = r.setup_live("gemini-3.8-live", montar_instrucao(c), c["voz"])
        assert s["model"] == "models/gemini-3.8-live"
        assert s["generationConfig"]["responseModalities"] == ["AUDIO"]
        assert s["generationConfig"]["speechConfig"]["languageCode"] == "pt-BR"
        texto = s["systemInstruction"]["parts"][0]["text"]
        assert REGRAS_FIXAS in texto and c["persona"] in texto
        assert s["inputAudioTranscription"] == {} and s["outputAudioTranscription"] == {}
        assert s["sessionResumption"] == {}
        assert s["contextWindowCompression"]["slidingWindow"]["targetTokens"] < \
            s["contextWindowCompression"]["triggerTokens"]

    def test_token_de_uso_unico_com_2_min_para_abrir(self):
        corpo = r.corpo_token({"model": "models/x"}, AGORA)
        assert corpo["uses"] == 1
        assert corpo["newSessionExpireTime"] == "2026-10-08T14:02:00Z"
        assert corpo["expireTime"] == "2026-10-08T14:30:00Z"
        assert corpo["bidiGenerateContentSetup"] == {"model": "models/x"}


class TestCenarios:
    CAMPOS = {"cargo", "versao", "formato", "bloco", "itens_foco", "titulo", "dificuldade",
              "duracao_alvo_min", "voz", "objetivo", "briefing", "persona"}

    @pytest.mark.parametrize("cid", list(CENARIOS))
    def test_campos(self, cid):
        c = CENARIOS[cid]
        assert set(c) == self.CAMPOS
        assert c["formato"] in ("bloco", "completa")
        assert (c["bloco"] is None) == (c["formato"] == "completa")
        assert c["persona"].strip() and c["briefing"].strip()
        assert len(cid) <= 60
        assert c["duracao_alvo_min"] < 55
        assert c["itens_foco"] and set(c["itens_foco"]) <= set(range(1, 11))
        if c["formato"] == "completa":
            assert c["itens_foco"] == tuple(range(1, 11))

    def test_ev_tem_tres_blocos_e_uma_completa(self):
        cen = cenarios_do_cargo("EV")
        assert sorted(c["bloco"] or "completa" for _, c in cen) == \
            ["abertura_descoberta", "completa", "fechamento", "objecoes"]

    def test_gestao_ve_todos(self):
        assert len(cenarios_do_cargo("ADM", gestao=True)) == len(CENARIOS)
        assert cenarios_do_cargo("SDR") == []


class TestEmitirToken:
    """O POST para o Google, com o httpx dublado."""

    async def test_sucesso_devolve_o_nome(self, monkeypatch):
        import httpx
        from config import settings

        visto = {}

        def resposta(request):
            visto["chave"] = request.headers.get("x-goog-api-key")
            visto["corpo"] = request.read()
            return httpx.Response(200, json={"name": "auth_tokens/abc"})

        monkeypatch.setattr(settings, "GEMINI_API_KEY", "k-teste")
        _dublar_httpx(monkeypatch, resposta)
        assert await r.emitir_token({"model": "models/x"}, AGORA) == "auth_tokens/abc"
        assert visto["chave"] == "k-teste"
        assert b'"bidiGenerateContentSetup"' in visto["corpo"]

    async def test_cota_vira_sem_saldo(self, monkeypatch):
        import httpx
        from config import settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", "k-teste")
        _dublar_httpx(monkeypatch, lambda req: httpx.Response(
            429, json={"error": {"message": "Resource has been exhausted", "status": "RESOURCE_EXHAUSTED"}}))
        with pytest.raises(r.GeminiIndisponivel) as e:
            await r.emitir_token({"model": "models/x"}, AGORA)
        assert e.value.sem_saldo and "exhausted" in str(e.value)

    async def test_sem_chave(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        with pytest.raises(r.GeminiIndisponivel):
            await r.emitir_token({"model": "models/x"}, AGORA)


def _dublar_httpx(monkeypatch, handler):
    import httpx

    original = httpx.AsyncClient

    def fabrica(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return original(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", fabrica)


class TestAvaliacaoRegras:
    def test_itens_do_cenario(self):
        from services import roleplay_avaliacao as rav
        assert rav.itens_do_cenario(CENARIOS["ev-ferrovale-objecoes"]) == (7, 8, 9, 10)
        assert rav.itens_do_cenario(None) == tuple(range(1, 11))

    def test_nota_reescalada(self):
        from decimal import Decimal
        from services import roleplay_avaliacao as rav
        assert rav.nota_reescalada({7: 2, 8: 2, 9: 1, 10: 1}, (7, 8, 9, 10)) == Decimal("15.0")
        assert rav.nota_reescalada({}, ()) is None

    def test_conteudo_minimo(self):
        from services import roleplay_avaliacao as rav
        with pytest.raises(rav.SemConteudo):
            rav.conferir_conteudo([{"quem": "executivo", "texto": "Oi"}])
        rav.conferir_conteudo([{"quem": "executivo", "texto": "palavra " * 20}] * 3)

    def test_instrucao_tem_bloco_foco_e_persona(self):
        from services import roleplay_avaliacao as rav
        c = CENARIOS["ev-ferrovale-objecoes"]
        txt = rav.instrucao(c, (7, 8, 9, 10))
        assert c["titulo"] in txt and c["persona"] in txt
        assert "9 (Objeções com LAER)" in txt and "ASUS" in txt
