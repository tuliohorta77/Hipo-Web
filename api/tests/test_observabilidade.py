"""
HIPO -- observabilidade (032): Sentry.

O que esta suite protege:

  1. Sem DSN, nada liga; sem o pacote, a API sobe igual.
  2. O que sai para o Sentry nao carrega dado pessoal: querystring, corpo,
     cookie, Authorization e e-mail do usuario sao cortados.
  3. Com o SDK de verdade, um 500 e um log.error viram evento -- e o evento
     ja sai podado.

O teste (3) roda num SUBPROCESSO. `sentry_sdk.init` pendura integracoes
em classes do Starlette e no logging do processo inteiro; ligado no meio
da suite, mudaria o comportamento de todo teste que viesse depois.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from services import observabilidade

API_DIR = Path(__file__).resolve().parent.parent


class TestLimparEvento:
    def test_corta_o_que_carrega_dado_pessoal(self):
        evento = {
            "request": {
                "url": "https://hipogestao.com.br/api/crm/contatos?q=maria",
                "query_string": "q=maria%40alfa.com",
                "data": {"nome": "Maria", "telefone": "11999990000"},
                "cookies": {"s": "1"},
                "headers": {
                    "Authorization": "Bearer eyJ...",
                    "X-Real-IP": "200.1.2.3",
                    "User-Agent": "Mozilla",
                },
            },
            "user": {"id": "u1", "email": "x@y.com", "ip_address": "1.2.3.4"},
        }
        limpo = observabilidade.limpar_evento(evento)
        req = limpo["request"]
        assert req["url"] == "https://hipogestao.com.br/api/crm/contatos"
        assert req["query_string"] == "[cortado]"
        assert "data" not in req and "cookies" not in req
        assert req["headers"]["Authorization"] == "[cortado]"
        assert req["headers"]["X-Real-IP"] == "[cortado]"
        assert req["headers"]["User-Agent"] == "Mozilla"
        assert limpo["user"] == {"id": "u1"}

    def test_evento_sem_request_passa_intacto(self):
        evento = {"message": "x", "level": "error"}
        assert observabilidade.limpar_evento(dict(evento)) == evento


class TestIniciar:
    def test_sem_dsn_nao_liga(self):
        assert observabilidade.iniciar("", ambiente="x", release="r") is False
        assert observabilidade.iniciar("   ", ambiente="x", release="r") is False

    def test_sem_pacote_nao_derruba(self, monkeypatch):
        import builtins

        original = builtins.__import__

        def sem_sentry(nome, *a, **k):
            if nome.startswith("sentry_sdk"):
                raise ImportError("No module named 'sentry_sdk'")
            return original(nome, *a, **k)

        monkeypatch.setattr(builtins, "__import__", sem_sentry)
        assert observabilidade.iniciar(
            "https://chave@o0.ingest.sentry.io/0", ambiente="x", release="r",
        ) is False

    def test_ambiente_padrao(self):
        assert observabilidade.ambiente_padrao("production", "") == "production"
        assert observabilidade.ambiente_padrao("production", "MOS") == "production-mos"
        assert observabilidade.ambiente_padrao("", "") == "production"

    def test_marcar_usuario_sem_sentry_e_no_op(self):
        observabilidade.marcar_usuario({"id": "x", "cargo": "ADM"})


async def test_health_mostra_o_estado(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["sentry"] is False


# ── SDK de verdade, em processo separado ───────────────────────────────

_SCRIPT = textwrap.dedent(
    """
    import asyncio, json, logging, os, sys
    sys.path.insert(0, os.environ["API_DIR"])

    import sentry_sdk
    from sentry_sdk.transport import Transport

    capturados = []

    class Captura(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    capturados.append(item.payload.json)

    # Pendura o transporte falso no init que observabilidade.iniciar faz.
    _init = sentry_sdk.init
    def init_com_captura(*a, **k):
        k["transport"] = Captura
        return _init(*a, **k)
    sentry_sdk.init = init_com_captura

    from services import observabilidade
    assert observabilidade.iniciar(
        "https://chave@o0.ingest.sentry.io/0",
        ambiente="teste", release="hipo-api@teste", instancia="MOS",
    )

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    app = FastAPI()

    @app.get("/explode")
    async def explode(q: str = ""):
        raise RuntimeError("falhou de proposito")

    async def main():
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://t",
        ) as c:
            r = await c.get(
                "/explode", params={"q": "maria@alfa.com"},
                headers={"Authorization": "Bearer segredo"},
            )
            assert r.status_code == 500, r.status_code
        logging.getLogger("hipo.qualquer").error("deu ruim no fechamento")
        sentry_sdk.flush(2)

    asyncio.run(main())
    print(json.dumps(capturados))
    """
)


def test_sdk_de_verdade_captura_e_poda():
    pytest.importorskip("sentry_sdk")
    env = {**os.environ, "API_DIR": str(API_DIR)}
    saida = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True, text=True, env=env, cwd=str(API_DIR), timeout=60,
    )
    assert saida.returncode == 0, saida.stderr[-2000:]
    eventos = json.loads(saida.stdout.strip().splitlines()[-1])

    excecoes = [e for e in eventos if e.get("exception")]
    logs = [e for e in eventos if (e.get("logentry") or {}).get("message") == "deu ruim no fechamento"
            or e.get("message") == "deu ruim no fechamento"]
    assert excecoes, eventos
    assert logs, eventos

    ev = excecoes[0]
    bruto = json.dumps(ev)
    assert "maria@alfa.com" not in bruto
    assert "segredo" not in bruto
    assert ev["environment"] == "teste"
    assert ev["release"] == "hipo-api@teste"
    assert ev["tags"]["instancia"] == "MOS"
    # Sem variavel local de frame no stack trace.
    for exc in ev["exception"]["values"]:
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            assert "vars" not in frame
