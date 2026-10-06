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
    # relatorios_diarios NAO tem FK para usuarios (o fechamento sobrevive a
    # saida de quem o gerou), entao o CASCADE acima nao a alcanca. Sem este
    # TRUNCATE explicito, o dia gravado por um teste colide com o do proximo
    # na PK e a suite falha por ordem de execucao.
    await conn.execute("TRUNCATE TABLE relatorios_diarios")
    # Base da Receita (022): escrita so pelo script de carga, sem FK para
    # usuarios -- o CASCADE acima nao a alcanca.
    await conn.execute(
        "TRUNCATE TABLE receita_estabelecimentos, receita_municipios, "
        "receita_cnaes, receita_cargas"
    )
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
