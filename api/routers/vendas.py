"""
HIPO — Router do módulo Vendas.

Primeira visualização: o Funil de Vendas CROmie — classifica as
oportunidades ATIVAS pela "régua interna" de utilização correta do
CROmie (ver services/vendas_cromie.py para a definição das regras).

ATENÇÃO: a régua interna é mais exigente que o indicador PEX oficial
(cobra tarefa futura em todas as fases). O percentual devolvido aqui
NÃO é o número que a consultoria de campo da Omie apura — é uma
ferramenta interna de correção. O frontend deixa isso explícito.

Endpoints:
  GET /vendas/funil-cromie          — oportunidades ativas classificadas
  GET /vendas/funil-cromie/filtros  — valores distintos p/ os dropdowns
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from database import get_conn
from routers.auth import usuario_atual
from services.vendas_cromie import resumir_funil, FASES_ANALISADAS

router = APIRouter()

# Status que conta como "oportunidade ativa". Confirmado com a operação:
# cliente_oportunidade.status guarda 'ativo' para oportunidades em aberto.
_STATUS_ATIVO = "ativo"

# Colunas de cliente_oportunidade necessárias para classificar + exibir.
_COLUNAS = """
    op_id, cnpj, razao_social, fase, status,
    temperatura, previsao_data, previsao_valor, proposta_nmrr,
    tarefa_futura, previsao_preenchido, ticket_preenchido,
    cnpj_contador, razao_contador, executivo_contas, executivo_vendas,
    dias_parado, ultima_tarefa_dias, data_atualizacao
"""


@router.get("/funil-cromie")
async def funil_cromie(
    fase: str | None = Query(None, description="Filtra por fase exata."),
    executivo: str | None = Query(
        None, description="Filtra por executivo de vendas."
    ),
    so_problema: bool = Query(
        False, description="Se true, devolve apenas oportunidades não conformes."
    ),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Lista as oportunidades ATIVAS classificadas pela régua interna do
    funil CROmie, com um resumo agregado para o cabeçalho da tela.

    O filtro por fase/executivo é aplicado no SQL. O filtro 'so_problema'
    é aplicado DEPOIS da classificação (depende do resultado), e por isso
    o 'resumo' é sempre calculado sobre o conjunto completo (sem
    so_problema) — o cabeçalho mostra o panorama real, não o filtrado.
    """
    where = [f"status ILIKE $1"]
    args: list[Any] = [_STATUS_ATIVO]

    if fase:
        args.append(fase)
        where.append(f"fase = ${len(args)}")
    if executivo:
        args.append(executivo)
        where.append(f"executivo_vendas = ${len(args)}")

    where_sql = " AND ".join(where)
    sql = f"""
        SELECT {_COLUNAS}
        FROM cliente_oportunidade
        WHERE {where_sql}
        ORDER BY fase, data_atualizacao DESC NULLS LAST, op_id DESC
    """
    rows = await conn.fetch(sql, *args)
    oportunidades = [dict(r) for r in rows]

    # Classifica tudo. O resumo reflete o conjunto filtrado por
    # fase/executivo (mas NÃO por so_problema).
    resultado = resumir_funil(oportunidades)

    itens = resultado["itens"]
    if so_problema:
        itens = [
            it for it in itens
            if it["classificacao"]["fase_analisada"]
            and not it["classificacao"]["conforme"]
        ]

    return {
        "itens": itens,
        "resumo": resultado["resumo"],
        "por_fase": resultado["por_fase"],
        "filtro_aplicado": {
            "fase": fase,
            "executivo": executivo,
            "so_problema": so_problema,
        },
    }


@router.get("/funil-cromie/filtros")
async def funil_cromie_filtros(
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Valores distintos para popular os dropdowns de filtro da tela.

    - fases: as fases analisadas (ordem fixa do funil), apenas as que
      têm ao menos uma oportunidade ativa.
    - executivos: executivos de vendas com oportunidade ativa, ordenados.
    """
    fases_rows = await conn.fetch(
        """
        SELECT DISTINCT fase
        FROM cliente_oportunidade
        WHERE status ILIKE $1 AND fase = ANY($2::text[])
        """,
        _STATUS_ATIVO, FASES_ANALISADAS,
    )
    fases_presentes = {r["fase"] for r in fases_rows}
    # Mantém a ordem do funil, não a ordem alfabética.
    fases = [f for f in FASES_ANALISADAS if f in fases_presentes]

    exec_rows = await conn.fetch(
        """
        SELECT DISTINCT executivo_vendas
        FROM cliente_oportunidade
        WHERE status ILIKE $1
          AND executivo_vendas IS NOT NULL
          AND executivo_vendas <> ''
        ORDER BY executivo_vendas
        """,
        _STATUS_ATIVO,
    )
    executivos = [r["executivo_vendas"] for r in exec_rows]

    return {"fases": fases, "executivos": executivos}
