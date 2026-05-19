"""
HIPO — Router do módulo Carteira (Hunter / Farmer / Outros)

Endpoints:
  POST /carteira/upload-carteira      — substitui snapshot de carteira_cnpj
  POST /carteira/upload-tarefas       — substitui snapshot de carteira_tarefa
  GET  /carteira/grupos               — lista agregada (com filtros e abas)
  GET  /carteira/grupos/{id_grupo}    — drill-down (CNPJs + tarefas do grupo)
  GET  /carteira/colaboradores        — lista para o modal de configuração
  PUT  /carteira/colaboradores/{id}   — atualiza função
  GET  /carteira/historico            — últimos uploads
  GET  /carteira/resumo               — totais para os cards do topo

Dashboard por colaborador (layout v2):
  GET  /carteira/dashboard/hunter         — 1 linha por colab Hunter + KPIs
  GET  /carteira/dashboard/farmer         — 1 linha por colab Farmer + bolinhas semanais
  GET  /carteira/colaboradores/{id}/grupos — drilldown: grupos do colaborador
"""
from __future__ import annotations

import os
import uuid
import shutil
from datetime import date

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from parsers.carteira import parse_carteira_arquivo
from parsers.tarefas import parse_tarefas_arquivo
from services.carteira_agg import (
    agregar_grupos,
    aplicar_filtros,
    kpis_por_funcao,
    dashboard_hunter,
    dashboard_farmer,
    grupos_do_colaborador,
)

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")

FUNCOES_VALIDAS = {"EC_HUNTER", "EC_FARMER", "OUTROS"}


# ── Schemas Pydantic ─────────────────────────────────────────────

class ColaboradorUpdate(BaseModel):
    funcao: str = Field(..., description="EC_HUNTER | EC_FARMER | OUTROS")


# ── Helpers ──────────────────────────────────────────────────────

