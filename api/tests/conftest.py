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
# Custo do bcrypt na suite. 4 e o minimo do algoritmo e derruba a
# operacao de ~277ms para ~1ms. Com 1214 testes criando usuario e
# logando (2 operacoes cada), e a diferenca entre 8m11s e 1m55s de
# pytest. Precisa vir ANTES do import de config/main, que le o
# ambiente uma vez so.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# 052: os PDFs de proposta ficam em cache em disco. Na suite, uma pasta
# propria e descartavel -- teste que simula o LibreOffice nao pode deixar
# PDF falso no cache de quem roda o HIPO na mesma maquina.
import tempfile as _tempfile  # noqa: E402
os.environ.setdefault("HIPO_CACHE_PROPOSTAS", _tempfile.mkdtemp(prefix="hipo-teste-pdf-"))

_SENHA_TESTE = "test123"
_DB_URL = os.environ["DATABASE_URL"]
_ROUNDS = int(os.environ["BCRYPT_ROUNDS"])


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


# ---------------------------------------------------------------------------
# UM BANCO POR WORKER (pytest-xdist)
# ---------------------------------------------------------------------------
# Com `pytest -n N`, cada worker roda num processo proprio. Como db_conn
# esvazia o banco inteiro a cada teste, dois workers no mesmo banco
# apagariam os dados um do outro no meio do teste. Cada worker clona o
# banco ja migrado (CREATE DATABASE ... TEMPLATE) e passa a usar o clone.
#
# Tem que acontecer AQUI: antes do `from main import app` (config le o
# DATABASE_URL uma vez so, no import) e antes dos modulos de teste que
# leem os.environ["DATABASE_URL"] no proprio import.
#
# O comando sai de uma conexao ao banco `postgres`: o Postgres recusa
# clonar um template com qualquer sessao aberta nele, inclusive a de quem
# esta pedindo o clone. Sem xdist (PYTEST_XDIST_WORKER ausente), nada muda.
# ---------------------------------------------------------------------------
def _url_com_banco(url: str, banco: str) -> str:
    from urllib.parse import urlparse, urlunparse
    return urlunparse(urlparse(url)._replace(path=f"/{banco}"))


def _banco_do_worker(db_url: str, worker: str) -> str:
    import asyncio
    from urllib.parse import urlparse

    base = urlparse(db_url).path.lstrip("/")
    clone = f"{base}_{worker}"

    async def _clonar():
        admin = await asyncpg.connect(_url_com_banco(db_url, "postgres"))
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{clone}" WITH (FORCE)')
            # Varios workers clonam o mesmo template ao mesmo tempo; se um
            # deles ainda estiver no meio, o Postgres devolve "source database
            # is being accessed by other users". Tenta de novo por ate ~30 s.
            for tentativa in range(60):
                try:
                    await admin.execute(f'CREATE DATABASE "{clone}" TEMPLATE "{base}"')
                    return
                except asyncpg.ObjectInUseError:
                    if tentativa == 59:
                        raise
                    await asyncio.sleep(0.5)
        finally:
            await admin.close()

    asyncio.run(_clonar())
    return _url_com_banco(db_url, clone)


# A marca no ambiente segura o caso de este arquivo ser importado duas
# vezes no mesmo processo (test_crm_avaliacao faz `from tests.conftest
# import ...`): sem ela, a segunda importacao clonaria o clone e o teste
# falaria com um banco diferente do da API.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
if _WORKER and os.environ.get("HIPO_TEST_DB_WORKER") != _WORKER:
    _DB_URL = _banco_do_worker(_DB_URL, _WORKER)
    os.environ["DATABASE_URL"] = _DB_URL
    os.environ["HIPO_TEST_DB_WORKER"] = _WORKER


from main import app  # noqa: E402  (import após o safeguard, de propósito)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def telemetria_sem_descarga_automatica():
    """
    Desliga a descarga automatica do buffer de telemetria durante os testes.

    O middleware, ao juntar LOTE_DESCARGA eventos, dispara uma task solta que
    abre conexao propria e INSERE em uso_eventos. A fixture db_conn roda
    TRUNCATE usuarios CASCADE, que alcanca uso_eventos pela FK e precisa de
    ACCESS EXCLUSIVE. Os dois se encontram e a suite trava sem erro nenhum --
    foi exatamente o que aconteceu quando a telemetria entrou.

    Elevando o lote, nada descarrega sozinho: os testes de captura chamam
    `buffer.descarregar()` explicitamente, no momento em que querem gravar.
    O comportamento de producao fica intacto.
    """
    from middleware.telemetria import buffer

    original_lote = buffer.lote
    original_idade = buffer.idade_maxima
    buffer.lote = 10 ** 9
    # O gatilho por TEMPO passaria por cima do lote elevado: bastaria um evento
    # parado por mais de IDADE_MAXIMA_S para a descarga disparar sozinha e
    # reencontrar o TRUNCATE CASCADE. None desliga so o gatilho, e so no teste.
    buffer.idade_maxima = None
    yield
    await buffer.limpar()
    buffer.lote = original_lote
    buffer.idade_maxima = original_idade


