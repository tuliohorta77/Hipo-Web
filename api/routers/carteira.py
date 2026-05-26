"""
HIPO — Router do módulo Carteira (Hunter / Farmer / Outros)

Endpoints:
  POST /carteira/upload-carteira      — substitui snapshot de carteira_cnpj
  POST /carteira/upload-tarefas       — substitui snapshot de carteira_tarefa
  GET  /carteira/grupos               — lista agregada (com filtros e abas)
  GET  /carteira/grupos/{id_grupo}    — drill-down (CNPJs + tarefas do grupo)
  GET  /carteira/colaboradores        — lista para o modal de configuração
  PUT  /carteira/colaboradores/{id}   — atualiza função e/ou vínculo de usuário
  GET  /carteira/usuarios-ativos      — usuários ativos (dropdown de vínculo)
  GET  /carteira/historico            — últimos uploads
  GET  /carteira/resumo               — totais para os cards do topo
  GET  /carteira/relacionamento       — grupos Farmer via bastão do Hunter

Dashboard por colaborador (layout v2):
  GET  /carteira/dashboard/hunter         — 1 linha por colab Hunter + KPIs
  GET  /carteira/dashboard/farmer         — 1 linha por colab Farmer + bolinhas semanais
  GET  /carteira/colaboradores/{id}/grupos — drilldown: grupos do colaborador

Visibilidade por colaborador (v1.3.0 — Etapa 2 completa):
  Cargos operacionais (Hunter, Farmer, ...) só enxergam o colaborador
  vinculado ao seu usuário (carteira_colaborador.usuario_id). Cargos
  admin/gestão (ADM, Franqueado, Gerente, EP) veem tudo. A decisão é
  centralizada em permissions.deve_filtrar_por_usuario().
  Os 3 dashboards (hunter, farmer, resumo) filtram; /grupos (aba Outros)
  permanece visível a todos por decisão de produto.
"""
from __future__ import annotations

import os
import uuid
import shutil
from datetime import date

import asyncpg
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import deve_filtrar_por_usuario
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
from services.carteira_relacionamento import cruzar_bastoes_com_grupos
from services import bastao as svc_bastao

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")

FUNCOES_VALIDAS = {"EC_HUNTER", "EC_FARMER", "OUTROS"}

# Mensagem para operacional (Hunter/Farmer) sem colaborador vinculado.
AVISO_SEM_VINCULO = (
    "Sua carteira ainda não foi configurada. "
    "Peça ao gestor para vincular seu usuário a um colaborador."
)

# Cargos que podem consultar o Relacionamento de outro Hunter via ?hunter=.
# Mesma política do /bastoes/meus em routers/bastao.py.
_CARGOS_VE_OUTRO_HUNTER = {"ADM", "Franqueado", "Gerente", "EP"}


# ── Schemas Pydantic ─────────────────────────────────────────────

