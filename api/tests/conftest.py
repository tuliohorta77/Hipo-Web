"""
Fixtures para testes do HIPO.
Usa anyio_backend + loop por função para evitar conflito de event loop
com asyncpg no pytest-asyncio 0.23.
"""
import os
import asyncio
import pytest
import asyncpg
import bcrypt
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_URL", "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-hipo-2026")
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")
os.environ.setdefault("UPLOAD_DIR", "/tmp/hipo_test_uploads")

from main import app

_SENHA_TESTE = "test123"
_DB_URL = os.environ["DATABASE_URL"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_conn():
    """Conexão direta por teste com event loop próprio."""
    conn = await asyncpg.connect(_DB_URL)
    # NOTA: pex_metas_mensais agora é VIEW (não TRUNCATE).
    # Limpamos pex_metas_cabecalho com CASCADE — isso puxa pex_metas_indicadores e pex_metas_big3.
    await conn.execute("""
        TRUNCATE TABLE
            po_linhas, po_uploads, po_projecao_semanal, repasse_calendario,
            cromie_cliente_final, cromie_tarefa_cliente, cromie_contador,
            cromie_tarefa_contador, cromie_uploads, pex_snapshot,
            pex_compliance_gaps,
            pex_metas_big3, pex_metas_indicadores, pex_metas_cabecalho,
            bd_ativados, bd_ativados_upload, usuarios
        CASCADE
    """)
    yield conn
    await conn.close()


@pytest.fixture
async def client():
    """
    Cliente HTTP com lifespan desabilitado — evita que o pool asyncpg
    da aplicação seja criado no event loop errado.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=True),
        base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def usuario_adm(db_conn, client):
    pwd_hash = bcrypt.hashpw(_SENHA_TESTE.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute("""
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('ADM Teste', 'adm@teste.com', $1, 'ADM')
    """, pwd_hash)
    resp = await client.post(
        "/auth/login",
        data={"username": "adm@teste.com", "password": _SENHA_TESTE}
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "email": "adm@teste.com",
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"}
    }


@pytest.fixture
async def meta_abril(db_conn):
    """
    Cadastra meta de abril/2026 no novo modelo (cabecalho + indicadores).
    Equivalente ao INSERT antigo em pex_metas_mensais.
    """
    cab_id = await db_conn.fetchval("""
        INSERT INTO pex_metas_cabecalho
            (mes_ref, cluster_unidade, dias_uteis, ecs_ativos_m3, evs_ativos,
             carteira_total_contadores, apps_ativos)
        VALUES ('2026-04', 'BASE', 22, 2, 1, 120, 100)
        RETURNING id
    """)
    # Metas numéricas dos 5 indicadores editáveis
    await db_conn.executemany("""
        INSERT INTO pex_metas_indicadores (cabecalho_id, codigo, meta_valor)
        VALUES ($1, $2, $3)
    """, [
        (cab_id, 'nmrr', 41044),
        (cab_id, 'demos_outbound', 100),
        (cab_id, 'integracao_contabil', 5),  # Cluster BASE = 5
        (cab_id, 'eventos', 3),              # Cluster BASE = 3
    ])
    # Big3 placeholder (3 ações vazias, não atingidas)
    await db_conn.executemany("""
        INSERT INTO pex_metas_big3 (cabecalho_id, ordem, descricao, atingiu)
        VALUES ($1, $2, $3, $4)
    """, [
        (cab_id, 1, "Ação teste 1", False),
        (cab_id, 2, "Ação teste 2", False),
        (cab_id, 3, "Ação teste 3", False),
    ])
    return cab_id