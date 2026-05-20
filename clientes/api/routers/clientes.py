"""
HIPO -- Router do módulo Clientes (Oportunidades + Tarefas).

Endpoints:
  POST /clientes/upload-oportunidades  — substitui snapshot de cliente_oportunidade
  POST /clientes/upload-tarefas        — substitui snapshot de cliente_tarefa
  GET  /clientes/oportunidades         — lista paginada com filtros
  GET  /clientes/oportunidades/{op_id} — detalhe + tarefas da OP
  GET  /clientes/tarefas               — lista paginada com filtros
  GET  /clientes/resumo                — totais p/ cards
  GET  /clientes/historico             — últimos uploads
  GET  /clientes/contador/{cnpj}/leads — leads de um contador (usado no drilldown da Carteira)
"""
from __future__ import annotations

import os
import uuid
import shutil
from typing import Any

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query

from database import get_conn
from routers.auth import usuario_atual
from parsers.cliente_oportunidades import parse_oportunidades_arquivo
from parsers.cliente_tarefas import parse_tarefas_clientes_arquivo

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")


# ── Helpers ──────────────────────────────────────────────────────

async def _salvar_temp(arquivo: UploadFile, subdir: str) -> tuple[str, str]:
    nome = arquivo.filename or "upload.xlsx"
    dest = os.path.join(UPLOAD_DIR, subdir)
    os.makedirs(dest, exist_ok=True)
    caminho = os.path.join(dest, f"{uuid.uuid4()}_{nome}")
    with open(caminho, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)
    return caminho, nome


async def _registrar_upload(
    conn, tipo: str, usuario_id, nome: str, total: int, validos: int
) -> str:
    return await conn.fetchval(
        """
        INSERT INTO cliente_upload
            (tipo, usuario_id, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ($1, $2, $3, $4, $5, FALSE)
        RETURNING id
        """,
        tipo, usuario_id, nome, total, validos,
    )


async def _marcar_processado(conn, upload_id: str) -> None:
    await conn.execute(
        "UPDATE cliente_upload SET processado = TRUE WHERE id = $1",
        upload_id,
    )


# Campos de cliente_oportunidade na ordem do INSERT
_OP_FIELDS = [
    "op_id", "cnpj", "razao_social", "data_criacao", "data_agendamento",
    "data_atualizacao", "ult_prox_tarefa", "origem_crm", "origem_macro",
    "status", "fase", "motivo_perda", "temperatura",
    "proposta_nmrr", "proposta_pack", "previsao_valor", "previsao_data",
    "cnae", "cnae_bim", "secao", "setor", "faixa_faturamento",
    "fase_suspect", "fase_cadencia", "fase_qualificacao",
    "fase_apresentacao", "fase_proposta", "fase_conquistado",
    "unidade", "cnpj_contador", "razao_contador", "executivo_contas",
    "sdr_fr", "sdr_gd", "executivo_vendas", "executivo_vendas_gd",
    "tipo_produto", "tipo_treinamento", "ultima_demo_realizada",
    "ultima_tarefa_tipo", "ultima_tarefa_dias", "dias_parado",
    "previsao_preenchido", "ticket_preenchido", "lead_trabalhado",
    "lead_agendado", "tarefa_futura", "demo_agendada", "demo_realizada",
]

_TAREFA_FIELDS = [
    "tarefa_id", "op_id", "cnpj", "razao_social",
    "data_criacao", "data_atualizacao", "data_agendamento",
    "fase_lead", "status", "finalidade", "resultado", "origem_lead",
    "usuario_atribuido", "usuario_criador", "canal", "situacao_tarefa",
    "unidade",
]


# ── Upload de Oportunidades ──────────────────────────────────────