class ColaboradorUpdate(BaseModel):
    """
    Payload do PUT /colaboradores/{id}.

    `funcao` é obrigatório (mantém o comportamento anterior do endpoint).

    `usuario_id` é OPCIONAL e tri-estado, distinguido via model_fields_set:
      - campo ausente no JSON  -> o vínculo NÃO é alterado;
      - campo presente com valor (UUID em string) -> vincula ao usuário;
      - campo presente com null -> desvincula (usuario_id = NULL).
    """
    funcao: str = Field(..., description="EC_HUNTER | EC_FARMER | OUTROS")
    usuario_id: str | None = Field(
        default=None,
        description="UUID do usuário a vincular; null desvincula; "
                    "omitir o campo mantém o vínculo atual.",
    )


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
        SELECT id, nome, funcao::text AS funcao, funcao_origem, usuario_id
        FROM carteira_colaborador WHERE ativo = TRUE
    """)
    return (
        [dict(r) for r in cnpjs_rows],
        [dict(r) for r in tarefas_rows],
        [dict(r) for r in colab_rows],
    )


async def _colaborador_do_usuario(conn, user: dict) -> dict | None:
    """
    Traduz o usuário logado -> colaborador da carteira vinculado a ele.

    O vínculo é a coluna carteira_colaborador.usuario_id (v1.3.0 etapa 1).
    Retorna o dict do colaborador (id, nome, funcao) ou None se o usuário
    não estiver vinculado a nenhum colaborador ativo.
    """
    row = await conn.fetchrow(
        """
        SELECT id, nome, funcao::text AS funcao
        FROM carteira_colaborador
        WHERE usuario_id = $1 AND ativo = TRUE
        """,
        user["id"],
    )
    return dict(row) if row else None


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
    """
    Lista agregada de grupos. NÃO é filtrado por usuário (decisão de produto
    v1.3.0: a aba 'Outros' é visível para todos os cargos, inclusive
    operacionais — é uma fila de correção de bagunça da carteira).
    """
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
    """
    Lista colaboradores para o modal de configuração.

    Cada linha traz o vínculo de usuário (v1.3.0):
      - usuario_id    : UUID do usuário vinculado, ou null;
      - usuario_email : email do usuário vinculado, ou null;
      - usuario_nome  : nome do usuário vinculado, ou null.
    O LEFT JOIN garante que colaboradores SEM vínculo continuem na lista
    (decisão de produto: aparecem para o gestor com aviso "sem usuário").

    NÃO é filtrado por usuário: além do modal de configuração, alimenta
    o dropdown de Farmers do modal de passagem de bastão (BastaoModal),
    que precisa de todos os Farmers ativos independentemente de quem
    está logado.
    """
    if incluir_inativos:
        rows = await conn.fetch("""
            SELECT c.id, c.nome, c.funcao::text AS funcao, c.funcao_origem,
                   c.ativo, c.updated_at,
                   c.usuario_id, u.email AS usuario_email, u.nome AS usuario_nome
            FROM carteira_colaborador c
            LEFT JOIN usuarios u ON u.id = c.usuario_id
            ORDER BY c.ativo DESC, c.nome
        """)
    else:
        rows = await conn.fetch("""
            SELECT c.id, c.nome, c.funcao::text AS funcao, c.funcao_origem,
                   c.ativo, c.updated_at,
                   c.usuario_id, u.email AS usuario_email, u.nome AS usuario_nome
            FROM carteira_colaborador c
            LEFT JOIN usuarios u ON u.id = c.usuario_id
            WHERE c.ativo = TRUE
            ORDER BY c.nome
        """)
    return [dict(r) for r in rows]


@router.put("/colaboradores/{colab_id}")
async def atualizar_colaborador(
    colab_id: str,
    payload: ColaboradorUpdate,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Atualiza a função do colaborador e, opcionalmente, o vínculo de usuário.

    Tri-estado do campo `usuario_id` (ver ColaboradorUpdate):
      - ausente -> vínculo intacto;
      - UUID    -> vincula;
      - null    -> desvincula.

    Cardinalidade 1:1: um usuário só pode estar vinculado a um colaborador.
    Tentar reutilizar um usuário já vinculado devolve 409.
    """
    if payload.funcao not in FUNCOES_VALIDAS:
        raise HTTPException(400, f"Função inválida: {payload.funcao}")

    try:
        colab_uuid = uuid.UUID(colab_id)
    except ValueError:
        raise HTTPException(400, "ID inválido")

    mexer_no_vinculo = "usuario_id" in payload.model_fields_set

    # Resolve o usuario_id alvo (quando o campo veio no payload).
    usuario_uuid = None
    if mexer_no_vinculo and payload.usuario_id is not None:
        try:
            usuario_uuid = uuid.UUID(payload.usuario_id)
        except ValueError:
            raise HTTPException(400, "usuario_id inválido")
        existe = await conn.fetchval(
            "SELECT 1 FROM usuarios WHERE id = $1 AND ativo = TRUE", usuario_uuid
        )
        if not existe:
            raise HTTPException(400, "Usuário não encontrado ou inativo.")

    try:
        if mexer_no_vinculo:
            updated = await conn.fetchrow(
                """
                UPDATE carteira_colaborador
                SET funcao = $1::carteira_funcao_enum,
                    usuario_id = $2,
                    updated_at = NOW()
                WHERE id = $3
                RETURNING id, nome, funcao::text AS funcao, usuario_id
                """,
                payload.funcao, usuario_uuid, colab_uuid,
            )
        else:
            updated = await conn.fetchrow(
                """
                UPDATE carteira_colaborador
                SET funcao = $1::carteira_funcao_enum, updated_at = NOW()
                WHERE id = $2
                RETURNING id, nome, funcao::text AS funcao, usuario_id
                """,
                payload.funcao, colab_uuid,
            )
    except asyncpg.UniqueViolationError:
        # usuario_id já está vinculado a outro colaborador (constraint 1:1).
        outro = await conn.fetchrow(
            "SELECT nome FROM carteira_colaborador WHERE usuario_id = $1",
            usuario_uuid,
        )
        nome_outro = outro["nome"] if outro else "outro colaborador"
        raise HTTPException(
            409,
            f"Este usuário já está vinculado ao colaborador '{nome_outro}'. "
            f"Cada usuário pode estar vinculado a apenas um colaborador.",
        )

    if not updated:
        raise HTTPException(404, "Colaborador não encontrado")

    row = dict(updated)
    if row.get("usuario_id") is not None:
        row["usuario_id"] = str(row["usuario_id"])
    return row


