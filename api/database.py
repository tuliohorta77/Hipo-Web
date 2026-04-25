import asyncpg
from config import settings

_pool = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=2,
            max_size=20,
            command_timeout=60,
        )
    return _pool

async def get_conn():
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
