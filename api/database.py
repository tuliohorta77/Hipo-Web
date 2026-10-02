"""
HIPO -- acesso ao Postgres.

CAMINHO NORMAL: pool asyncpg criado no lifespan de main.py e guardado em
app.state.pool (um por worker). `get_conn` pega uma conexao do pool e
devolve no fim da request -- sem abrir socket a cada chamada.

FALLBACK: sem pool em app.state, abre conexao direta e fecha no fim, que e
exatamente o que este arquivo fazia antes. Cai aqui quando:
  - a suite roda (o conftest sobe o cliente com lifespan DESABILITADO);
  - o pool nao conseguiu subir no boot (banco fora, rede travada).
Nos dois casos as rotas seguem respondendo.

Os routers continuam com `conn=Depends(get_conn)`: o FastAPI injeta a
conexao HTTP sozinho. `HTTPConnection`, e nao `Request`, para servir tambem
a uma rota WebSocket se um dia existir.
"""
from __future__ import annotations

import asyncpg
from starlette.requests import HTTPConnection

from config import settings


async def criar_pool() -> asyncpg.Pool:
    """Pool do worker, com os limites do .env. Levanta excecao se falhar."""
    return await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
        command_timeout=settings.DB_COMMAND_TIMEOUT_S or None,
    )


async def get_conn(conexao: HTTPConnection):
    pool: asyncpg.Pool | None = getattr(conexao.app.state, "pool", None)

    if pool is not None:
        async with pool.acquire() as conn:
            yield conn
        return

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()
