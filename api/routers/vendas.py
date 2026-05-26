"""
HIPO — Router do módulo Vendas.

Duas visualizações sobre as oportunidades ATIVAS do CROmie:

1. Funil-cromie (aba "Conformidade") — classifica as oportunidades
   pela "régua interna" de utilização correta do CROmie. Ver
   services/vendas_cromie.py para a definição das regras.

   ATENÇÃO: a régua interna é mais exigente que o indicador PEX
   oficial. O percentual NÃO é o número da consultoria de campo.

2. Funil de Vendas (aba "Funil") — visão comercial. Agrega as
   oportunidades ativas por fase x faixa de temperatura, com soma de
   valor (proposta_nmrr).

O endpoint /funil-cromie aceita um filtro de faixa de temperatura.
Isso alimenta o drawer da aba Funil: ao clicar numa faixa colorida
(ex.: "fechando" da Negociação), o frontend pede /funil-cromie com
fase + temperatura para listar as oportunidades daquele recorte.

Endpoints:
  GET /vendas/funil-cromie          — oportunidades ativas classificadas
  GET /vendas/funil-cromie/filtros  — valores distintos p/ os dropdowns
  GET /vendas/funil                 — agregação por fase x temperatura
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from database import get_conn
from routers.auth import usuario_atual
from services.vendas_cromie import (
    resumir_funil,
    montar_funil,
    FASES_ANALISADAS,
    FASES_DO_SDR,
    FAIXA_SEM,
    INTERVALO_FAIXA,
)

router = APIRouter()

# Status que conta como "oportunidade ativa".
_STATUS_ATIVO = "ativo"

# Colunas de cliente_oportunidade necessárias para classificar + exibir.
_COLUNAS = """
    op_id, cnpj, razao_social, fase, status,
    temperatura, previsao_data, previsao_valor, proposta_nmrr,
    tarefa_futura, previsao_preenchido, ticket_preenchido,
    cnpj_contador, razao_contador, executivo_contas,
    sdr_fr, executivo_vendas,
    dias_parado, ultima_tarefa_dias, data_atualizacao
"""

# Colunas mínimas para a agregação do funil.
_COLUNAS_FUNIL = "fase, temperatura, proposta_nmrr"

# Lista de fases do SDR como literal SQL (ver explicação abaixo).
_FASES_SDR_SQL = ", ".join(
    "'" + f.replace("'", "''") + "'" for f in sorted(FASES_DO_SDR)
)

# Expressão SQL do "responsável pela fase": SDR nas fases iniciais,
# executivo nas demais. As fases entram como literal (não parâmetro)
# porque a expressão CASE pode aparecer numa posição em que o Postgres
# não infere o tipo de um parâmetro $N. Valores fixos, sem injection.
_RESPONSAVEL_SQL = f"""
    CASE WHEN fase IN ({_FASES_SDR_SQL})
         THEN sdr_fr
         ELSE executivo_vendas
    END
