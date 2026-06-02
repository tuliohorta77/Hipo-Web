"""Seed inicial do modulo Painel Gerencial (HIPO v1.4.0 - Etapa 1).

Roda apos a migration `painel.sql`. Idempotente: pode rodar varias vezes
sem duplicar dados (usa ON CONFLICT DO NOTHING / DO UPDATE conforme o caso).

Insere:
  1. Os 10 KPIs em `painel_kpi_config` (com tipo, polaridade, fonte, ordem).
  2. Os feriados nacionais brasileiros de 2026 a 2030 em `dia_nao_util`.

Uso:
    cd api
    python -m scripts.seed_painel

Ou via SSH no EC2:
    cd /home/hipo/app
    sudo -iu hipo
    cd api
    python -m scripts.seed_painel
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

import asyncpg

# Adiciona o diretorio raiz ao sys.path para imports funcionarem ao rodar como modulo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.dias_uteis import feriados_nacionais_br  # noqa: E402


KPIS: list[dict] = [
    {
        "codigo": "LEAD",
        "nome": "Leads",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 1,
        "icone": "ti-user",
        "cor_hex": "#2563EB",
        "fonte": "bridge",
    },
    {
        "codigo": "AGEN",
        "nome": "Agendamentos",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 2,
        "icone": "ti-calendar",
        "cor_hex": "#16A34A",
        "fonte": "bridge",
    },
    {
        "codigo": "APRE",
        "nome": "Apresentacoes",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 3,
        "icone": "ti-device-desktop",
        "cor_hex": "#7C3AED",
        "fonte": "bridge",
    },
    {
        "codigo": "NMRR",
        "nome": "NMRR",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 4,
        "icone": "ti-trending-up",
        "cor_hex": "#EA580C",
        "fonte": "bridge",
    },
    {
        "codigo": "TICK_MED",
        "nome": "Tick. Medio",
        "tipo": "media",
        "polaridade": "maior",
        "ordem": 5,
        "icone": "ti-coin",
        "cor_hex": "#0891B2",
        "fonte": "bridge",
    },
    {
        "codigo": "RN_PARC",
        "nome": "Reun. Parcerias",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 6,
        "icone": "ti-handshake",
        "cor_hex": "#7C3AED",
        "fonte": "bridge",
    },
    {
        "codigo": "AGEND_MES",
        "nome": "Agend. Mes",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 7,
        "icone": "ti-calendar-event",
        "cor_hex": "#16A34A",
        "fonte": "bridge",
    },
    {
        "codigo": "NOSHOW",
        "nome": "% No-show",
        "tipo": "taxa_invertida",
        "polaridade": "menor",
        "ordem": 8,
        "icone": "ti-user-question",
        "cor_hex": "#DC2626",
        "fonte": "bridge",
    },
    {
        "codigo": "APPS",
        "nome": "APPs",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 9,
        "icone": "ti-bulb",
        "cor_hex": "#2563EB",
        "fonte": "bridge",
    },
    {
        "codigo": "TREIN",
        "nome": "Treinamento",
        "tipo": "cumulativo",
        "polaridade": "maior",
        "ordem": 10,
        "icone": "ti-school",
        "cor_hex": "#0D9488",
        "fonte": "bridge",
    },
]


ANOS_FERIADOS = [2026, 2027, 2028, 2029, 2030]


def _mascarar_database_url(url: str) -> str:
    """Esconde a senha do DATABASE_URL para log seguro."""
    if "@" not in url or "://" not in url:
        return url
    proto_resto = url.split("://", 1)
    proto = proto_resto[0]
    resto = proto_resto[1]
    if "@" in resto:
        credenciais, host = resto.split("@", 1)
        if ":" in credenciais:
            user = credenciais.split(":", 1)[0]
            return f"{proto}://{user}:****@{host}"
    return url


async def seed_kpis(conn: asyncpg.Connection) -> None:
    """Insere ou atualiza os 10 KPIs em painel_kpi_config."""
    sql = """
        INSERT INTO painel_kpi_config
            (codigo, nome, tipo, polaridade, ordem, icone, cor_hex, fonte, ativo)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, TRUE)
        ON CONFLICT (codigo) DO UPDATE SET
            nome = EXCLUDED.nome,
            tipo = EXCLUDED.tipo,
            polaridade = EXCLUDED.polaridade,
            ordem = EXCLUDED.ordem,
            icone = EXCLUDED.icone,
            cor_hex = EXCLUDED.cor_hex,
            fonte = EXCLUDED.fonte,
            ativo = TRUE
    """
    for kpi in KPIS:
        await conn.execute(
            sql,
            kpi["codigo"],
            kpi["nome"],
            kpi["tipo"],
            kpi["polaridade"],
            kpi["ordem"],
            kpi["icone"],
            kpi["cor_hex"],
            kpi["fonte"],
        )
    print(f"  -> {len(KPIS)} KPIs sincronizados em painel_kpi_config")


async def seed_feriados(conn: asyncpg.Connection) -> None:
    """Insere os feriados nacionais brasileiros nos anos definidos."""
    sql = """
        INSERT INTO dia_nao_util (data, motivo, criado_por_usuario_id)
        VALUES ($1, $2, NULL)
        ON CONFLICT (data) DO NOTHING
    """
    total_inseridos = 0
    for ano in ANOS_FERIADOS:
        for d, motivo in feriados_nacionais_br(ano):
            resultado = await conn.execute(sql, d, motivo)
            if resultado.endswith("1"):
                total_inseridos += 1
    print(
        f"  -> {total_inseridos} feriados inseridos em dia_nao_util "
        f"(anos {ANOS_FERIADOS[0]}-{ANOS_FERIADOS[-1]}, "
        f"existentes mantidos)"
    )


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERRO: DATABASE_URL nao definida no ambiente.")
        sys.exit(1)

    print(f"Conectando em {_mascarar_database_url(database_url)} ...")
    conn = await asyncpg.connect(database_url)
    try:
        print("Seed painel iniciado.")
        await seed_kpis(conn)
        await seed_feriados(conn)
        print("Seed painel concluido com sucesso.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