@router.get("/usuarios-ativos")
async def listar_usuarios_ativos(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Lista os usuários ativos para o dropdown de vínculo na tela Configurar.
    Retorna apenas id, nome e email — sem dados sensíveis.
    """
    rows = await conn.fetch("""
        SELECT id, nome, email
        FROM usuarios
        WHERE ativo = TRUE
        ORDER BY nome
    """)
    return [
        {"id": str(r["id"]), "nome": r["nome"], "email": r["email"]}
        for r in rows
    ]


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
    """
    Totais para os cards do topo da tela Contadores.

    Visibilidade por colaborador (v1.3.0):
      - Cargo operacional COM vínculo  -> KPIs calculados só sobre os
        grupos do colaborador vinculado.
      - Cargo operacional SEM vínculo  -> KPIs zerados + campo 'aviso'.
      - Cargo admin/gestão             -> KPIs da unidade inteira.
    """
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)

    aviso = None
    if deve_filtrar_por_usuario(user.get("cargo")):
        meu_colab = await _colaborador_do_usuario(conn, user)
        if meu_colab is None:
            # Operacional sem vínculo: nada a mostrar.
            grupos = []
            aviso = AVISO_SEM_VINCULO
        else:
            grupos = [
                g for g in grupos
                if g.get("colaborador_nome") == meu_colab["nome"]
            ]

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
        "aviso": aviso,
        "ultima_carteira": ultima_carteira["data_upload"].isoformat() if ultima_carteira else None,
        "ultima_tarefas":  ultima_tarefas["data_upload"].isoformat() if ultima_tarefas else None,
    }


# ── RELACIONAMENTO (Hunter — grupos passados via bastão) ─────────

@router.get("/relacionamento")
async def relacionamento(
    hunter: str | None = Query(
        None,
        description="Nome do Hunter. Cargos admin/gestão podem consultar "
                    "outro Hunter; operacionais ignoram o parâmetro.",
    ),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Sub-aba 'Relacionamento' do Hunter: os grupos Farmer correspondentes
    aos contadores que o Hunter passou via bastão APROVADO.

    Move para o backend o cruzamento bastão ↔ grupo que antes era feito
    no frontend (BastaoLista.jsx). Assim /dashboard/farmer pode ser
    filtrado por usuário sem quebrar o Relacionamento.

    Resolução do Hunter-alvo:
      - Cargo operacional  -> sempre o colaborador vinculado ao seu
        usuário (ignora o parâmetro ?hunter=). Sem vínculo -> 'aviso'.
      - Cargo admin/gestão -> usa ?hunter=NOME se informado; senão,
        usa o próprio nome do usuário logado.

    Retorno:
      - hunter_nome: str — o Hunter efetivamente consultado
      - grupos: list[dict] — grupos Farmer via bastão (formato Farmer)
      - bastoes_sem_grupo: list[dict] — bastões aprovados ainda sem grupo
      - kpis: dict — total_grupos, com_atrasada, com_futura, leads
      - aviso: str | null — preenchido quando operacional sem vínculo
    """
    cargo = user.get("cargo")

    # 1) Resolve de qual Hunter é o Relacionamento.
    if deve_filtrar_por_usuario(cargo):
        # Operacional: só o próprio colaborador vinculado.
        meu_colab = await _colaborador_do_usuario(conn, user)
        if meu_colab is None:
            return {
                "hunter_nome": None,
                "grupos": [],
                "bastoes_sem_grupo": [],
                "kpis": {"total_grupos": 0, "com_atrasada": 0,
                         "com_futura": 0, "leads": 0},
                "aviso": AVISO_SEM_VINCULO,
            }
        hunter_nome = meu_colab["nome"]
    else:
        # Admin/gestão: ?hunter= se veio; senão, o próprio nome.
        if hunter and cargo in _CARGOS_VE_OUTRO_HUNTER:
            hunter_nome = hunter
        else:
            hunter_nome = user.get("nome")
        if not hunter_nome:
            raise HTTPException(
                400,
                "Não foi possível determinar o Hunter. "
                "Informe ?hunter=NOME.",
            )

    # 2) Bastões do Hunter (reusa o service de bastão).
    bastoes = await svc_bastao.listar_bastoes_do_hunter(conn, hunter_nome)

    # 3) Grupos Farmer agregados.
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)
    grupos_farmer = [g for g in grupos if g.get("funcao") == "EC_FARMER"]

    # 4) Cruzamento bastão ↔ grupo (service puro).
    resultado = cruzar_bastoes_com_grupos(bastoes, grupos_farmer)

    return {
        "hunter_nome": hunter_nome,
        "grupos": resultado["grupos"],
        "bastoes_sem_grupo": resultado["bastoes_sem_grupo"],
        "kpis": resultado["kpis"],
        "aviso": None,
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

    Visibilidade por colaborador (v1.3.0):
      - Cargo operacional COM vínculo  -> só a linha do colaborador dele.
      - Cargo operacional SEM vínculo  -> linhas=[] + campo 'aviso'.
      - Cargo admin/gestão             -> todas as linhas Hunter.
    """
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    grupos = agregar_grupos(cnpjs, tarefas, colab)
    linhas = dashboard_hunter(grupos, colab)

    aviso = None
    if deve_filtrar_por_usuario(user.get("cargo")):
        meu_colab = await _colaborador_do_usuario(conn, user)
        if meu_colab is None:
            return {"total": 0, "linhas": [], "aviso": AVISO_SEM_VINCULO}
        linhas = [l for l in linhas if l.get("nome") == meu_colab["nome"]]

    return {
        "total": len(linhas),
        "linhas": linhas,
        "aviso": aviso,
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

    Visibilidade por colaborador (v1.3.0 — Etapa 2c):
      - Cargo operacional COM vínculo  -> só a linha do colaborador dele.
      - Cargo operacional SEM vínculo  -> linhas=[] + campo 'aviso'.
      - Cargo admin/gestão             -> todas as linhas Farmer.

    NOTA: a sub-aba Relacionamento do Hunter NÃO depende mais deste
    endpoint — o cruzamento bastão↔grupo agora é feito pelo endpoint
    /carteira/relacionamento (Commit 2b). Por isso este endpoint pode
    ser filtrado sem quebrar o Relacionamento.
    """
    cnpjs, tarefas, colab = await _carregar_estado(conn)
    linhas = dashboard_farmer(cnpjs, tarefas, colab)

    aviso = None
    if deve_filtrar_por_usuario(user.get("cargo")):
        meu_colab = await _colaborador_do_usuario(conn, user)
        if meu_colab is None:
            return {"total": 0, "linhas": [], "aviso": AVISO_SEM_VINCULO}
        linhas = [l for l in linhas if l.get("nome") == meu_colab["nome"]]

    return {
        "total": len(linhas),
        "linhas": linhas,
        "aviso": aviso,
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

    Visibilidade por colaborador (v1.3.0):
      - Cargo operacional só pode acessar o drilldown do PRÓPRIO
        colaborador vinculado. Tentar o ID de outro colaborador devolve
        403 (não 404, não lista vazia — bloqueio explícito, para não
        permitir bisbilhotar trocando o ID na URL).
      - Cargo admin/gestão acessa o drilldown de qualquer colaborador.
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

    # Controle de acesso: operacional só vê o próprio colaborador.
    if deve_filtrar_por_usuario(user.get("cargo")):
        meu_colab = await _colaborador_do_usuario(conn, user)
        if meu_colab is None or str(meu_colab["id"]) != str(colaborador["id"]):
            raise HTTPException(
                403,
                "Você não tem acesso à carteira deste colaborador.",
            )

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
