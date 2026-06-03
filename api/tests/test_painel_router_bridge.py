"""
Testes de integracao do endpoint Bridge (POST /painel/bridge/snapshot).

Roda no CI (PostgreSQL disponivel via container). Usa as fixtures `client`
e `db_conn` do conftest.

As tabelas painel_* NAO estao na lista de TRUNCATE do conftest, entao este
modulo limpa os proprios codigos de KPI. O DELETE em painel_kpi_config
cascateia para painel_snapshot (FK ON DELETE CASCADE), entao um delete so
limpa as duas tabelas. Usa codigos com prefixo TST_ para nao tocar em
eventual seed de KPIs reais.
"""
from decimal import Decimal

import pytest

from config import settings

TOKEN = "token-de-teste-bridge"

COD_LEAD = "TST_LEAD"   # fonte = bridge
COD_REU = "TST_REU"     # fonte = bridge
COD_HIPO = "TST_HIPO"   # fonte = hipo (deve ser rejeitado pelo bridge)


@pytest.fixture
def bridge_token(monkeypatch):
    monkeypatch.setattr(settings, "BRIDGE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture
async def kpis(db_conn):
    codigos = [COD_LEAD, COD_REU, COD_HIPO]
    await db_conn.execute(
        "DELETE FROM painel_kpi_config WHERE codigo = ANY($1::text[])", codigos
    )
    await db_conn.executemany(
        """
        INSERT INTO painel_kpi_config
            (codigo, nome, tipo, polaridade, ordem, icone, cor_hex, fonte, ativo)
        VALUES ($1, $2, 'cumulativo', 'maior', $3, 'activity', '#2563EB', $4, true)
        """,
        [
            (COD_LEAD, "Leads (teste)", 901, "bridge"),
            (COD_REU, "Reunioes (teste)", 902, "bridge"),
            (COD_HIPO, "MRR HIPO (teste)", 903, "hipo"),
        ],
    )
    yield codigos
    await db_conn.execute(
        "DELETE FROM painel_kpi_config WHERE codigo = ANY($1::text[])", codigos
    )


async def _valor(db_conn, codigo):
    return await db_conn.fetchval(
        "SELECT valor FROM painel_snapshot WHERE kpi_codigo = $1", codigo
    )


async def test_token_ok_faz_upsert(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        headers={"X-Bridge-Token": bridge_token},
        json=[
            {"kpi_codigo": COD_LEAD, "valor": 116},
            {"kpi_codigo": COD_REU, "valor": 12},
        ],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["upserts"] == 2
    assert await _valor(db_conn, COD_LEAD) == Decimal("116")
    assert await _valor(db_conn, COD_REU) == Decimal("12")


async def test_token_errado_retorna_401(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        headers={"X-Bridge-Token": "errado"},
        json=[{"kpi_codigo": COD_LEAD, "valor": 1}],
    )
    assert resp.status_code == 401
    assert await _valor(db_conn, COD_LEAD) is None


async def test_sem_token_retorna_401(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        json=[{"kpi_codigo": COD_LEAD, "valor": 1}],
    )
    assert resp.status_code == 401
    assert await _valor(db_conn, COD_LEAD) is None


async def test_kpi_inexistente_retorna_400(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        headers={"X-Bridge-Token": bridge_token},
        json=[{"kpi_codigo": "NAO_EXISTE", "valor": 1}],
    )
    assert resp.status_code == 400


async def test_fonte_hipo_rejeitada(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        headers={"X-Bridge-Token": bridge_token},
        json=[{"kpi_codigo": COD_HIPO, "valor": 9999}],
    )
    assert resp.status_code == 400
    assert await _valor(db_conn, COD_HIPO) is None


async def test_upsert_sobrescreve_valor(client, db_conn, kpis, bridge_token):
    h = {"X-Bridge-Token": bridge_token}
    r1 = await client.post(
        "/painel/bridge/snapshot", headers=h,
        json=[{"kpi_codigo": COD_LEAD, "valor": 100}],
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/painel/bridge/snapshot", headers=h,
        json=[{"kpi_codigo": COD_LEAD, "valor": 250}],
    )
    assert r2.status_code == 200
    assert await _valor(db_conn, COD_LEAD) == Decimal("250")
    n = await db_conn.fetchval(
        "SELECT count(*) FROM painel_snapshot WHERE kpi_codigo = $1", COD_LEAD
    )
    assert n == 1


async def test_batch_parcial_e_atomico(client, db_conn, kpis, bridge_token):
    resp = await client.post(
        "/painel/bridge/snapshot",
        headers={"X-Bridge-Token": bridge_token},
        json=[
            {"kpi_codigo": COD_LEAD, "valor": 116},      # valido
            {"kpi_codigo": "NAO_EXISTE", "valor": 5},    # invalido
        ],
    )
    assert resp.status_code == 400
    # O LEAD valido tambem nao pode ter sido gravado.
    assert await _valor(db_conn, COD_LEAD) is None