async def _salvar_temp(arquivo: UploadFile, subdir: str) -> tuple[str, str]:
    """Salva o upload em disco e devolve (caminho, nome_original)."""
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
        INSERT INTO carteira_upload
            (tipo, usuario_id, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ($1, $2, $3, $4, $5, FALSE)
        RETURNING id
        """,
        tipo, usuario_id, nome, total, validos,
    )


async def _carregar_estado(conn) -> tuple[list[dict], list[dict], list[dict]]:
    """Lê os 3 snapshots em memória — entrada do agregador."""
    cnpjs_rows = await conn.fetch("""
        SELECT id_grupo, nome_grupo, cnpj_contador, contabilidade,
               bairro, cidade_uf, parceria, data_parceria, tipo_cnae,
               colaborador_nome, funcao_origem, porte_faturamento,
               score_rfm, apps_ativos, mrr_ativo, leads_no_mes, status_rf
        FROM carteira_cnpj
    """)
    tarefas_rows = await conn.fetch("""
        SELECT cnpj_contador, contabilidade, executivo_nome,
               situacao::text AS situacao, status, tarefa_canal,
               tipo_tarefa, resultado, data_criacao, data_agendamento,
               data_efetiva
        FROM carteira_tarefa
    """)
    colab_rows = await conn.fetch("""
        SELECT id, nome, funcao::text AS funcao, funcao_origem
        FROM carteira_colaborador WHERE ativo = TRUE
    """)
    return (
        [dict(r) for r in cnpjs_rows],
        [dict(r) for r in tarefas_rows],
        [dict(r) for r in colab_rows],
    )


# ── UPLOAD: CARTEIRA ─────────────────────────────────────────────

@router.post("/upload-carteira")
async def upload_carteira(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Substitui o snapshot da carteira (somente CNAE Contábil).
    Atualiza a lista de colaboradores: novos nomes entram com função 'OUTROS';
    nomes que sumiram são marcados como ativo=FALSE (mas a função é preservada).
    """
    caminho, nome = await _salvar_temp(arquivo, "carteira")

    res = parse_carteira_arquivo(caminho)

    if res["erros"] and not res["linhas"]:
        os.remove(caminho)
        raise HTTPException(422, {"erros": res["erros"]})

    if res["total_validos"] == 0:
        os.remove(caminho)
        raise HTTPException(422, "Nenhuma linha CNAE Contábil encontrada na planilha.")

    upload_id = await _registrar_upload(
        conn, "CARTEIRA", user["id"], nome, res["total_linhas"], res["total_validos"]
    )

    # Substitui snapshot (mesma filosofia do BD Ativados)
    await conn.execute("DELETE FROM carteira_cnpj")

    for l in res["linhas"]:
        await conn.execute(
            """
            INSERT INTO carteira_cnpj (
                upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade,
                bairro, cidade_uf, parceria, data_parceria, tipo_cnae,
                colaborador_nome, funcao_origem, porte_faturamento,
                score_rfm, apps_ativos, mrr_ativo, leads_no_mes, status_rf
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18
            )
            """,
            upload_id,
            l.get("id_grupo"),
            l.get("nome_grupo"),
            l.get("cnpj_contador"),
            l.get("contabilidade"),
            l.get("bairro"),
            l.get("cidade_uf"),
            l.get("parceria"),
            l.get("data_parceria"),
            l.get("tipo_cnae"),
            l.get("colaborador_nome"),
            l.get("funcao_origem"),
            l.get("porte_faturamento"),
            l.get("score_rfm"),
            l.get("apps_ativos"),
            l.get("mrr_ativo"),
            l.get("leads_no_mes"),
            l.get("status_rf"),
        )

    # Sincroniza colaboradores
    nomes_atuais = {c["nome"] for c in res["colaboradores"]}
    for c in res["colaboradores"]:
        await conn.execute(
            """
            INSERT INTO carteira_colaborador (nome, funcao_origem)
            VALUES ($1, $2)
            ON CONFLICT (nome) DO UPDATE SET
                funcao_origem = EXCLUDED.funcao_origem,
                ativo = TRUE,
                updated_at = NOW()
            """,
            c["nome"], c.get("funcao_origem"),
        )
    # Desativa quem sumiu (mantém a função pra retomar se voltar)
    if nomes_atuais:
        await conn.execute(
            "UPDATE carteira_colaborador SET ativo = FALSE WHERE nome <> ALL($1::text[])",
            list(nomes_atuais),
        )
    else:
        await conn.execute("UPDATE carteira_colaborador SET ativo = FALSE")

    await conn.execute(
        "UPDATE carteira_upload SET processado = TRUE WHERE id = $1", upload_id
    )

    return {
        "upload_id": str(upload_id),
        "total_linhas": res["total_linhas"],
        "total_validos": res["total_validos"],
        "colaboradores_total": len(res["colaboradores"]),
        "message": f"Carteira atualizada: {res['total_validos']} CNPJs CNAE Contábil.",
    }


# ── UPLOAD: TAREFAS ──────────────────────────────────────────────

@router.post("/upload-tarefas")
async def upload_tarefas(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Substitui o snapshot de tarefas."""
    caminho, nome = await _salvar_temp(arquivo, "tarefas")

    res = parse_tarefas_arquivo(caminho)
    if res["erros"] and not res["linhas"]:
        os.remove(caminho)
        raise HTTPException(422, {"erros": res["erros"]})

    if res["total_validos"] == 0:
        os.remove(caminho)
        raise HTTPException(422, "Nenhuma tarefa válida encontrada.")

    upload_id = await _registrar_upload(
        conn, "TAREFAS", user["id"], nome, res["total_linhas"], res["total_validos"]
    )

    await conn.execute("DELETE FROM carteira_tarefa")

    for t in res["linhas"]:
        await conn.execute(
            """
            INSERT INTO carteira_tarefa (
                upload_id, tarefa_id_origem, cnpj_contador, contabilidade,
                executivo_nome, situacao, status, tarefa_canal, tipo_tarefa,
                resultado, data_criacao, data_agendamento, data_efetiva
            ) VALUES (
                $1,$2,$3,$4,$5,$6::tarefa_situacao_enum,$7,$8,$9,$10,$11,$12,$13
            )
            """,
            upload_id,
            t.get("tarefa_id_origem"),
            t.get("cnpj_contador"),
            t.get("contabilidade"),
            t.get("executivo_nome"),
            t.get("situacao", "DESCONHECIDA"),
            t.get("status"),
            t.get("tarefa_canal"),
            t.get("tipo_tarefa"),
            t.get("resultado"),
            t.get("data_criacao"),
            t.get("data_agendamento"),
            t.get("data_efetiva"),
        )

    await conn.execute(
        "UPDATE carteira_upload SET processado = TRUE WHERE id = $1", upload_id
    )

    return {
        "upload_id": str(upload_id),
        "total_linhas": res["total_linhas"],
        "total_validos": res["total_validos"],
        "message": f"Tarefas atualizadas: {res['total_validos']} registros.",
    }


# ── GRUPOS ───────────────────────────────────────────────────────

@router.get("/grupos")
async def listar_grupos(
    funcao: str | None = Query(None, description="EC_HUNTER | EC_FARMER | OUTROS"),
    tarefa_atrasada: bool = False,
    sem_tarefa_futura: bool = False,
    busca: str | None = None,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if funcao and funcao not in FUNCOES_VALIDAS:
        raise HTTPException(400, f"Função inválida: {funcao}")

    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)

    filtrados = aplicar_filtros(
        grupos,
        funcao=funcao,
        tarefa_atrasada=tarefa_atrasada,
        sem_tarefa_futura=sem_tarefa_futura,
        busca=busca,
    )

    # Ordena: meta_atingida=False primeiro (ação imediata),
    # depois por leads_no_mes desc (mais oportunidade vai pro topo)
    filtrados.sort(key=lambda g: (g["meta_atingida"], -g["leads_no_mes"]))

    return {
        "total": len(filtrados),
        "grupos": filtrados,
    }


@router.get("/grupos/{id_grupo}")
async def detalhe_grupo(
    id_grupo: str,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Drill-down: lista de CNPJs e tarefas do grupo."""
    cnpjs_rows = await conn.fetch(
        """
        SELECT id_grupo, nome_grupo, cnpj_contador, contabilidade, bairro, cidade_uf,
               parceria, data_parceria, colaborador_nome, funcao_origem,
               apps_ativos, mrr_ativo, leads_no_mes, status_rf
        FROM carteira_cnpj
        WHERE id_grupo = $1
        ORDER BY contabilidade NULLS LAST
        """,
        id_grupo,
    )
    if not cnpjs_rows:
        raise HTTPException(404, "Grupo não encontrado")

    cnpjs = [dict(r) for r in cnpjs_rows]
    cnpj_lista = [c["cnpj_contador"] for c in cnpjs if c.get("cnpj_contador")]

    tarefas_rows = []
    if cnpj_lista:
        tarefas_rows = await conn.fetch(
            """
            SELECT cnpj_contador, contabilidade, executivo_nome,
                   situacao::text AS situacao, status, tarefa_canal,
                   tipo_tarefa, resultado, data_criacao, data_agendamento,
                   data_efetiva
            FROM carteira_tarefa
            WHERE cnpj_contador = ANY($1::text[])
            ORDER BY data_efetiva DESC NULLS LAST
            LIMIT 200
            """,
            cnpj_lista,
        )

    return {
        "id_grupo": id_grupo,
        "qtd_cnpj": len(cnpjs),
        "cnpjs": cnpjs,
        "tarefas": [dict(r) for r in tarefas_rows],
    }


# ── COLABORADORES (config) ───────────────────────────────────────

@router.get("/colaboradores")
async def listar_colaboradores(
    incluir_inativos: bool = False,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if incluir_inativos:
        rows = await conn.fetch("""
            SELECT id, nome, funcao::text AS funcao, funcao_origem, ativo, updated_at
            FROM carteira_colaborador
            ORDER BY ativo DESC, nome
        """)
    else:
        rows = await conn.fetch("""
            SELECT id, nome, funcao::text AS funcao, funcao_origem, ativo, updated_at
            FROM carteira_colaborador
            WHERE ativo = TRUE
            ORDER BY nome
        """)
    return [dict(r) for r in rows]


@router.put("/colaboradores/{colab_id}")
async def atualizar_colaborador(
    colab_id: str,
    payload: ColaboradorUpdate,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if payload.funcao not in FUNCOES_VALIDAS:
        raise HTTPException(400, f"Função inválida: {payload.funcao}")

    try:
        colab_uuid = uuid.UUID(colab_id)
    except ValueError:
        raise HTTPException(400, "ID inválido")

    updated = await conn.fetchrow(
        """
        UPDATE carteira_colaborador
        SET funcao = $1::carteira_funcao_enum, updated_at = NOW()
        WHERE id = $2
        RETURNING id, nome, funcao::text AS funcao
        """,
        payload.funcao, colab_uuid,
    )
    if not updated:
        raise HTTPException(404, "Colaborador não encontrado")

    return dict(updated)


# ── HISTÓRICO ────────────────────────────────────────────────────

@router.get("/historico")
async def historico(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    rows = await conn.fetch("""
        SELECT
            cu.id, cu.tipo, cu.data_upload, cu.nome_arquivo,
            cu.total_linhas, cu.total_validos, cu.processado,
            u.nome AS usuario_nome
        FROM carteira_upload cu
        LEFT JOIN usuarios u ON u.id = cu.usuario_id
        ORDER BY cu.data_upload DESC
        LIMIT 50
    """)
    return [dict(r) for r in rows]


# ── RESUMO (cards do topo) ───────────────────────────────────────

@router.get("/resumo")
async def resumo(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)

    ultima_carteira = await conn.fetchrow(
        "SELECT data_upload FROM carteira_upload "
        "WHERE tipo='CARTEIRA' AND processado=TRUE "
        "ORDER BY data_upload DESC LIMIT 1"
    )
    ultima_tarefas = await conn.fetchrow(
        "SELECT data_upload FROM carteira_upload "
        "WHERE tipo='TAREFAS' AND processado=TRUE "
        "ORDER BY data_upload DESC LIMIT 1"
    )

    return {
        "hunter":  kpis_por_funcao(grupos, "EC_HUNTER"),
        "farmer":  kpis_por_funcao(grupos, "EC_FARMER"),
        "outros":  kpis_por_funcao(grupos, "OUTROS"),
        "totais": {
            "grupos_total": len(grupos),
            "cnpjs_total":  len(cnpjs),
            "tarefas_total": len(tarefas),
            "colaboradores": len(colab),
        },
        "ultima_carteira": ultima_carteira["data_upload"].isoformat() if ultima_carteira else None,
        "ultima_tarefas":  ultima_tarefas["data_upload"].isoformat() if ultima_tarefas else None,
    }


# ─────────────────────────────────────────────────────────────────
#  DASHBOARD por colaborador (v2 — layout linha-por-pessoa)
# ─────────────────────────────────────────────────────────────────

@router.get("/dashboard/hunter")
async def dashboard_hunter_endpoint(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Lista 1 linha por colaborador EC_HUNTER com agregados do mês:
      total_grupos, meta_atingida, tarefas_atrasadas, sem_tarefa_futura,
      leads_no_mes, compliance_pct.
    Ordenado por compliance descendente (melhor primeiro).
    """
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)
    return {
        "total": len([c for c in colab if c["funcao"] == "EC_HUNTER"]),
        "linhas": dashboard_hunter(grupos, colab),
    }


@router.get("/dashboard/farmer")
async def dashboard_farmer_endpoint(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Lista 1 linha por colaborador EC_FARMER. Cada linha tem:
      - total_contadores: nº de CNPJs distintos atribuídos ao colab
      - semanas: lista das semanas ISO do mês corrente; cada uma com
        com_reuniao / sem_reuniao / pendente (contagem de CONTADORES).
      - tarefas_atrasadas, tarefas_futuras, leads_no_mes.
    """
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    return {
        "total": len([c for c in colab if c["funcao"] == "EC_FARMER"]),
        "linhas": dashboard_farmer(cnpjs, tarefas, colab),
    }


@router.get("/colaboradores/{colab_id}/grupos")
async def grupos_do_colaborador_endpoint(
    colab_id: str,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Drilldown: devolve os grupos atribuídos a um colaborador específico.
    Mesmo schema do GET /grupos, mas filtrado pelo ID.
    """
    try:
        colab_uuid = uuid.UUID(colab_id)
    except ValueError:
        raise HTTPException(400, "ID inválido")

    colaborador = await conn.fetchrow(
        "SELECT id, nome, funcao::text AS funcao FROM carteira_colaborador WHERE id = $1",
        colab_uuid,
    )
    if not colaborador:
        raise HTTPException(404, "Colaborador não encontrado")

    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)
    do_colab = grupos_do_colaborador(grupos, colaborador["nome"])

    # Ordena pela meta_atingida (não atingida primeiro = ação imediata),
    # depois por leads_no_mes desc (oportunidade vai pro topo).
    do_colab.sort(key=lambda g: (g["meta_atingida"], -g["leads_no_mes"]))

    return {
        "colaborador": {
            "id": str(colaborador["id"]),
            "nome": colaborador["nome"],
            "funcao": colaborador["funcao"],
        },
        "total": len(do_colab),
        "grupos": do_colab,
    }
