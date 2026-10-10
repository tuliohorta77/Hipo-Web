"""
HIPO Gravador — o que dá para testar fora do Windows.

A captura de áudio e a leitura do mixer só existem no Windows; o resto
(detecção de início/fim, alinhamento dos canais, FLAC, fila, envio e as
respostas do HIPO) é Python puro e roda aqui.

    cd gravador && python -m pytest -q tests
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config as cfgmod  # noqa: E402
from app.captura import Alinhador, juntar_canais, salvar_flac  # noqa: E402
from app.cliente import (  # noqa: E402
    ArquivoNaoChegou, Cliente, GravacaoRecusada, Indisponivel, NaoEncontrada, TokenInvalido,
)
from app.deteccao import MaquinaDeChamada, Sessao, casa_processo, softphone_ativo  # noqa: E402
from app.envio import Enviador  # noqa: E402
from app.fila import Fila, espera_apos_falha  # noqa: E402


# ── Detecção ─────────────────────────────────────────────────────────


class TestMaquina:
    def test_inicio_e_fim_depois_do_silencio(self):
        m = MaquinaDeChamada(fim_apos_s=4)
        assert m.atualizar(False, 0) is None
        ev = m.atualizar(True, 10)
        assert ev.tipo == "inicio" and ev.inicio == 10
        assert m.atualizar(True, 60) is None
        assert m.atualizar(False, 62) is None          # pausa curta não derruba
        assert m.atualizar(True, 63) is None
        assert m.atualizar(False, 65) is None
        fim = m.atualizar(False, 67.5)
        assert fim.tipo == "fim" and fim.inicio == 10 and fim.fim == 63
        assert not m.gravando

    def test_teto_de_duracao(self):
        m = MaquinaDeChamada(fim_apos_s=4, max_duracao_s=100)
        m.atualizar(True, 0)
        ev = m.atualizar(True, 100)
        assert ev.tipo == "fim"

    def test_forcar_fim(self):
        m = MaquinaDeChamada()
        assert m.forcar_fim(5) is None
        m.atualizar(True, 1)
        assert m.forcar_fim(5).fim == 5

    def test_processo_e_fluxo(self):
        sessoes = [
            Sessao("saida", 1, "Accession Communicator.exe", True, "d"),
            Sessao("microfone", 2, "Teams.exe", True, "d"),
        ]
        assert not softphone_ativo(sessoes, ["accession"], "microfone")   # só a saída tocando
        assert softphone_ativo(sessoes, ["accession"], "saida")
        sessoes.append(Sessao("microfone", 1, "Accession Communicator.exe", True, "d"))
        assert softphone_ativo(sessoes, ["accession"], "microfone")
        assert casa_processo("MaX UC.exe", cfgmod.PROCESSOS_PADRAO)
        assert not casa_processo("chrome.exe", cfgmod.PROCESSOS_PADRAO)


# ── Áudio ────────────────────────────────────────────────────────────


class TestAudio:
    def test_alinhador_preenche_buraco_antes_do_bloco(self):
        a = Alinhador(taxa=100, folga_s=0.2)
        a.adicionar(np.ones(100, dtype="float32"), 1.0)
        # 2 s sem nada, e chega um bloco de 0,1 s aos 3,1 s.
        a.adicionar(np.ones(10, dtype="float32"), 3.1)
        s = a.sinal()
        assert len(s) == 310 and s.dtype == np.int16
        assert (s[100:300] == 0).all() and (s[300:] == 32767).all()

    def test_alinhador_tolera_atraso_pequeno(self):
        a = Alinhador(taxa=100, folga_s=0.5)
        a.adicionar(np.ones(100, dtype="float32"), 1.3)
        assert len(a.sinal()) == 100

    def test_juntar_canais_e_flac(self, tmp_path):
        esq = np.full(1600, 0.5, dtype="float32")
        dir_ = np.full(800, -2.0, dtype="float32")                # passa do limite: corta
        est = juntar_canais(esq, dir_)
        assert est.shape == (1600, 2) and est.dtype == np.int16
        assert est[0, 1] == -32767 and est[1000, 1] == 0
        tam = salvar_flac(tmp_path / "x.flac", est, 16000)
        assert tam > 0
        import soundfile as sf
        lido, taxa = sf.read(str(tmp_path / "x.flac"), dtype="int16")
        assert taxa == 16000 and lido.shape == (1600, 2)


# ── Config ───────────────────────────────────────────────────────────


def test_config_ida_e_volta(tmp_path):
    c = cfgmod.Config(url="https://x.test/api/", token="hipograv_abc")
    cfgmod.salvar(c, tmp_path / "c.json")
    lido = cfgmod.carregar(tmp_path / "c.json")
    assert lido.url == "https://x.test/api" and lido.ok()
    (tmp_path / "ruim.json").write_text("{nao e json", encoding="utf-8")
    assert cfgmod.carregar(tmp_path / "ruim.json").token == ""
    assert not cfgmod.Config(token="eyJ").ok()


# ── Fila ─────────────────────────────────────────────────────────────


def nova(fila, inicio="2026-10-09T15:00:00+00:00"):
    i = fila.novo_id()
    fila.audio(i).write_bytes(b"flac")
    fila.adicionar(i, {"inicio": inicio, "inicio_ts": 1.0, "fim_ts": 61.0, "duracao_s": 60.0})
    return i


class TestFila:
    def test_ordem_espera_e_descarte(self, tmp_path):
        f = Fila(tmp_path)
        b = nova(f, "2026-10-09T16:00:00+00:00")
        a = nova(f, "2026-10-09T15:00:00+00:00")
        assert [m["id"] for m in f.pendentes()] == [a, b]
        f.falhou(f.pendentes()[0], agora=1000)
        assert [m["id"] for m in f.pendentes(agora=1001)] == [b]
        assert len(f.pendentes(agora=1000 + 31)) == 2
        f.descartar(a, "curta")
        assert (tmp_path / "descartadas" / f"{a}.motivo.txt").read_text() == "curta"
        assert f.quantidade() == 1

    def test_metadado_sem_audio_some(self, tmp_path):
        f = Fila(tmp_path)
        i = nova(f)
        f.audio(i).unlink()
        assert f.pendentes() == [] and f.quantidade() == 0

    def test_prazo_de_7_dias(self, tmp_path):
        f = Fila(tmp_path)
        i = nova(f)
        meta = json.loads((f.pasta / f"{i}.json").read_text())
        assert f.limpar(agora=meta["criado_em"] + 8 * 86400) == 1
        assert f.quantidade() == 0

    def test_espera_crescente(self):
        assert espera_apos_falha(1) == 30 and espera_apos_falha(20) == 1800


# ── Envio ────────────────────────────────────────────────────────────


class ClienteFalso:
    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.chamadas = []

    def _r(self, nome, padrao):
        r = self.respostas.get(nome, padrao)
        if isinstance(r, list):
            r = r.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def nova_gravacao(self, meta, tamanho, agora=None):
        self.chamadas.append(("nova", meta["id"], tamanho))
        return self._r("nova", {"ligacao_id": "L1", "upload_url": "https://s3/x",
                                "content_type": "audio/flac", "vinculada": True})

    def subir(self, url, arquivo, tipo):
        self.chamadas.append(("subir", url, tipo))
        return self._r("subir", None)

    def concluir(self, lid):
        self.chamadas.append(("concluir", lid))
        return self._r("concluir", {"status": "transcrevendo"})


class TestEnvio:
    def test_caminho_feliz_apaga_da_maquina(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        c = ClienteFalso()
        assert Enviador(f, c).passo() == 1
        assert [x[0] for x in c.chamadas] == ["nova", "subir", "concluir"]
        assert f.quantidade() == 0

    def test_ja_recebida_so_apaga(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        c = ClienteFalso({"nova": {"ligacao_id": "L1", "ja_recebida": True}})
        Enviador(f, c).passo()
        assert [x[0] for x in c.chamadas] == ["nova"] and f.quantidade() == 0

    def test_servidor_fora_reagenda_e_para(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        nova(f, "2026-10-09T17:00:00+00:00")
        c = ClienteFalso({"nova": Indisponivel("503")})
        e = Enviador(f, c)
        assert e.passo(agora=100) == 0
        assert len(c.chamadas) == 1                          # não martelou a segunda
        assert e.ultimo_erro == "503"
        assert len(f.pendentes(agora=101)) == 1

    def test_recusada_descarta_e_segue(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        nova(f, "2026-10-09T17:00:00+00:00")
        c = ClienteFalso({"nova": [GravacaoRecusada("curta"), {"ligacao_id": "L2",
                          "upload_url": "u", "content_type": "audio/flac"}]})
        assert Enviador(f, c).passo() == 1
        assert f.quantidade() == 0
        assert len(list((tmp_path / "descartadas").glob("*.motivo.txt"))) == 1

    def test_token_invalido_para_tudo(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        e = Enviador(f, ClienteFalso({"nova": TokenInvalido("revogado")}))
        e.passo()
        assert e.token_invalido and f.quantidade() == 1
        assert e.passo() == 0

    def test_descartada_no_hipo_apaga_daqui_sem_recriar(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        c = ClienteFalso({"concluir": NaoEncontrada("descartada")})
        assert Enviador(f, c).passo() == 0
        assert f.quantidade() == 0
        assert [x[0] for x in c.chamadas] == ["nova", "subir", "concluir"]

    def test_arquivo_nao_chegou_sobe_de_novo(self, tmp_path):
        f = Fila(tmp_path)
        nova(f)
        c = ClienteFalso({"concluir": [ArquivoNaoChegou("x"), {"status": "transcrevendo"}]})
        assert Enviador(f, c).passo() == 1
        assert [x[0] for x in c.chamadas] == ["nova", "subir", "concluir", "subir", "concluir"]


# ── Cliente HTTP ─────────────────────────────────────────────────────


class Resp:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self._corpo = corpo or {}
        self.text = json.dumps(self._corpo)

    def json(self):
        return self._corpo


class SessaoFalsa:
    def __init__(self, resp):
        self.headers = {}
        self.resp = resp
        self.pedidos = []

    def post(self, url, json=None, timeout=None):
        self.pedidos.append((url, json))
        return self.resp


@pytest.mark.parametrize("status,erro", [
    (401, TokenInvalido), (422, GravacaoRecusada), (409, ArquivoNaoChegou), (404, NaoEncontrada),
    (503, Indisponivel), (500, Indisponivel),
])
def test_cliente_traduz_status(status, erro):
    c = Cliente("https://h.test/api/", "hipograv_x", "1.0.0", sessao=SessaoFalsa(Resp(status, {"detail": "d"})))
    with pytest.raises(erro):
        c.pulso()


def test_cliente_manda_o_relogio_do_momento_do_pedido(monkeypatch):
    import app.cliente as cl
    s = SessaoFalsa(Resp(200, {"ligacao_id": "L"}))
    c = Cliente("https://h.test/api", "hipograv_x", "1.0.0", sessao=s)
    monkeypatch.setattr(cl.time, "time", lambda: 86400.0)
    c.nova_gravacao({"id": "abc12345", "inicio_ts": 0, "fim_ts": 60, "duracao_s": 60}, 1)
    assert s.pedidos[0][1]["agora"] == "1970-01-02T00:00:00+00:00"


def test_cliente_monta_o_pedido_da_gravacao():
    s = SessaoFalsa(Resp(200, {"ligacao_id": "L"}))
    c = Cliente("https://h.test/api", "hipograv_x", "1.0.0", sessao=s)
    assert s.headers["Authorization"] == "Bearer hipograv_x"
    c.nova_gravacao({"id": "abc12345", "inicio_ts": 0, "fim_ts": 60, "duracao_s": 60.04}, 999, 61)
    url, corpo = s.pedidos[0]
    assert url == "https://h.test/api/ligacoes/gravador/gravacoes"
    assert corpo["inicio"] == "1970-01-01T00:00:00+00:00"
    assert corpo["duracao_s"] == 60.0 and corpo["tamanho_bytes"] == 999
    assert corpo["id_local"] == "abc12345" and corpo["formato"] == "flac"
