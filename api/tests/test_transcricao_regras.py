"""
HIPO — Regras puras da transcrição (services/transcricao.py) e do resumo
(services/resumo_reuniao.py, a parte que não chama a rede).

Sem banco e sem Google: rodam no Windows sem Postgres.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import resumo_reuniao
from services import transcricao as t
from services.transcricao import Conferencia, Fala, Transcricao

UTC = timezone.utc
INICIO = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)      # 09:00 em Brasília
FIM = INICIO + timedelta(minutes=30)


def conf(nome="conferenceRecords/a", ini=INICIO, fim=FIM, *ts):
    return Conferencia(nome=nome, inicio=ini, fim=fim, transcricoes=tuple(ts))


def tr(estado="FILE_GENERATED", nome="conferenceRecords/a/transcripts/1", doc=None):
    return Transcricao(nome=nome, estado=estado, documento_url=doc)


# ── Código da sala ───────────────────────────────────────────────────

class TestCodigoMeet:
    def test_link_gerado(self):
        assert t.codigo_meet("https://meet.google.com/abc-defg-hij") == "abc-defg-hij"

    def test_primeiro_link_do_meet_vence(self):
        assert t.codigo_meet(
            "https://zoom.us/j/1", "https://meet.google.com/xyz-abcd-efg"
        ) == "xyz-abcd-efg"

    def test_maiuscula_e_query(self):
        assert t.codigo_meet("meet.google.com/ABC-DEFG-HIJ?authuser=1") == "abc-defg-hij"

    @pytest.mark.parametrize("link", [None, "", "https://zoom.us/j/99",
                                      "https://meet.google.com/lookup/abc",
                                      "https://meet.google.com/abc-de-hij"])
    def test_sem_meet(self, link):
        assert t.codigo_meet(link) is None


# ── Janelas ──────────────────────────────────────────────────────────

class TestJanelas:
    def test_nao_procura_antes_do_fim_mais_margem(self):
        assert not t.pode_procurar(FIM, FIM + timedelta(minutes=4))
        assert t.pode_procurar(FIM, FIM + timedelta(minutes=5))

    def test_limite_da_api(self):
        assert t.dentro_do_limite_da_api(FIM, FIM + timedelta(days=29))
        assert not t.dentro_do_limite_da_api(FIM, FIM + timedelta(days=29, minutes=1))

    def test_data_sem_fuso_e_utc(self):
        """asyncpg e Google entregam UTC; nunca tratar como horário local."""
        ingenua = FIM.replace(tzinfo=None)
        assert t.pode_procurar(ingenua, FIM + timedelta(minutes=5))


# ── Conferências desta reunião ───────────────────────────────────────

class TestConferenciasDaReuniao:
    def test_ignora_uso_da_sala_em_outro_dia(self):
        """O link é reutilizável: a call de quinta com outro cliente não entra."""
        hoje = conf("c/hoje")
        quinta = conf("c/quinta", INICIO + timedelta(days=3), FIM + timedelta(days=3))
        assert [c.nome for c in t.conferencias_da_reuniao([quinta, hoje], INICIO, FIM)] == ["c/hoje"]

    def test_aceita_quem_entrou_cedo_e_a_reconexao(self):
        cedo = conf("c/1", INICIO - timedelta(minutes=50), INICIO + timedelta(minutes=5))
        volta = conf("c/2", INICIO + timedelta(minutes=10), FIM)
        nomes = [c.nome for c in t.conferencias_da_reuniao([volta, cedo], INICIO, FIM)]
        assert nomes == ["c/1", "c/2"]  # em ordem de início

    def test_muito_cedo_fica_de_fora(self):
        cedo = conf("c/1", INICIO - timedelta(hours=2), INICIO - timedelta(hours=1, minutes=30))
        assert t.conferencias_da_reuniao([cedo], INICIO, FIM) == ()


# ── A decisão ────────────────────────────────────────────────────────

class TestDecidir:
    def test_ninguem_entrou_ainda(self):
        d = t.decidir([], INICIO, FIM, FIM + timedelta(hours=2))
        assert d.acao == "aguardar"
        assert "Ninguém entrou" in d.motivo

    def test_ninguem_entrou_em_24h_desiste(self):
        d = t.decidir([], INICIO, FIM, FIM + timedelta(hours=24))
        assert d.acao == "desistir"

    def test_em_andamento(self):
        d = t.decidir([conf("c", INICIO, None)], INICIO, FIM, FIM + timedelta(minutes=20))
        assert d.acao == "aguardar"
        assert "andamento" in d.motivo

    def test_acabou_sem_transcricao_espera_meia_hora(self):
        d = t.decidir([conf()], INICIO, FIM, FIM + timedelta(minutes=10))
        assert d.acao == "aguardar"

    def test_acabou_sem_transcricao_desiste(self):
        d = t.decidir([conf()], INICIO, FIM, FIM + timedelta(minutes=30))
        assert d.acao == "desistir"
        assert "não foi ligada" in d.motivo

    def test_arquivo_pronto_coleta(self):
        c = conf("c", INICIO, FIM, tr())
        d = t.decidir([c], INICIO, FIM, FIM + timedelta(minutes=6))
        assert d.acao == "coletar"
        assert [x.nome for x in d.transcricoes] == ["conferenceRecords/a/transcripts/1"]

    def test_arquivo_gerando_espera(self):
        c = conf("c", INICIO, FIM, tr("ENDED"))
        d = t.decidir([c], INICIO, FIM, FIM + timedelta(hours=1))
        assert d.acao == "aguardar"
        assert "gerando" in d.motivo

    def test_arquivo_travado_coleta_mesmo_assim(self):
        """Seis horas depois, o que houver: as falas existem antes do Doc."""
        c = conf("c", INICIO, FIM, tr("ENDED"))
        d = t.decidir([c], INICIO, FIM, FIM + timedelta(hours=6))
        assert d.acao == "coletar"

    def test_espera_conta_do_ultimo_fim(self):
        """A chamada caiu e voltou: a espera vale a partir da segunda."""
        c1 = conf("c1", INICIO, INICIO + timedelta(minutes=10), tr(nome="c1/t"))
        c2 = conf("c2", INICIO + timedelta(minutes=12), FIM + timedelta(hours=1), tr("ENDED", "c2/t"))
        d = t.decidir([c1, c2], INICIO, FIM, FIM + timedelta(hours=6, minutes=30))
        assert d.acao == "aguardar"

    def test_conferencia_de_outro_dia_nao_conta(self):
        outra = conf("c", INICIO + timedelta(days=5), FIM + timedelta(days=5), tr())
        d = t.decidir([outra], INICIO, FIM, FIM + timedelta(days=6))
        assert d.acao == "desistir"


# ── O texto ──────────────────────────────────────────────────────────

def fala(minuto, quem, texto):
    return Fala(INICIO + timedelta(minutes=minuto), None, quem, texto)


class TestTexto:
    def test_junta_falas_seguidas_da_mesma_pessoa(self):
        falas = [fala(0, "Ana", "Bom dia."), fala(1, "Ana", "Tudo bem?"),
                 fala(2, "Rui", "Tudo.")]
        juntas = t.juntar_falas(falas)
        assert [(f.participante, f.texto) for f in juntas] == [
            ("Ana", "Bom dia. Tudo bem?"), ("Rui", "Tudo."),
        ]

    def test_ordena_por_horario_e_ignora_vazio(self):
        falas = [fala(2, "Rui", "Depois."), fala(0, "Ana", "Antes."), fala(1, "Ana", "   ")]
        assert [f.texto for f in t.juntar_falas(falas)] == ["Antes.", "Depois."]

    def test_texto_corrido_no_horario_de_brasilia(self):
        """A EC2 roda em UTC; o texto tem de dizer 09:00, não 12:00."""
        txt = t.texto_corrido([fala(0, "Ana", "Oi"), fala(3, "Rui", "Olá")])
        assert txt == "[09:00] Ana: Oi\n[09:03] Rui: Olá"

    def test_entradas_json(self):
        e = t.entradas_json([fala(0, "Ana", "Oi")])
        assert e == [{"inicio": INICIO.isoformat(), "fim": None,
                      "participante": "Ana", "texto": "Oi"}]

    @pytest.mark.parametrize("p,esperado", [
        ({"signedinUser": {"displayName": "Ana Souza"}}, "Ana Souza"),
        ({"anonymousUser": {"displayName": "Cliente XPTO"}}, "Cliente XPTO"),
        ({"phoneUser": {"displayName": "+55 11"}}, "+55 11"),
        ({"signedinUser": {"displayName": " "}}, "Participante"),
        (None, "Participante"),
    ])
    def test_nome_do_participante(self, p, esperado):
        assert t.nome_do_participante(p) == esperado

    def test_recorte_mantem_comeco_e_fim(self):
        r = t.recorte_para_ia("x" * 100 + "FIM", limite=50)
        assert r.startswith("x" * 25) and r.endswith("FIM")

    def test_data_do_google_nanossegundos(self):
        d = t.data_do_google("2026-09-24T12:00:00.123456789Z")
        assert d == datetime(2026, 9, 24, 12, 0, 0, 123456, tzinfo=UTC)

    def test_data_do_google_sem_fracao(self):
        assert t.data_do_google("2026-09-24T12:00:00Z") == INICIO


# ── Resumo: leitura e guarda numérica ────────────────────────────────

class TestResumoPuro:
    def test_le_json_limpo(self):
        r, p = resumo_reuniao.ler_resposta(
            '{"resumo": "Cliente quer PCMSO.", "proximos_passos": ["Enviar proposta"]}'
        )
        assert r == "Cliente quer PCMSO." and p == ["Enviar proposta"]

    def test_le_json_com_texto_em_volta(self):
        r, p = resumo_reuniao.ler_resposta('Aqui está:\n{"resumo": "A", "proximos_passos": []}\nfim')
        assert r == "A" and p == []

    def test_descarta_passo_que_nao_e_texto_e_limita(self):
        passos = ["p%d" % i for i in range(12)] + [3, None, ""]
        import json
        _, p = resumo_reuniao.ler_resposta(json.dumps({"resumo": "A", "proximos_passos": passos}))
        assert p == ["p%d" % i for i in range(8)]

    @pytest.mark.parametrize("bruto", [None, "", "nada", "{quebrado", '["lista"]',
                                       '{"resumo": "", "proximos_passos": []}'])
    def test_fora_do_formato(self, bruto):
        assert resumo_reuniao.ler_resposta(bruto)[0] is None

    def test_numero_da_transcricao_passa(self):
        assert resumo_reuniao.conferir_numeros(
            "A empresa tem 120 vidas.", ["Ligar dia 30"],
            "[09:00] Ana: são 120 vidas\n[09:05] Rui: te ligo dia 30", {},
        ) == []

    def test_numero_inventado_e_pego_com_o_trecho(self):
        fora = resumo_reuniao.conferir_numeros(
            "Valor de R$ 45 por vida.", [], "[09:00] Ana: vamos ver o valor", {},
        )
        assert fora[0][0] == "45"
        assert "R$ 45 por vida" in fora[0][1]

    def test_data_da_reuniao_e_permitida(self):
        ctx = resumo_reuniao.contexto_da_reuniao("XPTO", "Apresentação", INICIO)
        assert ctx == {"empresa": "XPTO", "tipo_de_reuniao": "Apresentação",
                       "data": "2026-09-24"}
        assert resumo_reuniao.conferir_numeros("Reunião de 24/09.", [], "oi", ctx) == []

    def test_contexto_usa_o_dia_de_brasilia(self):
        """23h de quarta em Brasília já é quinta em UTC."""
        tarde = datetime(2026, 9, 25, 2, 0, tzinfo=UTC)
        assert resumo_reuniao.contexto_da_reuniao(None, None, tarde) == {"data": "2026-09-24"}

    def test_payload_leva_transcricao_e_contexto(self):
        corpo = resumo_reuniao.payload("abc", {"empresa": "X"})
        assert corpo["system"] == resumo_reuniao.INSTRUCAO
        assert "abc" in corpo["messages"][0]["content"]
        assert '"empresa": "X"' in corpo["messages"][0]["content"]


class TestResumoSemChave:
    async def test_sem_chave_devolve_erro_sem_chamar_rede(self, monkeypatch):
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "")
        r = await resumo_reuniao.resumir("[09:00] Ana: oi", {})
        assert r.resumo is None and "ANTHROPIC_API_KEY" in r.erro

    async def test_texto_vazio(self, monkeypatch):
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "x")
        r = await resumo_reuniao.resumir("   ", {})
        assert "vazia" in r.erro


class _RespIA:
    def __init__(self, status, texto):
        self.status_code = status
        self.text = texto
        self._texto = texto

    def json(self):
        return {"content": [{"type": "text", "text": self._texto}]}


def _cliente_falso(resposta, capturado):
    class Cliente:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            capturado["url"] = url
            capturado["corpo"] = json
            return resposta
    return Cliente


class TestResumirComIAFalsa:
    TEXTO = "[09:00] Ana: são 120 vidas\n[09:02] Rui: mando a proposta amanhã"

    async def test_resumo_valido(self, monkeypatch):
        cap = {}
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "k")
        monkeypatch.setattr(resumo_reuniao.httpx, "AsyncClient", _cliente_falso(
            _RespIA(200, '{"resumo": "Empresa com 120 vidas.", '
                         '"proximos_passos": ["Rui manda a proposta"]}'), cap))
        r = await resumo_reuniao.resumir(self.TEXTO, {"empresa": "XPTO"})
        assert r.erro is None
        assert r.resumo == "Empresa com 120 vidas."
        assert r.proximos_passos == ("Rui manda a proposta",)
        assert cap["url"] == resumo_reuniao.ia.URL_API
        assert "120 vidas" in cap["corpo"]["messages"][0]["content"]

    async def test_numero_inventado_descarta(self, monkeypatch):
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "k")
        monkeypatch.setattr(resumo_reuniao.httpx, "AsyncClient", _cliente_falso(
            _RespIA(200, '{"resumo": "Valor de R$ 45 por vida.", "proximos_passos": []}'), {}))
        r = await resumo_reuniao.resumir(self.TEXTO, {})
        assert r.resumo is None
        assert "45" in r.erro and "descartado" in r.erro

    async def test_http_de_erro(self, monkeypatch):
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "k")
        monkeypatch.setattr(resumo_reuniao.httpx, "AsyncClient", _cliente_falso(
            _RespIA(529, "overloaded"), {}))
        r = await resumo_reuniao.resumir(self.TEXTO, {})
        assert r.erro == "A IA respondeu HTTP 529."

    async def test_fora_do_formato(self, monkeypatch):
        monkeypatch.setattr(resumo_reuniao.settings, "ANTHROPIC_API_KEY", "k")
        monkeypatch.setattr(resumo_reuniao.httpx, "AsyncClient", _cliente_falso(
            _RespIA(200, "Não consigo."), {}))
        r = await resumo_reuniao.resumir(self.TEXTO, {})
        assert "formato" in r.erro
