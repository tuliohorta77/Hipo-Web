"""
HIPO -- Router de Passagem de Bastão.

Endpoints (montados em /carteira/* via main.py):
  GET    /carteira/bastoes/contador?cnpj=...   -- lookup pro modal (sem registrar nada)
  POST   /carteira/bastoes                     -- Hunter cria (PENDENTE)
  GET    /carteira/bastoes/meus                -- Hunter vê seus próprios
  GET    /carteira/bastoes/pendentes           -- Aprovador (Gerente/Franqueado): fila
  GET    /carteira/bastoes/kpis/{hunter}       -- KPIs agregados pro header
  PATCH  /carteira/bastoes/{id}/aprovar        -- Gerente/Franqueado aprovam
  PATCH  /carteira/bastoes/{id}/rejeitar       -- Gerente/Franqueado rejeitam (com motivo)
  DELETE /carteira/bastoes/{id}                -- Hunter remove (soft delete)

Guard:
  - Todas as rotas usam dependency_modulo("carteira") herdada do main.py
  - Endpoints de aprovação (aprovar/rejeitar/listar pendentes) verificam cargo
    dentro do handler — restritos a Gerente/Franqueado (NÃO ADM).

NOTA sobre o lookup de contador: CNPJ é passado via query (?cnpj=...)
em vez de path. Motivo: o CNPJ com mascara (XX.XXX.XXX/XXXX-XX) contém
'/' e o FastAPI interpreta isso como separador de path, gerando 404
de "rota não encontrada" em vez de chamar o handler.

NOTA sobre permissões (v1.2.0 etapa 3): aprovação de bastão é tratada
como FLUXO DE OPERAÇÕES — competência do Gerente e do Franqueado, não
do ADM (que cuida de outras frentes do Hipo). ADM consegue ver todos
os bastões via /meus?hunter=X, mas não aprova/rejeita.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from services import bastao as svc


router = APIRouter()


# ── Models (input) ────────────────────────────────────────────

class BastaoCreateIn(BaseModel):
    farmer_nome: str = Field(..., min_length=1, max_length=150)
    cnpj_contador: str = Field(..., min_length=14, max_length=20)
    data_parceria: date
    leads_iniciais: int = Field(..., ge=0)
    observacoes: str | None = Field(None, max_length=1000)


class BastaoRejectIn(BaseModel):
    motivo: str = Field(..., min_length=1, max_length=500)


# ── Helpers ───────────────────────────────────────────────────

# Cargos que APROVAM bastão. Operações de carteira são do
# Gerente e do Franqueado — ADM cuida de outras frentes do Hipo.
_CARGOS_APROVADOR = {"Gerente", "Franqueado"}

# Cargos com privilégios administrativos (para /meus?hunter=X e remover
# bastão alheio). ADM continua tendo poder operacional pra esses casos
# excepcionais, mesmo sem poder aprovar a fila normal.
_CARGOS_ADM_GERAL = {"ADM", "Franqueado", "Gerente"}


def _exigir_aprovador(user: dict) -> None:
    """Restringe a Gerente/Franqueado. Levanta 403 caso contrário."""
    cargo = user.get("cargo")
    if cargo not in _CARGOS_APROVADOR:
        raise HTTPException(
            403,
            f"Apenas Gerente/Franqueado pode aprovar ou rejeitar bastões "
            f"(cargo atual: '{cargo}').",
        )


def _hunter_nome_do_user(user: dict) -> str:
    """
    Resolve o 'hunter_nome' do usuário logado.

    Convenção: o `nome` da usuarios deve casar com `carteira_colaborador.nome`
    e com `carteira_cnpj.colaborador_nome` (todos vêm da mesma fonte).
    """
    nome = user.get("nome")
    if not nome:
        raise HTTPException(400, "Usuário sem nome cadastrado.")
    return nome


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/bastoes/contador")
async def lookup_contador(
    cnpj: str = Query(..., description="CNPJ com ou sem máscara (formato livre)"),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Lookup pro modal de inclusão de bastão.
    Não cria nada — só confere se o CNPJ existe na carteira.

    CNPJ é query param (não path) porque a máscara XX.XXX.XXX/XXXX-XX
    contém '/' que o FastAPI interpreta como separador de rota.
    """
    try:
        return await svc.buscar_contador_por_cnpj(conn, cnpj)
    except svc.ContadorNaoEncontrado as e:
        raise HTTPException(404, str(e))


