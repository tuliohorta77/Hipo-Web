"""
HIPO — Router de Metas PEX
Endpoints para o ADM cadastrar metas mensais.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_conn
from routers.auth import usuario_atual
from services.pex_catalogo import (
    CATALOGO,
    CLUSTERS,
    indicadores_editaveis,
    meta_para_cluster,
    get_indicador,
)

router = APIRouter()


# ──────────────────── Schemas ────────────────────

class MetaIndicadorIn(BaseModel):
    codigo: str
    meta_valor: Optional[float] = None


class Big3AcaoIn(BaseModel):
    ordem: int = Field(ge=1, le=3)
    descricao: Optional[str] = None
    atingiu: bool = False


class CabecalhoIn(BaseModel):
    mes_ref: str = Field(pattern=r"^\d{4}-\d{2}$")
    cluster_unidade: str = "BASE"
    dias_uteis: int = 22
    ecs_ativos_m3: int = 0
    evs_ativos: int = 0
    carteira_total_contadores: int = 0
    apps_ativos: int = 0
    headcount_recomendado: Optional[int] = None
    indicadores: list[MetaIndicadorIn] = []
    big3: list[Big3AcaoIn] = []


# ──────────────────── Helpers ────────────────────

def _ensure_adm(user: dict):
    if (user.get("cargo") or "").upper() != "ADM":
        raise HTTPException(403, "Apenas usuários ADM podem editar metas.")


def _validar_cluster(cluster: str):
    if cluster not in CLUSTERS:
        raise HTTPException(400, f"Cluster inválido. Esperado um de: {CLUSTERS}")


# ──────────────────── Endpoints públicos ────────────────────

@router.get("/catalogo")
async def get_catalogo(_user=Depends(usuario_atual)):
    """
    Retorna o catálogo dos 30 indicadores PEX (faixas, pesos, pilares).
    Frontend usa pra renderizar a página de metas.
    """
    return {"clusters": CLUSTERS, "indicadores": CATALOGO}


@router.get("/meses")
async def listar_meses(conn=Depends(get_conn), _user=Depends(usuario_atual)):
    """Lista os meses já cadastrados (mais recente primeiro)."""
    rows = await conn.fetch("""
        SELECT mes_ref, cluster_unidade, atualizado_em
        FROM pex_metas_cabecalho
        ORDER BY mes_ref DESC
    """)
    return [dict(r) for r in rows]


@router.get("/{mes_ref}")
async def get_meta_mes(
    mes_ref: str,
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Retorna a meta cadastrada do mês. Se não existir, devolve um esqueleto
    pré-populado com os valores do último mês cadastrado (para o usuário
    apenas ajustar o que mudou).
    """
    if not mes_ref or len(mes_ref) != 7:
        raise HTTPException(400, "mes_ref deve ser YYYY-MM")

    cab = await conn.fetchrow(
        "SELECT * FROM pex_metas_cabecalho WHERE mes_ref = $1", mes_ref
    )

    if cab is None:
        # Pré-popular com último mês existente
        ultimo = await conn.fetchrow("""
            SELECT * FROM pex_metas_cabecalho
            ORDER BY mes_ref DESC LIMIT 1
        """)
        if ultimo:
            ind_anterior = await conn.fetch(
                "SELECT codigo, meta_valor FROM pex_metas_indicadores WHERE cabecalho_id = $1",
                ultimo["id"],
            )
            big3_anterior = await conn.fetch(
                "SELECT ordem, descricao FROM pex_metas_big3 WHERE cabecalho_id = $1 ORDER BY ordem",
                ultimo["id"],
            )
            return {
                "existente": False,
                "pre_populado": True,
                "mes_ref": mes_ref,
                "cluster_unidade": ultimo["cluster_unidade"],
                "dias_uteis": ultimo["dias_uteis"],
                "ecs_ativos_m3": ultimo["ecs_ativos_m3"],
                "evs_ativos": ultimo["evs_ativos"],
                "carteira_total_contadores": ultimo["carteira_total_contadores"],
                "apps_ativos": ultimo["apps_ativos"],
                "headcount_recomendado": ultimo["headcount_recomendado"],
                "indicadores": [
                    {"codigo": r["codigo"], "meta_valor": float(r["meta_valor"]) if r["meta_valor"] else None}
                    for r in ind_anterior
                ],
                "big3": [
                    {"ordem": r["ordem"], "descricao": r["descricao"], "atingiu": False}
                    for r in big3_anterior
                ],
            }
        # Esqueleto cru
        return {
            "existente": False,
            "pre_populado": False,
            "mes_ref": mes_ref,
            "cluster_unidade": "BASE",
            "dias_uteis": 22,
            "ecs_ativos_m3": 0,
            "evs_ativos": 0,
            "carteira_total_contadores": 0,
            "apps_ativos": 0,
            "headcount_recomendado": None,
            "indicadores": [],
            "big3": [],
        }

    # Mês cadastrado
    inds = await conn.fetch(
        "SELECT codigo, meta_valor FROM pex_metas_indicadores WHERE cabecalho_id = $1",
        cab["id"],
    )
    big3 = await conn.fetch(
        "SELECT ordem, descricao, atingiu FROM pex_metas_big3 WHERE cabecalho_id = $1 ORDER BY ordem",
        cab["id"],
    )

    return {
        "existente": True,
        "pre_populado": False,
        "mes_ref": cab["mes_ref"],
        "cluster_unidade": cab["cluster_unidade"],
        "dias_uteis": cab["dias_uteis"],
        "ecs_ativos_m3": cab["ecs_ativos_m3"],
        "evs_ativos": cab["evs_ativos"],
        "carteira_total_contadores": cab["carteira_total_contadores"],
        "apps_ativos": cab["apps_ativos"],
        "headcount_recomendado": cab["headcount_recomendado"],
        "atualizado_em": cab["atualizado_em"].isoformat() if cab["atualizado_em"] else None,
        "indicadores": [
            {"codigo": r["codigo"], "meta_valor": float(r["meta_valor"]) if r["meta_valor"] is not None else None}
            for r in inds
        ],
        "big3": [
            {"ordem": r["ordem"], "descricao": r["descricao"], "atingiu": bool(r["atingiu"])}
            for r in big3
        ],
    }


