"""
HIPO -- Router de drilldown de leads do contador.

Endpoint isolado em arquivo próprio porque tem regra de acesso especial:
serve à aba "Leads" do drawer do módulo Contadores, então precisa ser
acessível por cargos que têm o módulo 'carteira' (Hunter, Farmer) OU
o módulo 'clientes' (ADM, Franqueado, Gerente, EP).

Por que não fica em routers/clientes.py?
  - O router /clientes está globalmente protegido por requer_modulo("clientes"),
    que bloqueia Hunter/Farmer. Como dependencies de include_router e de rota
    são ADITIVAS no FastAPI (todas executam), não dá pra "soltar" uma rota
    individual. A saída limpa é montar um segundo router em /clientes com
    guard próprio.

Endpoint:
  GET /clientes/contador-leads?cnpj=...  -- oportunidades vinculadas a um contador
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from database import get_conn
from routers.permissions import requer_qualquer_modulo


router = APIRouter()


@router.get(
    "/contador-leads",
    dependencies=[Depends(requer_qualquer_modulo(["clientes", "carteira"]))],
)
async def leads_do_contador(
    cnpj: str = Query(..., description="CNPJ do contador (com ou sem máscara)"),
    conn=Depends(get_conn),
):
    """
    Lista as oportunidades vinculadas a um CNPJ de contador.
    Usado pela aba "Leads" no drilldown do módulo Contadores.

    Acessível por: ADM, Franqueado, Gerente, EP (via módulo 'clientes')
    e Hunter, Farmer, SDR, EV, EC (via módulo 'carteira').

    Query param em vez de path param: CNPJs contêm '/' que quebraria
    o roteamento (ex: 02.543.245/0001-90).
    """
    rows = await conn.fetch(
        """
        SELECT op_id, cnpj, razao_social, status, fase, origem_macro,
               temperatura, previsao_valor, proposta_nmrr, previsao_data,
               executivo_contas, executivo_vendas,
               ultima_tarefa_dias, dias_parado,
               data_criacao, data_atualizacao
        FROM cliente_oportunidade
        WHERE cnpj_contador = $1
        ORDER BY data_atualizacao DESC NULLS LAST, op_id DESC
        """,
        cnpj,
    )

    total = len(rows)
    em_andamento = sum(1 for r in rows if (r["status"] or "").lower() == "ativo")
    conquistado = sum(1 for r in rows if (r["status"] or "").lower() == "conquistado")
    perdido = sum(1 for r in rows if (r["status"] or "").lower() == "perdido")

    return {
        "cnpj_contador": cnpj,
        "kpis": {
            "total": total,
            "em_andamento": em_andamento,
            "conquistado": conquistado,
            "perdido": perdido,
        },
        "leads": [dict(r) for r in rows],
    }
