"""
Pool asyncpg por worker + CORS por ambiente.

O resto da suite roda com lifespan DESABILITADO (ver conftest) e por isso
so exercita o fallback de connect-por-request. Aqui ficam:

  - o caminho do pool em `get_conn` (conexao sai e volta para o pool);
  - o fallback sem pool;
  - o lifespan criando, usando e FECHANDO o pool -- e devolvendo
    app.state.pool para None, sem o que os testes seguintes tentariam usar
    um pool morto;
  - o lifespan subindo mesmo com o banco fora;
  - as regras de `resolver_origens_cors`.
"""
from types import SimpleNamespace

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

import config
import database
from config import ORIGENS_PRODUCAO, resolver_origens_cors
from main import app


def _conexao_falsa(pool):
    """O minimo de HTTPConnection que `get_conn` le: .app.state.pool."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(pool=pool)))


# ---------------------------------------------------------------------------
# get_conn
# ---------------------------------------------------------------------------

async def test_get_conn_usa_o_pool_e_devolve_a_conexao():
    pool = await asyncpg.create_pool(config.settings.DATABASE_URL, min_size=1, max_size=2)
    try:
        gen = database.get_conn(_conexao_falsa(pool))
        conn = await gen.__anext__()
        assert await conn.fetchval("SELECT 1") == 1
        # Emprestada: o pool nao a tem livre.
        assert pool.get_idle_size() == pool.get_size() - 1

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        # Devolvida no fim da request.
        assert pool.get_idle_size() == pool.get_size()
    finally:
        await pool.close()


async def test_get_conn_sem_pool_abre_e_fecha_conexao_propria():
    gen = database.get_conn(_conexao_falsa(None))
    conn = await gen.__anext__()
    assert await conn.fetchval("SELECT 1") == 1
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert conn.is_closed()


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------

async def test_lifespan_cria_usa_e_fecha_o_pool(db_conn, monkeypatch):
    # Sem a task de descarga periodica: o teste e sobre o pool.
    monkeypatch.setattr(config.settings, "TELEMETRIA_ATIVA", False)
    assert app.state.pool is None

    async with app.router.lifespan_context(app):
        pool = app.state.pool
        assert pool is not None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # /auth/login passa por Depends(get_conn): usuario inexistente
            # da 401 DEPOIS de consultar o banco pelo pool.
            r = await c.post(
                "/auth/login",
                data={"username": "ninguem@teste.com", "password": "x"},
            )
            assert r.status_code == 401
            assert (await c.get("/health")).json()["pool"] is True
        assert pool.get_idle_size() == pool.get_size()

    assert pool.is_closing()
    # O ponto que quebraria o resto da suite: nada de pool morto em app.state.
    assert app.state.pool is None


async def test_depois_do_lifespan_as_rotas_voltam_ao_fallback(db_conn, client, monkeypatch):
    monkeypatch.setattr(config.settings, "TELEMETRIA_ATIVA", False)
    async with app.router.lifespan_context(app):
        pass

    r = await client.post(
        "/auth/login",
        data={"username": "ninguem@teste.com", "password": "x"},
    )
    assert r.status_code == 401


async def test_lifespan_sobe_sem_banco_e_cai_no_fallback(monkeypatch):
    monkeypatch.setattr(config.settings, "TELEMETRIA_ATIVA", False)
    # Porta 1: conexao recusada na hora, sem esperar timeout.
    monkeypatch.setattr(
        config.settings, "DATABASE_URL", "postgresql://x:y@127.0.0.1:1/nada"
    )

    async with app.router.lifespan_context(app):
        assert app.state.pool is None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/health")
            assert r.status_code == 200
            assert r.json()["pool"] is False

    assert app.state.pool is None


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class TestResolverOrigensCors:
    def test_producao_vazio_usa_o_dominio_do_hipo(self):
        assert resolver_origens_cors("", "production") == list(ORIGENS_PRODUCAO)

    def test_producao_descarta_curinga(self):
        assert resolver_origens_cors("*", "production") == list(ORIGENS_PRODUCAO)
        assert resolver_origens_cors("*, https://a.com", "production") == ["https://a.com"]

    def test_producao_respeita_lista_explicita(self):
        assert resolver_origens_cors(
            "https://a.com, https://b.com", "production"
        ) == ["https://a.com", "https://b.com"]

    def test_fora_de_producao_vazio_libera_tudo(self):
        assert resolver_origens_cors("", "test") == ["*"]
        assert resolver_origens_cors("  ,  ", "development") == ["*"]

    def test_fora_de_producao_lista_explicita_vale(self):
        assert resolver_origens_cors("http://localhost:5173", "development") == [
            "http://localhost:5173"
        ]

    def test_barra_final_e_espaco_caem_fora(self):
        assert resolver_origens_cors(" https://a.com/ ,", "production") == ["https://a.com"]

    def test_none_tratado_como_vazio(self):
        assert resolver_origens_cors(None, "production") == list(ORIGENS_PRODUCAO)


async def test_preflight_responde_com_a_origem_em_ambiente_de_teste(client):
    # Na suite ENVIRONMENT=test, entao "*": o preflight devolve a origem.
    r = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")