# Limpeza entre testes. Antes era TRUNCATE usuarios CASCADE + 3 TRUNCATEs
# avulsos (~50 ms por teste: TRUNCATE troca o arquivo fisico de cada uma
# das ~55 tabelas, mesmo vazias). Com ~3000 testes eram ~2,5 min so de
# limpeza. DELETE em tabela com meia duzia de linhas custa quase nada.
#
# Efeito igual ao anterior: toda tabela do schema public fica vazia, menos
# schema_migrations (que nao tem FK para usuarios e nunca foi tocada).
# session_replication_role=replica desliga os triggers de FK durante o
# DELETE, entao a ordem das tabelas nao importa. Sequences nao sao
# reiniciadas -- o TRUNCATE antigo tambem nao reiniciava (sem RESTART
# IDENTITY). Tabela nova entra sozinha: a lista vem do catalogo.
_PRESERVAR = {"schema_migrations"}
_tabelas_cache: list[str] | None = None


async def _limpar_banco(conn) -> None:
    global _tabelas_cache
    if _tabelas_cache is None:
        linhas = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        _tabelas_cache = [r["tablename"] for r in linhas if r["tablename"] not in _PRESERVAR]
    sql = "SET session_replication_role = replica;\n" + "".join(
        f'DELETE FROM "{t}";\n' for t in _tabelas_cache
    ) + "SET session_replication_role = DEFAULT;"
    await conn.execute(sql)


@pytest.fixture
async def db_conn():
    """
    Conexão direta por teste, com o banco esvaziado antes (ver _limpar_banco).

    Todo teste começa do zero: contas, contatos, oportunidades, listas de
    domínio, dia_nao_util, base da Receita -- tudo, menos schema_migrations.
    """
    conn = await asyncpg.connect(_DB_URL)
    await _limpar_banco(conn)
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
    pwd_hash = bcrypt.hashpw(
        _SENHA_TESTE.encode(), bcrypt.gensalt(rounds=_ROUNDS)
    ).decode()
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


async def contato_do_alvo(
    client,
    headers: dict,
    *,
    oportunidade_id: str | None = None,
    conta_id: str | None = None,
    nome: str = "Ana Contato",
) -> str:
    """
    Um contato da empresa do alvo, criado se ainda não houver (045).

    Desde a 045, ligação, reunião, visita, WhatsApp e e-mail exigem o
    contato. Os testes que NÃO são sobre essa regra usam este helper para
    cumprir o requisito sem repetir o cadastro: na oportunidade, devolve o
    principal (e cria + promove um, se faltar); no parceiro, o primeiro
    contato vinculado à conta.

    Vai pela API, e não por INSERT, para que o contato nasça pelo mesmo
    caminho da tela — vínculo com a conta e espelho do principal incluídos.
    """
    if oportunidade_id is not None:
        opp = await client.get(f"/crm/oportunidades/{oportunidade_id}", headers=headers)
        assert opp.status_code == 200, opp.text
        if opp.json().get("contato_id"):
            return opp.json()["contato_id"]
        novo = await client.post(
            "/crm/contatos",
            json={"nome": nome, "conta_id": opp.json()["conta_id"]},
            headers=headers,
        )
        assert novo.status_code == 201, novo.text
        add = await client.post(
            f"/crm/oportunidades/{oportunidade_id}/contatos",
            json={"contato_id": novo.json()["id"], "principal": True},
            headers=headers,
        )
        assert add.status_code == 201, add.text
        return novo.json()["id"]

    assert conta_id is not None, "Informe oportunidade_id ou conta_id."
    lista = await client.get(
        "/crm/contatos/por-alvo", params={"conta_id": conta_id}, headers=headers
    )
    assert lista.status_code == 200, lista.text
    if lista.json():
        return lista.json()[0]["id"]
    novo = await client.post(
        "/crm/contatos", json={"nome": nome, "conta_id": conta_id}, headers=headers
    )
    assert novo.status_code == 201, novo.text
    return novo.json()["id"]


async def contato_para_proxima(client, headers: dict, url: str) -> str:
    """
    O contato da PRÓXIMA tarefa de uma conclusão/desfecho (045), deduzido
    da URL da própria chamada: a próxima herda o alvo da tarefa que fecha.

    Aceita as três portas que criam próxima:
        /crm/tarefas/{id}/concluir
        /crm/agenda/tarefas/{id}/desfecho
        /crm/agenda/reunioes/{id}/desfecho
    """
    partes = url.strip("/").split("/")
    if partes[:2] == ["crm", "tarefas"] or partes[:3] == ["crm", "agenda", "tarefas"]:
        tarefa_id = partes[2] if partes[1] == "tarefas" else partes[3]
        t = await client.get(f"/crm/tarefas/{tarefa_id}", headers=headers)
        assert t.status_code == 200, t.text
        alvo = t.json()
    else:
        r = await client.get(f"/crm/agenda/reunioes/{partes[3]}", headers=headers)
        assert r.status_code == 200, r.text
        alvo = r.json()
        alvo = {
            **alvo,
            "alvo": "oportunidade" if alvo.get("oportunidade_id") else "parceiro",
        }
    if alvo.get("oportunidade_id"):
        return await contato_do_alvo(
            client, headers, oportunidade_id=alvo["oportunidade_id"]
        )
    return await contato_do_alvo(client, headers, conta_id=alvo["conta_id"])
