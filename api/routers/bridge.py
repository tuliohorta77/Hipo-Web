"""
Endpoint Bridge: recebe os KPIs do Apps Script e grava em painel_snapshot.

Autenticacao por X-Bridge-Token (NAO usa JWT) - quem chama e o Apps Script,
nao um usuario logado. Por isso este router e registrado em main.py SEM
requer_modulo(...).
"""
import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config import settings
from database import get_conn

router = APIRouter(prefix="/painel/bridge", tags=["bridge"])


class KpiSnapshotIn(BaseModel):
    kpi_codigo: str = Field(..., min_length=1)
    valor: float


def verifica_bridge_token(x_bridge_token: str | None = Header(default=None)) -> None:
    esperado = settings.BRIDGE_TOKEN
    if (
        not esperado
        or not x_bridge_token
        or not secrets.compare_digest(x_bridge_token, esperado)
    ):
        raise HTTPException(status_code=401, detail="Token de bridge invalido")


@router.post("/snapshot")
async def upsert_snapshot(
    itens: list[KpiSnapshotIn],
    _: None = Depends(verifica_bridge_token),
    conn=Depends(get_conn),
):
    if not itens:
        raise HTTPException(status_code=400, detail="Body vazio")

    codigos = [i.kpi_codigo for i in itens]

    # Valida o batch inteiro ANTES de gravar qualquer coisa.
    rows = await conn.fetch(
        "SELECT codigo, fonte FROM painel_kpi_config WHERE codigo = ANY($1::text[])",
        codigos,
    )
    fonte_por_codigo = {r["codigo"]: r["fonte"] for r in rows}

    invalidos = []
    for c in codigos:
        if c not in fonte_por_codigo:
            invalidos.append({"kpi_codigo": c, "motivo": "inexistente"})
        elif fonte_por_codigo[c] != "bridge":
            invalidos.append({"kpi_codigo": c, "motivo": f"fonte={fonte_por_codigo[c]}"})

    if invalidos:
        # Qualquer KPI invalido derruba o batch inteiro: 400 e nada e gravado.
        raise HTTPException(
            status_code=400,
            detail={"erro": "kpis_invalidos", "itens": invalidos},
        )

    async with conn.transaction():
        for item in itens:
            await conn.execute(
                """
                INSERT INTO painel_snapshot (kpi_codigo, valor, atualizado_em)
                VALUES ($1, $2::numeric, now())
                ON CONFLICT (kpi_codigo)
                DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()
                """,
                item.kpi_codigo,
                Decimal(str(item.valor)),
            )

    return {"upserts": len(itens)}
