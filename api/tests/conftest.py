"""
Fixtures compartilhadas para todos os testes do HIPO.
Usa banco PostgreSQL de teste isolado — não toca no banco de produção.
"""
import os
import pytest
import asyncpg
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_URL", "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-hipo-2026")
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")
os.environ.setdefault("UPLOAD_DIR", "/tmp/hipo_test_uploads")

from main import app


@pytest.fixture
async def db_conn():
    """
    Conexão direta por teste — evita conflito de event loop do pytest-asyncio.
    Cada teste recebe uma conexão limpa e independente.
    """
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    await conn.execute("""
        TRUNCATE TABLE
            po_linhas,
            po_uploads,
            po_projecao_semanal,
            repasse_calendario,
            cromie_cliente_final,
            cromie_tarefa_cliente,
            cromie_contador,
            cromie_tarefa_contador,
            cromie_uploads,
            pex_snapshot,
            pex_compliance_gaps,
            pex_metas_mensais,
            bd_ativados,
            bd_ativados_upload,
            usuarios
        CASCADE
    """)
    yield conn
    await conn.close()


@pytest.fixture
async def client():
    """Cliente HTTP assíncrono para testar os endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def usuario_adm(db_conn, client):
    """Cria um usuário ADM de teste e retorna o token JWT."""
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"]).hash("senha123")
    await db_conn.execute("""
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('ADM Teste', 'adm@teste.com', $1, 'ADM')
    """, pwd)
    resp = await client.post(
        "/auth/login",
        data={"username": "adm@teste.com", "password": "senha123"}
    )
    token = resp.json()["access_token"]
    return {
        "email": "adm@teste.com",
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"}
    }


@pytest.fixture
async def meta_abril(db_conn):
    """Insere metas de Abril/2026 para os cálculos do PEX."""
    await db_conn.execute("""
        INSERT INTO pex_metas_mensais
            (mes_ref, nmrr_meta, demos_outbound_meta,
             dias_uteis, ecs_ativos_m3, evs_ativos,
             carteira_total_contadores)
        VALUES ('2026-04', 41044, 100, 22, 2, 1, 120)
    """)