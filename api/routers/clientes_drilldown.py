"""
HIPO -- Router de drilldown da Carteira que usa dados de Clientes.

Endpoints servidos aqui (montados em /clientes/* via main.py):
  GET  /clientes/contador-leads        -- aba Leads do drawer
  GET  /clientes/oportunidades/{op_id} -- drill-in: tarefas de um lead expandido no drawer
  POST /clientes/funil-por-grupos      -- mini-funil agregado por id_grupo na listagem

Todas têm guard requer_qualquer_modulo(["clientes", "carteira"]), ou seja:
  - ADM, Franqueado, Gerente, EP (via módulo 'clientes')
  - Hunter, Farmer, SDR, EV, EC  (via módulo 'carteira')

Por que vivem aqui e não em routers/clientes.py?
  O router principal de /clientes tem dependency global requer_modulo("clientes"),
  que bloqueia Hunter/Farmer. Essas 3 rotas servem ao drawer/listagem do módulo
  Contadores e precisam ser acessíveis também a esses cargos. Como dependencies
  de include_router e de rota são aditivas no FastAPI (todas executam), não dá
  pra "soltar" uma rota individual do guard global — daí o router separado,
  montado no mesmo prefixo /clientes mas sem dependency global.

Esse router NÃO contém as rotas de gestão de Clientes (upload, listagem geral,
resumo, histórico), que continuam restritas a quem tem o módulo 'clientes'.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import get_conn
from routers.permissions import requer_qualquer_modulo


router = APIRouter()

# Módulos que liberam acesso a TODAS as rotas deste router.
_MODULOS_DRILLDOWN = ["clientes", "carteira"]

# Etapas ativas do funil (1-5). Descarta '06. Conquistado' e leads 'Perdido'/'Cancelado'.
_ETAPAS = [
    ("suspect",       "01"),
    ("cadencia",      "02"),
    ("qualificacao",  "03"),
    ("apresentacao",  "04"),
    ("negociacao",    "05"),
]


class FunilGruposRequest(BaseModel):
    id_grupos: list[str]


# ── GET /contador-leads ────────────────────────────────────────────────────

@router.get(
    "/contador-leads",
    dependencies=[Depends(requer_qualquer_modulo(_MODULOS_DRILLDOWN))],
)
async def leads_do_contador(
    cnpj: str = Query(..., description="CNPJ do contador (com ou sem máscara)"),
    conn=Depends(get_conn),
):
    """
    Lista as oportunidades vinculadas a um CNPJ de contador.
    Usado pela aba "Leads" no drilldown do módulo Contadores.

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


# ── GET /oportunidades/{op_id} ─────────────────────────────────────────────

@router.get(
    "/oportunidades/{op_id}",
    dependencies=[Depends(requer_qualquer_modulo(_MODULOS_DRILLDOWN))],
)
async def detalhar_oportunidade(
    op_id: int,
    conn=Depends(get_conn),
):
    """
    Detalhe de uma oportunidade + suas tarefas.

    Usado pelo drawer de Contadores quando o usuário expande uma linha de lead
    pra ver as tarefas vinculadas àquela OP. Também serve à página de Clientes
    (cargos ADM/Franqueado/Gerente/EP).
    """
    op = await conn.fetchrow(
        "SELECT * FROM cliente_oportunidade WHERE op_id = $1 LIMIT 1",
        op_id,
    )
    if not op:
        raise HTTPException(404, "Oportunidade não encontrada.")

    tarefas = await conn.fetch(
        """
        SELECT tarefa_id, data_criacao, data_agendamento, data_atualizacao,
               fase_lead, status, finalidade, resultado, canal,
               situacao_tarefa, usuario_atribuido
        FROM cliente_tarefa
        WHERE op_id = $1
        ORDER BY data_agendamento DESC NULLS LAST
        """,
        op_id,
    )

    return {
        "oportunidade": dict(op),
        "tarefas": [dict(t) for t in tarefas],
    }


# ── POST /funil-por-grupos ─────────────────────────────────────────────────

@router.post(
    "/funil-por-grupos",
    dependencies=[Depends(requer_qualquer_modulo(_MODULOS_DRILLDOWN))],
)
async def funil_por_grupos(
    body: FunilGruposRequest,
    conn=Depends(get_conn),
):
    """
    Agregado de funil (5 etapas ativas: Suspect, Cadência, Qualificação,
    Apresentação, Negociação) por id_grupo.

    Body: { "id_grupos": ["abc123", "def456", ...] }

    Resposta:
      {
        "por_grupo": {
          "abc123": {
            "suspect":      {"qtd": 2, "ticket": 1500.00},
            "cadencia":     {"qtd": 5, "ticket": 8200.00},
            ...
          },
          ...
        }
      }

    Faz JOIN com carteira_cnpj.cnpj_contador → cliente_oportunidade.cnpj_contador.
    Filtra leads com status = 'Ativo'. Ticket = proposta_nmrr.

    Usado pelo mini-funil na listagem de Contadores. Acessível por Hunter/Farmer
    porque a listagem de Contadores é deles.
    """
    if not body.id_grupos:
        return {"por_grupo": {}}

    rows = await conn.fetch(
        """
        SELECT
            cc.id_grupo,
            LEFT(co.fase, 2) AS num_fase,
            COUNT(*)              AS qtd,
            COALESCE(SUM(co.proposta_nmrr), 0) AS ticket
        FROM carteira_cnpj cc
        JOIN cliente_oportunidade co
          ON co.cnpj_contador = cc.cnpj_contador
        WHERE cc.id_grupo = ANY($1::text[])
          AND LOWER(COALESCE(co.status, '')) = 'ativo'
          AND LEFT(co.fase, 2) IN ('01', '02', '03', '04', '05')
        GROUP BY cc.id_grupo, LEFT(co.fase, 2)
        """,
        body.id_grupos,
    )

    # Inicializa zeros pra todos os grupos pedidos (mesmo que sem leads)
    saida: dict[str, dict] = {}
    for gid in body.id_grupos:
        saida[gid] = {k: {"qtd": 0, "ticket": 0.0} for k, _ in _ETAPAS}

    fase_para_chave = {num: chave for chave, num in _ETAPAS}

    for r in rows:
        gid = r["id_grupo"]
        chave = fase_para_chave.get(r["num_fase"])
        if gid in saida and chave:
            saida[gid][chave] = {
                "qtd": int(r["qtd"]),
                "ticket": float(r["ticket"] or 0),
            }

    return {"por_grupo": saida}
