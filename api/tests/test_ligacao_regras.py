"""
HIPO — Ligações gravadas (056): regras puras, sem banco e sem AWS.

Rodam no pytest local do Windows. A costura com banco e endpoints está em
test_crm_ligacoes.py.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import ligacao as r

UTC = timezone.utc
T0 = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)


# ── Token ────────────────────────────────────────────────────────────


class TestToken:
    def test_gera_token_com_prefixo_e_hash_que_confere(self):
        t = r.gerar_token()
        assert t.token.startswith(r.PREFIXO_TOKEN)
        assert len(t.token) > 40
        assert t.hash == r.hash_token(t.token)
        assert t.prefixo == t.token[:16]

    def test_tokens_diferentes_a_cada_chamada(self):
        assert r.gerar_token().token != r.gerar_token().token

    @pytest.mark.parametrize("header,esperado", [
        ("Bearer hipograv_abc", "hipograv_abc"),
        ("bearer   hipograv_abc  ", "hipograv_abc"),
        ("Bearer eyJhbGciOiJIUzI1NiJ9.x.y", None),   # JWT de usuário não serve
        ("Basic hipograv_abc", None),
        ("", None),
        (None, None),
    ])
    def test_token_do_header(self, header, esperado):
        assert r.token_do_header(header) == esperado

    def test_nome_do_gravador(self):
        assert r.validar_nome_gravador("  Notebook   da  Kethlleen ") == "Notebook da Kethlleen"
        with pytest.raises(r.LigacaoInvalida):
            r.validar_nome_gravador("   ")

    def test_gravador_online(self):
        assert r.gravador_online(T0 - timedelta(minutes=2), T0)
        assert not r.gravador_online(T0 - timedelta(minutes=10), T0)
        assert not r.gravador_online(None, T0)


# ── Clique e telefone ────────────────────────────────────────────────


@pytest.mark.parametrize("bruto,esperado", [
    ("(11) 9 9571-3682", "11995713682"),
    ("+55 11 2222-3333", "+551122223333"),
    ("11 2222-3333 ramal 21", "112222333321"),
    ("", None),
    (None, None),
    ("sem número", None),
])
def test_normalizar_telefone(bruto, esperado):
    assert r.normalizar_telefone(bruto) == esperado


# ── Gravação ─────────────────────────────────────────────────────────


class TestValidarGravacao:
    def test_ok(self):
        assert r.validar_gravacao(62.4, 1_000_000, "FLAC") == (62, 1_000_000, "audio/flac", ".flac")

    @pytest.mark.parametrize("dur,tam,fmt", [
        (3, 1000, "flac"),                       # curta demais
        (5 * 3600, 1000, "flac"),                # longa demais
        (60, 0, "flac"),                         # vazia
        (60, 400 * 1024 * 1024, "flac"),         # grande demais
        (60, 1000, "mp3"),                       # formato
        ("x", 1000, "flac"),                     # lixo
    ])
    def test_recusa(self, dur, tam, fmt):
        with pytest.raises(r.LigacaoInvalida):
            r.validar_gravacao(dur, tam, fmt)


class TestRelogio:
    def test_sem_hora_do_agente_fica_como_veio(self):
        assert r.corrigir_relogio(T0, T0 + timedelta(minutes=1), None, T0) == (T0, T0 + timedelta(minutes=1))

    def test_desvio_pequeno_e_ignorado(self):
        i, f = r.corrigir_relogio(T0, T0 + timedelta(minutes=1), T0, T0 + timedelta(seconds=1))
        assert i == T0

    def test_relogio_atrasado_e_corrigido(self):
        # Máquina 4 min atrasada: mandou "agora = 15:10" quando eram 15:14.
        i, f = r.corrigir_relogio(
            T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=10), T0 + timedelta(minutes=14),
        )
        assert i == T0 + timedelta(minutes=4)
        assert f == T0 + timedelta(minutes=9)

    def test_relogio_absurdo_ancora_na_chegada(self):
        i, f = r.corrigir_relogio(
            T0 - timedelta(days=400), T0 - timedelta(days=400) + timedelta(minutes=3),
            T0 - timedelta(days=400) + timedelta(minutes=4), T0,
        )
        assert f == T0 and f - i == timedelta(minutes=3)

    def test_ler_data(self):
        assert r.ler_data("2026-10-09T15:00:00Z") == T0
        assert r.ler_data("2026-10-09T12:00:00-03:00") == T0
        assert r.ler_data("2026-10-09T15:00:00") == T0          # sem fuso = UTC
        assert r.ler_data(None) is None
        with pytest.raises(r.LigacaoInvalida):
            r.ler_data("ontem")


class TestCasar:
    def test_fica_com_o_clique_mais_recente_da_janela(self):
        cliques = [("a", T0 - timedelta(minutes=2)), ("b", T0 - timedelta(seconds=30))]
        assert r.casar(cliques, T0) == "b"

    def test_clique_logo_depois_do_audio_ainda_casa(self):
        # Relógio da máquina adiantado alguns segundos.
        assert r.casar([("a", T0 + timedelta(seconds=40))], T0) == "a"

    @pytest.mark.parametrize("delta", [timedelta(minutes=-4), timedelta(minutes=2)])
    def test_fora_da_janela_nao_casa(self, delta):
        assert r.casar([("a", T0 + delta)], T0) is None

    def test_sem_cliques(self):
        assert r.casar([], T0) is None


def test_chave_e_nome_do_job():
    assert r.chave_audio("u1", "l1") == "ligacoes/u1/l1.flac"
    assert r.nome_job("l1", 3) == "hipo-ligacao-l1-t3"


# ── Leitura do Transcribe ────────────────────────────────────────────


def _palavra(ini, fim, texto):
    return {"start_time": str(ini), "end_time": str(fim), "type": "pronunciation",
            "alternatives": [{"confidence": "0.99", "content": texto}]}


def _pont(texto):
    return {"type": "punctuation", "alternatives": [{"confidence": "0.0", "content": texto}]}


def json_transcribe():
    return {"results": {"channel_labels": {"number_of_channels": 2, "channels": [
        {"channel_label": "ch_0", "items": [
            _palavra(0.5, 0.8, "Bom"), _palavra(0.8, 1.1, "dia"), _pont(","),
            _palavra(1.2, 1.6, "Carla"), _pont("?"),
            # pausa longa: fala nova do mesmo lado
            _palavra(6.0, 6.4, "Perfeito"), _pont("."),
        ]},
        {"channel_label": "ch_1", "items": [
            _palavra(2.0, 2.3, "Oi"), _pont(","), _palavra(2.4, 2.9, "tudo"),
            _palavra(2.9, 3.2, "bem"), _pont("."),
        ]},
    ]}}}


class TestLerTranscribe:
    def test_canais_viram_trechos_em_ordem(self):
        t = r.ler_transcribe(json_transcribe())
        assert [(x.canal, x.texto) for x in t] == [
            (0, "Bom dia, Carla?"),
            (1, "Oi, tudo bem."),
            (0, "Perfeito."),
        ]

    def test_sem_canais_cai_nos_itens_como_cliente(self):
        d = {"results": {"items": [_palavra(0, 1, "alô")]}}
        assert [(x.canal, x.texto) for x in r.ler_transcribe(d)] == [(1, "alô")]

    def test_vazio(self):
        assert r.ler_transcribe({}) == []
        assert r.ler_transcribe({"results": {"channel_labels": {"channels": [
            {"channel_label": "ch_0", "items": []}]}}}) == []

    def test_item_sem_horario_e_ignorado(self):
        d = {"results": {"channel_labels": {"channels": [{"channel_label": "ch_0", "items": [
            {"type": "pronunciation", "alternatives": [{"content": "x"}]},
            _palavra(1, 2, "ok"),
        ]}]}}}
        assert [x.texto for x in r.ler_transcribe(d)] == ["ok"]

    def test_fala_do_usuario(self):
        t = r.ler_transcribe(json_transcribe())
        # usuário: 1.1 + 0.4 = 1.5 s; cliente: 1.2 s
        assert r.fala_usuario_pct(t) == 56

    def test_texto_e_entradas_com_horario_de_brasilia(self):
        t = r.ler_transcribe(json_transcribe())
        texto = r.texto(t, T0, "Kethlleen", "Carla")
        assert texto.splitlines()[0] == "[12:00] Kethlleen: Bom dia, Carla?"
        assert texto.splitlines()[1] == "[12:00] Carla: Oi, tudo bem."
        ent = r.entradas(t, T0, "Kethlleen", "Carla")
        assert [e["canal"] for e in ent] == [0, 1, 0]
        assert ent[0]["inicio"] == (T0 + timedelta(seconds=0.5)).isoformat()


def test_primeiro_nome():
    assert r.primeiro_nome("Jakeline Santana") == "Jakeline"
    assert r.primeiro_nome(None) == "Executivo"


# ── Passada e retenção ───────────────────────────────────────────────


def test_janelas_da_passada():
    assert r.clique_expirado(T0 - timedelta(hours=7), T0)
    assert not r.clique_expirado(T0 - timedelta(hours=5), T0)
    assert r.envio_expirado(T0 - timedelta(hours=3), T0)
    assert not r.envio_expirado(T0 - timedelta(minutes=30), T0)
    assert r.transcricao_expirada(T0 - timedelta(hours=4), T0)
    assert not r.transcricao_expirada(None, T0)


def test_retencao():
    assert r.audio_vencido(T0 - timedelta(days=181), T0, T0, 180)
    assert not r.audio_vencido(T0 - timedelta(days=10), T0, T0, 180)
    assert not r.audio_vencido(T0 - timedelta(days=999), T0, T0, 0)   # 0 = para sempre
    assert r.audio_vencido(None, T0 - timedelta(days=200), T0, 180)


# ── Visão ────────────────────────────────────────────────────────────


class TestVisao:
    def test_sem_vinculo_so_dono_e_gestao(self):
        assert r.pode_ver("u1", None, None, "u1", False)
        assert r.pode_ver("u1", None, None, "u2", True)
        assert not r.pode_ver("u1", None, None, "u2", False)

    def test_vinculada_e_da_negociacao(self):
        assert r.pode_ver("u1", "opp", None, "u2", False)
        assert r.pode_ver("u1", None, "conta", "u2", False)

    def test_alterar(self):
        assert r.pode_alterar("u1", "u1", False)
        assert r.pode_alterar("u1", "u9", True)
        assert not r.pode_alterar("u1", "u2", False)


def test_kpis():
    k = r.resumo_kpis([
        {"status": "pronta", "duracao_s": 90, "fala_usuario_pct": 60},
        {"status": "pronta", "duracao_s": 150, "fala_usuario_pct": 40},
        {"status": "sem_gravacao", "duracao_s": None, "fala_usuario_pct": None},
    ])
    assert k == {"total": 3, "gravadas": 2, "minutos": 4, "transcritas": 2, "fala_media_pct": 50}
    assert r.resumo_kpis([])["fala_media_pct"] is None


# ── Duplicata ────────────────────────────────────────────────────────


def json_frase(texto: str, canal: int = 1) -> dict:
    """Um JSON do Transcribe com `texto` inteiro no canal pedido (0,4 s por palavra)."""
    itens = [_palavra(round(i * 0.4, 2), round(i * 0.4 + 0.3, 2), p)
             for i, p in enumerate(texto.split())]
    canais = [{"channel_label": f"ch_{c}", "items": itens if c == canal else []} for c in (0, 1)]
    return {"results": {"channel_labels": {"number_of_channels": 2, "channels": canais}}}


# As duas transcrições reais de 13/10/2026: o mesmo áudio, transcrito duas
# vezes, com o Transcribe errando palavras diferentes em cada uma.
ORIGINAL_13_10 = ("Alô. Oi filha, tudo bem e você? Então tá internando, mas não saiu ainda. "
                  "Como já estava pedido, é provavelmente não é, não sei. É. É. Tá, tá, obrigada.")
COPIA_13_10 = ("Alô. Oi filha, tudo bem e você? Então. Tá internando, mas não sei ainda. "
               "Como já estava pedido. É provavelmente, não sei.")


class TestDuplicata:
    def test_palavras_normaliza_acento_caixa_e_pontuacao(self):
        assert r.palavras(["Então, TÁ internando!"]) == ["entao", "ta", "internando"]

    def test_palavras_das_entradas_aceita_lista_e_json(self):
        entradas = [{"texto": "Bom dia"}, {"texto": "Oi, tudo bem"}]
        assert r.palavras_das_entradas(entradas) == ["bom", "dia", "oi", "tudo", "bem"]
        assert r.palavras_das_entradas('[{"texto": "Bom dia"}]') == ["bom", "dia"]
        assert r.palavras_das_entradas("não é json") == []
        assert r.palavras_das_entradas(None) == []

    def test_o_caso_real_de_13_10_e_a_mesma_conversa(self):
        a, b = r.palavras([ORIGINAL_13_10]), r.palavras([COPIA_13_10])
        assert r.semelhanca(a, b) > 0.9
        assert r.mesma_conversa(a, b)

    def test_trecho_reproduzido_dentro_de_conversa_maior_e_duplicata(self):
        longa = r.palavras(["Bom dia, aqui é da Controller. " + ORIGINAL_13_10 + " Até logo então."])
        assert r.mesma_conversa(r.palavras([COPIA_13_10]), longa)

    def test_conversas_diferentes_nao_sao_duplicata(self):
        outra = r.palavras(["Bom dia, falo com o responsável pelo RH da empresa? "
                            "Queria apresentar a medicina ocupacional da Controller."])
        assert not r.mesma_conversa(r.palavras([ORIGINAL_13_10]), outra)

    def test_conversa_curta_nunca_e_duplicata(self):
        alo = r.palavras(["Alô, alô, quem fala?"])
        assert not r.mesma_conversa(alo, alo)

    def test_qual_sai_nunca_e_a_vinculada(self):
        vinc = {"id": "v", "vinculada": True, "inicio": T0 + timedelta(minutes=2)}
        solta = {"id": "s", "vinculada": False, "inicio": T0}
        assert r.qual_duplicada(vinc, solta) == "s"
        assert r.qual_duplicada(solta, vinc) == "s"

    def test_entre_duas_soltas_sai_a_mais_nova(self):
        a = {"id": "a", "vinculada": False, "inicio": T0}
        b = {"id": "b", "vinculada": False, "inicio": T0 + timedelta(minutes=2)}
        assert r.qual_duplicada(a, b) == "b"
        assert r.qual_duplicada(b, a) == "b"

    def test_duas_vinculadas_ficam(self):
        a = {"id": "a", "vinculada": True, "inicio": T0}
        assert r.qual_duplicada(a, {**a, "id": "b"}) is None