@router.post("/upload-oportunidades")
async def upload_oportunidades(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    caminho, nome = await _salvar_temp(arquivo, "clientes")
    res = parse_oportunidades_arquivo(caminho)

    if res["total_validos"] == 0:
        raise HTTPException(400, {
            "message": "Nenhuma oportunidade válida na planilha.",
            "erros": res["erros"][:5],
        })

    upload_id = await _registrar_upload(
        conn, "OPORTUNIDADES", user["id"], nome,
        res["total_linhas"], res["total_validos"],
    )

    # Snapshot: TRUNCATE + INSERT
    async with conn.transaction():
        await conn.execute("TRUNCATE cliente_oportunidade RESTART IDENTITY CASCADE")
        # INSERT em lote — montar valores
        col_list = ", ".join(["upload_id"] + _OP_FIELDS)
        placeholders = ", ".join(
            f"${i+1}" for i in range(len(_OP_FIELDS) + 1)
        )
        sql = f"INSERT INTO cliente_oportunidade ({col_list}) VALUES ({placeholders})"

        batch = []
        for ln in res["linhas"]:
            batch.append([upload_id] + [ln.get(f) for f in _OP_FIELDS])

        await conn.executemany(sql, batch)
        await _marcar_processado(conn, upload_id)

    return {
        "upload_id": upload_id,
        "total_linhas": res["total_linhas"],
        "total_validos": res["total_validos"],
        "erros": res["erros"][:20],
    }


# ── Upload de Tarefas ────────────────────────────────────────────

@router.post("/upload-tarefas")
async def upload_tarefas(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    caminho, nome = await _salvar_temp(arquivo, "clientes")
    res = parse_tarefas_clientes_arquivo(caminho)

    if res["total_validos"] == 0:
        raise HTTPException(400, {
            "message": "Nenhuma tarefa válida na planilha.",
            "erros": res["erros"][:5],
        })

    upload_id = await _registrar_upload(
        conn, "TAREFAS", user["id"], nome,
        res["total_linhas"], res["total_validos"],
    )

    async with conn.transaction():
        await conn.execute("TRUNCATE cliente_tarefa RESTART IDENTITY CASCADE")
        col_list = ", ".join(["upload_id"] + _TAREFA_FIELDS)
        placeholders = ", ".join(
            f"${i+1}" for i in range(len(_TAREFA_FIELDS) + 1)
        )
        sql = f"INSERT INTO cliente_tarefa ({col_list}) VALUES ({placeholders})"

        batch = []
        for ln in res["linhas"]:
            batch.append([upload_id] + [ln.get(f) for f in _TAREFA_FIELDS])

        await conn.executemany(sql, batch)
        await _marcar_processado(conn, upload_id)

    return {
        "upload_id": upload_id,
        "total_linhas": res["total_linhas"],
        "total_validos": res["total_validos"],
        "erros": res["erros"][:20],
    }


# ── Listagem com filtros ─────────────────────────────────────────

@router.get("/oportunidades")
async def listar_oportunidades(
    q: str | None = Query(None, description="busca por razão social ou CNPJ"),
    status: str | None = Query(None),
    fase: str | None = Query(None),
    origem_macro: str | None = Query(None),
    cnpj_contador: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    where = []
    args: list[Any] = []
    if q:
        args.append(f"%{q}%")
        where.append(f"(razao_social ILIKE ${len(args)} OR cnpj ILIKE ${len(args)})")
    if status:
        args.append(status)
        where.append(f"status = ${len(args)}")
    if fase:
        args.append(fase)
        where.append(f"fase = ${len(args)}")
    if origem_macro:
        args.append(origem_macro)
        where.append(f"origem_macro = ${len(args)}")
    if cnpj_contador:
        args.append(cnpj_contador)
        where.append(f"cnpj_contador = ${len(args)}")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM cliente_oportunidade {where_sql}",
        *args,
    )

    args_paginado = args + [page_size, (page - 1) * page_size]
    sql = f"""
        SELECT op_id, cnpj, razao_social, status, fase, origem_macro,
               temperatura, previsao_valor, previsao_data,
               cnpj_contador, razao_contador, executivo_contas,
               ultima_tarefa_dias, dias_parado,
               data_criacao, data_atualizacao
        FROM cliente_oportunidade
        {where_sql}
        ORDER BY data_atualizacao DESC NULLS LAST, op_id DESC
        LIMIT ${len(args_paginado) - 1} OFFSET ${len(args_paginado)}
    """
    rows = await conn.fetch(sql, *args_paginado)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.get("/oportunidades/{op_id}")
async def detalhar_oportunidade(
    op_id: int,
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
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


@router.get("/tarefas")
async def listar_tarefas(
    q: str | None = Query(None),
    canal: str | None = Query(None),
    situacao: str | None = Query(None),
    status: str | None = Query(None),
    op_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    where = []
    args: list[Any] = []
    if q:
        args.append(f"%{q}%")
        where.append(f"(razao_social ILIKE ${len(args)} OR cnpj ILIKE ${len(args)})")
    if canal:
        args.append(canal)
        where.append(f"canal = ${len(args)}")
    if situacao:
        args.append(situacao)
        where.append(f"situacao_tarefa = ${len(args)}")
    if status:
        args.append(status)
        where.append(f"status = ${len(args)}")
    if op_id is not None:
        args.append(op_id)
        where.append(f"op_id = ${len(args)}")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM cliente_tarefa {where_sql}",
        *args,
    )

    args_paginado = args + [page_size, (page - 1) * page_size]
    sql = f"""
        SELECT tarefa_id, op_id, cnpj, razao_social,
               data_criacao, data_agendamento,
               fase_lead, status, finalidade, resultado,
               canal, situacao_tarefa, usuario_atribuido
        FROM cliente_tarefa
        {where_sql}
        ORDER BY data_agendamento DESC NULLS LAST, tarefa_id DESC
        LIMIT ${len(args_paginado) - 1} OFFSET ${len(args_paginado)}
    """
    rows = await conn.fetch(sql, *args_paginado)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


# ── Resumo / Histórico ───────────────────────────────────────────

@router.get("/resumo")
async def resumo(
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """Cards do topo do módulo Clientes."""
    op_total = await conn.fetchval("SELECT COUNT(*) FROM cliente_oportunidade") or 0
    op_em_andamento = await conn.fetchval(
        "SELECT COUNT(*) FROM cliente_oportunidade WHERE status ILIKE 'em andamento'"
    ) or 0
    op_conquistado = await conn.fetchval(
        "SELECT COUNT(*) FROM cliente_oportunidade WHERE status ILIKE 'conquistado'"
    ) or 0
    op_perdido = await conn.fetchval(
        "SELECT COUNT(*) FROM cliente_oportunidade WHERE status ILIKE 'perdido'"
    ) or 0
    op_cancelado = await conn.fetchval(
        "SELECT COUNT(*) FROM cliente_oportunidade WHERE status ILIKE 'cancelado'"
    ) or 0
    tarefa_total = await conn.fetchval("SELECT COUNT(*) FROM cliente_tarefa") or 0
    tarefa_atrasada = await conn.fetchval(
        "SELECT COUNT(*) FROM cliente_tarefa WHERE situacao_tarefa ILIKE 'atrasada'"
    ) or 0

    op_last = await conn.fetchrow(
        """
        SELECT data_upload, nome_arquivo, total_validos
        FROM cliente_upload
        WHERE tipo = 'OPORTUNIDADES' AND processado = TRUE
        ORDER BY data_upload DESC LIMIT 1
        """,
    )
    tarefa_last = await conn.fetchrow(
        """
        SELECT data_upload, nome_arquivo, total_validos
        FROM cliente_upload
        WHERE tipo = 'TAREFAS' AND processado = TRUE
        ORDER BY data_upload DESC LIMIT 1
        """,
    )

    return {
        "oportunidades": {
            "total": op_total,
            "em_andamento": op_em_andamento,
            "conquistado": op_conquistado,
            "perdido": op_perdido,
            "cancelado": op_cancelado,
        },
        "tarefas": {
            "total": tarefa_total,
            "atrasada": tarefa_atrasada,
        },
        "ultimo_upload_oportunidades": dict(op_last) if op_last else None,
        "ultimo_upload_tarefas":       dict(tarefa_last) if tarefa_last else None,
    }


@router.get("/historico")
async def historico(
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    rows = await conn.fetch(
        """
        SELECT id, tipo, data_upload, nome_arquivo, total_linhas, total_validos, processado
        FROM cliente_upload
        ORDER BY data_upload DESC
        LIMIT 30
        """,
    )
    return {"items": [dict(r) for r in rows]}


# ── Leads por contador (usado no drilldown da Carteira) ──────────

@router.get("/contador/{cnpj}/leads")
async def leads_do_contador(
    cnpj: str,
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Lista as oportunidades vinculadas a um CNPJ de contador.
    Usado pela aba "Leads" no drilldown do módulo Contadores.
    """
    rows = await conn.fetch(
        """
        SELECT op_id, cnpj, razao_social, status, fase, origem_macro,
               temperatura, previsao_valor, previsao_data,
               executivo_contas, executivo_vendas,
               ultima_tarefa_dias, dias_parado,
               data_criacao, data_atualizacao
        FROM cliente_oportunidade
        WHERE cnpj_contador = $1
        ORDER BY data_atualizacao DESC NULLS LAST, op_id DESC
        """,
        cnpj,
    )

    # KPIs do bloco
    total = len(rows)
    em_andamento = sum(1 for r in rows if (r["status"] or "").lower() == "em andamento")
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