"""


@router.get("/funil-cromie")
async def funil_cromie(
    fase: str | None = Query(None, description="Filtra por fase exata."),
    responsavel: str | None = Query(
        None,
        description="Filtra por responsável (SDR nas fases iniciais, "
                    "executivo de vendas nas demais).",
    ),
    temperatura: str | None = Query(
        None,
        description="Filtra por faixa de temperatura: sem, fria, morna, "
                    "quente, fechando. Alimenta o drawer da aba Funil.",
    ),
    so_problema: bool = Query(
        False, description="Se true, devolve apenas oportunidades não conformes."
    ),
    so_incoerente: bool = Query(
        False,
        description="Se true, devolve apenas oportunidades com temperatura "
                    "incoerente (temp 100 em fase ativa).",
    ),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Lista as oportunidades ATIVAS classificadas pela régua interna do
    funil CROmie, com um resumo agregado para o cabeçalho da tela.

    Os filtros fase / responsável / temperatura são aplicados no SQL.
    Os filtros so_problema e so_incoerente são aplicados DEPOIS da
    classificação. O 'resumo' é sempre calculado sobre o conjunto
    filtrado por fase/responsável/temperatura (não por so_*).

    Parâmetros SQL são adicionados APENAS quando o filtro está ativo —
    um parâmetro $N declarado mas não usado faz o Postgres falhar com
    IndeterminateDatatypeError.
    """
    args: list[Any] = [_STATUS_ATIVO]
    where = ["status ILIKE $1"]

    if fase:
        args.append(fase)
        where.append(f"fase = ${len(args)}")

    if responsavel:
        args.append(responsavel)
        where.append(f"({_RESPONSAVEL_SQL}) = ${len(args)}")

    # Filtro de faixa de temperatura. "sem" é temperatura nula ou 0;
    # as demais faixas têm um intervalo [min, max] inclusivo.
    if temperatura:
        faixa = temperatura.strip().lower()
        if faixa == FAIXA_SEM:
            where.append("(temperatura IS NULL OR temperatura = 0)")
        elif faixa in INTERVALO_FAIXA:
            lo, hi = INTERVALO_FAIXA[faixa]
            args.append(lo)
            i_lo = len(args)
            args.append(hi)
            i_hi = len(args)
            where.append(f"temperatura BETWEEN ${i_lo} AND ${i_hi}")
        # Faixa desconhecida: ignora o filtro (não quebra a query).

    where_sql = " AND ".join(where)
    sql = f"""
        SELECT {_COLUNAS}
        FROM cliente_oportunidade
        WHERE {where_sql}
        ORDER BY fase, data_atualizacao DESC NULLS LAST, op_id DESC
    """
    rows = await conn.fetch(sql, *args)
    oportunidades = [dict(r) for r in rows]

    resultado = resumir_funil(oportunidades)

    itens = resultado["itens"]
    if so_problema:
        itens = [
            it for it in itens
            if it["classificacao"]["fase_analisada"]
            and not it["classificacao"]["conforme"]
        ]
    if so_incoerente:
        itens = [
            it for it in itens
            if it["classificacao"]["temperatura_incoerente"]
        ]

    return {
        "itens": itens,
        "resumo": resultado["resumo"],
        "por_fase": resultado["por_fase"],
        "filtro_aplicado": {
            "fase": fase,
            "responsavel": responsavel,
            "temperatura": temperatura,
            "so_problema": so_problema,
            "so_incoerente": so_incoerente,
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
    - responsaveis: nomes distintos do responsável pela fase.
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
    fases = [f for f in FASES_ANALISADAS if f in fases_presentes]

    resp_rows = await conn.fetch(
        f"""
        SELECT DISTINCT ({_RESPONSAVEL_SQL}) AS responsavel
        FROM cliente_oportunidade
        WHERE status ILIKE $1
        """,
        _STATUS_ATIVO,
    )
    responsaveis = sorted(
        r["responsavel"].strip()
        for r in resp_rows
        if r["responsavel"] and r["responsavel"].strip()
    )

    return {"fases": fases, "responsaveis": responsaveis}


@router.get("/funil")
async def funil(
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Funil de Vendas — agrega as oportunidades ATIVAS por fase x faixa
    de temperatura, com soma de valor (proposta_nmrr).

    São consideradas apenas as 5 fases ativas (Suspect..Negociação);
    Conquistado fica de fora. Oportunidades com temperatura 100 não
    entram nas faixas — são contadas à parte em 'temperatura_incoerente'.

    Returns:
      dict com 'fases' (cada uma com total, valor e faixas),
      'total_geral', 'valor_geral' e 'temperatura_incoerente'.
    """
    rows = await conn.fetch(
        f"""
        SELECT {_COLUNAS_FUNIL}
        FROM cliente_oportunidade
        WHERE status ILIKE $1
        """,
        _STATUS_ATIVO,
    )
    oportunidades = [dict(r) for r in rows]
    return montar_funil(oportunidades)