@router.post("/bastoes", status_code=201)
async def criar_bastao(
    body: BastaoCreateIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Hunter cria registro PENDENTE. Aguarda aprovação do Gerente/Franqueado.
    """
    hunter_nome = _hunter_nome_do_user(user)
    try:
        row = await svc.criar_bastao(
            conn,
            hunter_nome=hunter_nome,
            farmer_nome=body.farmer_nome,
            cnpj_contador=body.cnpj_contador,
            data_parceria=body.data_parceria,
            leads_iniciais=body.leads_iniciais,
            criado_por=user["id"],
            observacoes=body.observacoes,
        )
        return row
    except svc.ContadorNaoEncontrado as e:
        raise HTTPException(404, str(e))
    except svc.CnpjJaTemBastaoAtivo as e:
        raise HTTPException(409, str(e))


@router.get("/bastoes/meus")
async def meus_bastoes(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
    hunter: str | None = Query(
        None,
        description="Cargos com privilégio admin podem filtrar por hunter. Outros ignoram.",
    ),
):
    """
    Lista bastões deste usuário (todos os status).
    ADM/Gerente/Franqueado podem passar ?hunter=NOME pra ver de outros.
    """
    cargo = user.get("cargo")
    if cargo in _CARGOS_ADM_GERAL and hunter:
        nome = hunter
    else:
        nome = _hunter_nome_do_user(user)
    return await svc.listar_bastoes_do_hunter(conn, nome)


@router.get("/bastoes/pendentes")
async def fila_pendentes(
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Fila de aprovação — Gerente/Franqueado vê o que precisa aprovar."""
    _exigir_aprovador(user)
    return await svc.listar_bastoes_pendentes(conn)


@router.get("/bastoes/kpis/{hunter_nome}")
async def kpis_hunter(
    hunter_nome: str,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    KPIs agregados pro header da sub-aba Relacionamento do Hunter.
    Hunter só vê os próprios; ADM/Gerente/Franqueado/EP vê de qualquer um.
    """
    cargo = user.get("cargo")
    pode_ver_outros = cargo in (_CARGOS_ADM_GERAL | {"EP"})
    if not pode_ver_outros and user.get("nome") != hunter_nome:
        raise HTTPException(403, "Você só pode ver os próprios KPIs.")
    return await svc.kpis_do_hunter(conn, hunter_nome)


@router.patch("/bastoes/{bastao_id}/aprovar")
async def aprovar(
    bastao_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    _exigir_aprovador(user)
    try:
        return await svc.aprovar_bastao(conn, bastao_id, user["id"])
    except svc.BastaoNaoEncontrado as e:
        raise HTTPException(404, str(e))
    except svc.TransicaoInvalida as e:
        raise HTTPException(409, str(e))


@router.patch("/bastoes/{bastao_id}/rejeitar")
async def rejeitar(
    bastao_id: UUID,
    body: BastaoRejectIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    _exigir_aprovador(user)
    try:
        return await svc.rejeitar_bastao(conn, bastao_id, user["id"], body.motivo)
    except svc.BastaoNaoEncontrado as e:
        raise HTTPException(404, str(e))
    except svc.TransicaoInvalida as e:
        raise HTTPException(409, str(e))


@router.delete("/bastoes/{bastao_id}", status_code=200)
async def remover(
    bastao_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Hunter remove o próprio bastão (soft delete). ADM/Gerente/Franqueado
    também podem remover qualquer bastão (caso edge — não é workflow normal,
    mas evita lock-in).
    """
    cargo = user.get("cargo")
    nome = _hunter_nome_do_user(user)

    try:
        if cargo in _CARGOS_ADM_GERAL:
            # Privilégio admin pode remover qualquer um — passa o nome real do dono.
            atual = await conn.fetchrow(
                "SELECT hunter_nome FROM carteira_bastao WHERE id = $1",
                bastao_id,
            )
            if not atual:
                raise HTTPException(404, f"Bastão {bastao_id} não encontrado.")
            nome = atual["hunter_nome"]

        return await svc.remover_bastao(conn, bastao_id, nome)
    except svc.BastaoNaoEncontrado as e:
        raise HTTPException(404, str(e))
    except svc.TransicaoInvalida as e:
        raise HTTPException(409, str(e))
