"""
HIPO — Router do módulo Agendamento (cargo SDR + gestão).

v1.3.1 — primeira versão. Replica a régua de CONFORMIDADE do funil
CROmie já usada no módulo Vendas (services/vendas_cromie.py), exposta
agora sob /agendamento/* e liberada para o módulo 'agendamento'.

v1.3.2 — a classificação ganhou três estados (conforme / atenção
[tarefa para hoje] / problema). O SELECT inclui ult_prox_tarefa para o
serviço distinguir "tarefa hoje" de "tarefa vencida/ausente". A regra
é compartilhada com Vendas (mesmo serviço) — os dois módulos exibem o
estado de atenção.

Por que um router próprio (e não reuso de /vendas/funil-cromie):
  - /vendas/* é protegido por requer_modulo("clientes"); o SDR NÃO tem
    'clientes', então não poderia consumir aquele endpoint.
  - O Agendamento vai DIVERGIR da conformidade de Vendas nas próximas
    versões (régua/colunas próprias do SDR). Ter URL e router próprios
    desde já evita refator quando essa divergência chegar.

ATENÇÃO: a régua interna é mais exigente que o indicador PEX oficial.
O percentual NÃO é o número da consultoria de campo da Omie.

Endpoints:
  GET /agendamento/conformidade          — oportunidades ativas classificadas
  GET /agendamento/conformidade/filtros  — valores distintos p/ os dropdowns
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from database import get_conn
from routers.auth import usuario_atual
from services.vendas_cromie import (
    resumir_funil,
    FASES_ANALISADAS,
    FASES_DO_SDR,
    FAIXA_SEM,
    INTERVALO_FAIXA,
)

router = APIRouter()

# Status que conta como "oportunidade ativa".
_STATUS_ATIVO = "ativo"

# Colunas de cliente_oportunidade necessárias para classificar + exibir.
# v1.3.2: + ult_prox_tarefa (estado de atenção/tarefa-hoje).
_COLUNAS = """
    op_id, cnpj, razao_social, fase, status,
    temperatura, previsao_data, previsao_valor, proposta_nmrr,
    tarefa_futura, ult_prox_tarefa, previsao_preenchido, ticket_preenchido,
    cnpj_contador, razao_contador, executivo_contas,
    sdr_fr, executivo_vendas,
    dias_parado, ultima_tarefa_dias, data_atualizacao
"""

# Lista de fases do SDR como literal SQL.
_FASES_SDR_SQL = ", ".join(
    "'" + f.replace("'", "''") + "'" for f in sorted(FASES_DO_SDR)
)

# Expressão SQL do "responsável pela fase": SDR nas fases iniciais,
# executivo nas demais. Valores fixos (não parâmetro), sem injection.
_RESPONSAVEL_SQL = f"""
    CASE WHEN fase IN ({_FASES_SDR_SQL})
         THEN sdr_fr
         ELSE executivo_vendas
    END
"""


@router.get("/conformidade")
async def agendamento_conformidade(
    fase: str | None = Query(None, description="Filtra por fase exata."),
    responsavel: str | None = Query(
        None,
        description="Filtra por responsável (SDR nas fases iniciais, "
                    "executivo de vendas nas demais).",
    ),
    temperatura: str | None = Query(
        None,
        description="Filtra por faixa de temperatura: sem, fria, morna, "
                    "quente, fechando.",
    ),
    so_problema: bool = Query(
        False, description="Se true, devolve apenas oportunidades não conformes "
                           "(estado 'problema'; atenção/tarefa-hoje fica fora)."
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

    Espelha GET /vendas/funil-cromie. Os filtros fase / responsável /
    temperatura são aplicados no SQL; so_problema e so_incoerente são
    aplicados DEPOIS da classificação. O 'resumo' é sempre calculado
    sobre o conjunto filtrado por fase/responsável/temperatura.

    so_problema filtra pelo estado 'problema'. As oportunidades em
    estado 'atenção' (tarefa para hoje) NÃO entram no so_problema.

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
            and it["classificacao"]["estado"] == "problema"
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


@router.get("/conformidade/filtros")
async def agendamento_conformidade_filtros(
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Valores distintos para popular os dropdowns de filtro da tela.

    - fases: as fases analisadas (ordem fixa do funil), apenas as que
      têm ao menos uma oportunidade ativa.
    - responsaveis: nomes distintos do responsável pela fase.

    Espelha GET /vendas/funil-cromie/filtros.
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
