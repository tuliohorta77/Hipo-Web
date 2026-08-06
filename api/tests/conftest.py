"""
Fixtures para testes do HIPO.

A fixture db_conn trunca 'usuarios' com CASCADE. Como toda tabela do CRM
tem FK para usuarios (criado_por), o CASCADE varre o banco inteiro numa
tacada: contas, contatos, oportunidades, listas de domínio e dia_nao_util.

Isso é intencional — cada teste começa do zero. Testes que precisem de
feriados, verticais ou qualquer dado de apoio devem criá-los eles mesmos.

Usa anyio_backend + loop por função para evitar conflito de event loop
com asyncpg no pytest-asyncio 0.23.
"""
import os

import asyncpg
import bcrypt
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_URL", "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-hipo-2026")
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")

_SENHA_TESTE = "test123"
_DB_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# SAFEGUARD DE PRODUÇÃO
# ---------------------------------------------------------------------------
# A fixture `db_conn` executa TRUNCATE ... CASCADE. Se a suíte rodar
# acidentalmente apontada para o banco de produção (hipo-db no AWS RDS),
# todos os usuários seriam apagados e ninguém mais conseguiria logar.
#
# Este bloco aborta a sessão ANTES de coletar qualquer teste ou abrir
# qualquer conexão. A checagem roda no import do conftest.
#
# Escotilha de emergência: HIPO_PERMITIR_DB_REMOTO=1 desativa o bloqueio
# conscientemente. Use apenas para um banco remoto que NÃO é produção.
# ---------------------------------------------------------------------------
_MARCADORES_PRODUCAO = ("amazonaws.com", "hipo-db")


def _abortar_se_producao(db_url: str) -> None:
    if os.environ.get("HIPO_PERMITIR_DB_REMOTO") == "1":
        return
    url_lower = (db_url or "").lower()
    encontrados = [m for m in _MARCADORES_PRODUCAO if m in url_lower]
    if encontrados:
        pytest.exit(
            "\n"
            "================================================================\n"
            " ABORTADO: DATABASE_URL aponta para um banco de PRODUCAO.\n"
            "================================================================\n"
            f" Marcador(es) detectado(s): {', '.join(encontrados)}\n"
            "\n"
            " A suite executa TRUNCATE CASCADE em 'usuarios'. Rodar contra\n"
            " producao apagaria TODOS os dados: logins, contas, contatos\n"
            " e oportunidades.\n"
            "\n"
            " Use um banco de teste local ou o container do CI.\n"
            " DATABASE_URL de teste esperada aponta para 'localhost'.\n"
            "\n"
            " Se realmente precisa rodar contra um banco remoto que NAO\n"
            " e producao, defina HIPO_PERMITIR_DB_REMOTO=1 no ambiente.\n"
            "================================================================\n",
            returncode=1,
        )


# Executado no import do conftest, antes de qualquer fixture.
_abortar_se_producao(_DB_URL)


from main import app  # noqa: E402  (import após o safeguard, de propósito)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_conn():
    """
    Conexão direta por teste, com event loop próprio.

    O CASCADE puxa todo o CRM junto: contas, contatos, conta_contatos,
    oportunidades e derivados, listas de domínio e dia_nao_util — todas têm
    FK para usuarios.
    """
    conn = await asyncpg.connect(_DB_URL)
    await conn.execute("TRUNCATE TABLE usuarios CASCADE")
    yield conn
    await conn.close()


@pytest.fixture
async def client():
    """
    Cliente HTTP com lifespan desabilitado — evita que uma conexão asyncpg
    da aplicação seja criada no event loop errado.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=True),
        base_url="http://test",
    ) as c:
        yield c


async def criar_usuario(db_conn, client, cargo: str, email: str | None = None) -> dict:
    """
    Cria um usuário com o cargo pedido, faz login e devolve token + headers.

    Helper compartilhado entre os módulos de teste. Mantido no conftest para
    que os testes do CRM (Sprint 1 em diante) reaproveitem sem duplicar.
    """
    email = email or f"user-{cargo.lower()}@teste.com"
    pwd_hash = bcrypt.hashpw(_SENHA_TESTE.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ($1, $2, $3, $4)
        """,
        f"Test {cargo}", email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA_TESTE},
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "email": email,
        "cargo": cargo,
        "senha": _SENHA_TESTE,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def usuario_adm(db_conn, client):
    return await criar_usuario(db_conn, client, "ADM", "adm@teste.com")


@pytest.fixture
async def usuario_franqueado(db_conn, client):
    return await criar_usuario(db_conn, client, "Franqueado", "franqueado@teste.com")