# ──────────────────── Endpoint de escrita (UPSERT) ────────────────────

@router.post("/{mes_ref}")
async def salvar_meta_mes(
    mes_ref: str,
    payload: CabecalhoIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria ou sobrescreve as metas do mês. Apenas ADM.
    Substitui as linhas filhas em bloco (idempotente).
    """
    _ensure_adm(user)
    _validar_cluster(payload.cluster_unidade)

    if mes_ref != payload.mes_ref:
        raise HTTPException(400, "mes_ref do path e do payload não batem.")

    # Validar códigos do payload contra catálogo (rejeita inventados)
    codigos_validos = {i["codigo"] for i in CATALOGO}
    for ind in payload.indicadores:
        if ind.codigo not in codigos_validos:
            raise HTTPException(400, f"Indicador desconhecido: {ind.codigo}")

    # UPSERT cabeçalho
    cab_id = await conn.fetchval("""
        INSERT INTO pex_metas_cabecalho (
            mes_ref, cluster_unidade, dias_uteis, ecs_ativos_m3, evs_ativos,
            carteira_total_contadores, apps_ativos, headcount_recomendado,
            criado_por, atualizado_em
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, NOW())
        ON CONFLICT (mes_ref) DO UPDATE SET
            cluster_unidade           = EXCLUDED.cluster_unidade,
            dias_uteis                = EXCLUDED.dias_uteis,
            ecs_ativos_m3             = EXCLUDED.ecs_ativos_m3,
            evs_ativos                = EXCLUDED.evs_ativos,
            carteira_total_contadores = EXCLUDED.carteira_total_contadores,
            apps_ativos               = EXCLUDED.apps_ativos,
            headcount_recomendado     = EXCLUDED.headcount_recomendado,
            atualizado_em             = NOW()
        RETURNING id
    """,
        payload.mes_ref, payload.cluster_unidade, payload.dias_uteis,
        payload.ecs_ativos_m3, payload.evs_ativos,
        payload.carteira_total_contadores, payload.apps_ativos,
        payload.headcount_recomendado,
        user["id"],
    )

    # Substituir indicadores em bloco
    await conn.execute("DELETE FROM pex_metas_indicadores WHERE cabecalho_id = $1", cab_id)
    for ind in payload.indicadores:
        if ind.meta_valor is not None:
            await conn.execute("""
                INSERT INTO pex_metas_indicadores (cabecalho_id, codigo, meta_valor)
                VALUES ($1, $2, $3)
            """, cab_id, ind.codigo, ind.meta_valor)

    # Aplicar metas auto-derivadas do cluster (Integração Contábil, Eventos)
    # — só se o ADM não tiver fornecido manualmente
    codigos_informados = {i.codigo for i in payload.indicadores if i.meta_valor is not None}
    for ind_def in CATALOGO:
        cluster_meta = (ind_def.get("meta_por_cluster") or {}).get(payload.cluster_unidade)
        if cluster_meta is not None and ind_def["codigo"] not in codigos_informados:
            await conn.execute("""
                INSERT INTO pex_metas_indicadores (cabecalho_id, codigo, meta_valor)
                VALUES ($1, $2, $3)
                ON CONFLICT (cabecalho_id, codigo) DO UPDATE SET meta_valor = EXCLUDED.meta_valor
            """, cab_id, ind_def["codigo"], cluster_meta)

    # Substituir Big3 em bloco
    await conn.execute("DELETE FROM pex_metas_big3 WHERE cabecalho_id = $1", cab_id)
    for acao in payload.big3:
        await conn.execute("""
            INSERT INTO pex_metas_big3 (cabecalho_id, ordem, descricao, atingiu)
            VALUES ($1, $2, $3, $4)
        """, cab_id, acao.ordem, acao.descricao, acao.atingiu)

    return {"ok": True, "cabecalho_id": cab_id, "mes_ref": mes_ref}
