import asyncpg
from config import settings


async def get_conn():
    """
    Cria uma conexão direta por request — sem pool global.
    Isso evita conflito de event loop nos testes e é seguro
    com uvicorn workers (cada worker tem seu próprio loop).
    Em produção com carga alta, trocar por pool por worker via lifespan.
    """
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()