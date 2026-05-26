"""
HIPO — Router do módulo Vendas.

Primeira visualização: o Funil de Vendas CROmie — classifica as
oportunidades ATIVAS pela "régua interna" de utilização correta do
CROmie (ver services/vendas_cromie.py para a definição das regras).

ATENÇÃO: a régua interna é mais exigente que o indicador PEX oficial
(cobra tarefa futura em todas as fases). O percentual devolvido aqui
NÃO é o número que a consultoria de campo da Omie apura — é uma
ferramenta interna de correção. O frontend deixa isso explícito.

Responsável pela oportunidade: depende da fase. Nas fases iniciais
(Suspect, Cadência) o responsável é o SDR (coluna sdr_fr); nas demais
é o executivo de vendas (coluna executivo_vendas). O filtro
?responsavel= e o endpoint /filtros respeitam essa regra.

Endpoints:
  GET /vendas/funil-cromie          — oportunidades ativas classificadas
  GET /vendas/funil-cromie/filtros  — valores distintos p/ os dropdowns
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from database import get_conn
from routers.auth import usuario_atual
from services.vendas_cromie import resumir_funil, FASES_ANALISADAS, FASES_DO_SDR

router = APIRouter()

# Status que conta como "oportunidade ativa". Confirmado com a operação:
# cliente_oportunidade.status guarda 'ativo' para oportunidades em aberto.
_STATUS_ATIVO = "ativo"

# Colunas de cliente_oportunidade necessárias para classificar + exibir.
# sdr_fr e executivo_vendas entram para o serviço calcular o responsável.
_COLUNAS = """
    op_id, cnpj, razao_social, fase, status,
    temperatura, previsao_data, previsao_valor, proposta_nmrr,
    tarefa_futura, previsao_preenchido, ticket_preenchido,
    cnpj_contador, razao_contador, executivo_contas,
    sdr_fr, executivo_vendas,
    dias_parado, ultima_tarefa_dias, data_atualizacao
"""

# Lista de fases do SDR como literal SQL — usada na expressão CASE do
# "responsável pela fase". É um literal (e não um parâmetro) de
# propósito: a expressão CASE pode aparecer numa posição (cast de array)
# em que o Postgres não consegue inferir o tipo de um parâmetro $N.
# As fases são valores fixos e seguros, definidos no código (não vêm do
# usuário), então embuti-las como literal é seguro — sem risco de SQL
# injection. FASES_DO_SDR vem de services.vendas_cromie.
_FASES_SDR_SQL = ", ".join(
    "'" + f.replace("'", "''") + "'" for f in sorted(FASES_DO_SDR)
)

# Expressão SQL do "responsável pela fase": SDR nas fases iniciais,
# executivo de vendas nas demais. Mantida idêntica à regra de
# services.vendas_cromie.responsavel_da_op (as duas precisam casar).
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
    so_problema: bool = Query(
        False, description="Se true, devolve apenas oportunidades não conformes."
    ),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Lista as oportunidades ATIVAS classificadas pela régua interna do
    funil CROmie, com um resumo agregado para o cabeçalho da tela.

    O filtro por fase/responsável é aplicado no SQL. O filtro
    'so_problema' é aplicado DEPOIS da classificação (depende do
    resultado), e por isso o 'resumo' é sempre calculado sobre o
    conjunto completo (sem so_problema) — o cabeçalho mostra o
    panorama real, não o filtrado.

    Parâmetros SQL são adicionados APENAS quando o filtro correspondente
    está ativo — um parâmetro $N declarado mas não usado faz o Postgres
    falhar com IndeterminateDatatypeError.
    """
    args: list[Any] = [_STATUS_ATIVO]
    where = ["status ILIKE $1"]

    if fase:
        args.append(fase)
        where.append(f"fase = ${len(args)}")
    if responsavel:
        args.append(responsavel)
        # A expressão do responsável usa fases como literal SQL, então
        # o único parâmetro aqui é o nome do responsável.
        where.append(f"({_RESPONSAVEL_SQL}) = ${len(args)}")

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
    # fase/responsável (mas NÃO por so_problema).
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
            "responsavel": responsavel,
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
    - responsaveis: nomes distintos do responsável pela fase — SDRs
      (das fases iniciais) e executivos (das demais) numa lista única,
      ordenada. É a lista que alimenta o filtro unificado "Responsável".
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

    # Responsáveis: aplica a mesma expressão CASE (com fases literais)
    # e coleta os distintos. O único parâmetro aqui é o status.
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
