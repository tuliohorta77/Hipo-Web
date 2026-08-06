"""
HIPO — Listas de domínio do CRM (verticais, origens, concorrentes, motivos).

As listas nascem vazias e qualquer usuário com o módulo 'crm' cria entradas
direto do combobox. Para não virar lixo ("Metalúrgica" vs "metalurgica"), a
chave real é o slug normalizado, que é UNIQUE no banco.

O POST é IDEMPOTENTE de propósito: se o slug já existe, devolve o registro
existente com 200 em vez de 409. Do ponto de vista do combobox, "criar algo
que já existe" é o mesmo que "selecionar o que existe" — devolver erro só
obrigaria o front a tratar um caso que não é erro nenhum.

Backlog (tela ADM): renomear e fundir entradas parecidas.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from services.texto import limpar_nome, slugify

router = APIRouter()

# Tabelas expostas por este router. O nome vem da URL, então a whitelist é o
# que impede injeção de nome de tabela na f-string da query.
TABELAS_SIMPLES = {"verticais", "origens", "concorrentes"}

TIPOS_MOTIVO = {"perda", "cancelamento"}


class ItemDominioIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)


class ItemDominioOut(BaseModel):
    id: int
    nome: str
    slug: str


class MotivoOut(ItemDominioOut):
    tipo: str


def _validar_tabela(tabela: str) -> str:
    if tabela not in TABELAS_SIMPLES:
        raise HTTPException(404, f"Lista de domínio desconhecida: '{tabela}'.")
    return tabela


@router.get("/{tabela}", response_model=list[ItemDominioOut])
async def listar(
    tabela: str,
    q: str | None = Query(None, max_length=120),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Lista uma das listas simples, opcionalmente filtrando por trecho do nome."""
    _validar_tabela(tabela)
    if q:
        rows = await conn.fetch(
            f"SELECT id, nome, slug FROM {tabela} WHERE nome ILIKE $1 ORDER BY nome LIMIT 50",
            f"%{q}%",
        )
    else:
        rows = await conn.fetch(f"SELECT id, nome, slug FROM {tabela} ORDER BY nome")
    return [dict(r) for r in rows]


@router.post("/{tabela}", response_model=ItemDominioOut)
async def criar(
    tabela: str,
    payload: ItemDominioIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria a entrada, ou devolve a existente se o slug já estiver cadastrado.

    Idempotente: chamar duas vezes com "Metalúrgica" e "metalurgica " devolve
    o mesmo id nas duas.
    """
    _validar_tabela(tabela)
    nome = limpar_nome(payload.nome)
    slug = slugify(nome)
    if not slug:
        raise HTTPException(422, "Nome inválido: precisa ter ao menos uma letra ou número.")

    existente = await conn.fetchrow(
        f"SELECT id, nome, slug FROM {tabela} WHERE slug = $1", slug
    )
    if existente:
        return dict(existente)

    row = await conn.fetchrow(
        f"""
        INSERT INTO {tabela} (nome, slug, criado_por)
        VALUES ($1, $2, $3)
        ON CONFLICT (slug) DO UPDATE SET nome = {tabela}.nome
        RETURNING id, nome, slug
        """,
        nome, slug, user["id"],
    )
    return dict(row)


@router.get("/motivos/{tipo}", response_model=list[MotivoOut])
async def listar_motivos(
    tipo: str,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Motivos de desfecho, separados por tipo: 'perda' ou 'cancelamento'."""
    if tipo not in TIPOS_MOTIVO:
        raise HTTPException(404, f"Tipo de motivo desconhecido: '{tipo}'.")
    rows = await conn.fetch(
        "SELECT id, nome, slug, tipo FROM motivos_desfecho WHERE tipo = $1 ORDER BY nome",
        tipo,
    )
    return [dict(r) for r in rows]


@router.post("/motivos/{tipo}", response_model=MotivoOut)
async def criar_motivo(
    tipo: str,
    payload: ItemDominioIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Idem ao POST das listas simples, mas com o discriminador de tipo."""
    if tipo not in TIPOS_MOTIVO:
        raise HTTPException(404, f"Tipo de motivo desconhecido: '{tipo}'.")
    nome = limpar_nome(payload.nome)
    slug = slugify(nome)
    if not slug:
        raise HTTPException(422, "Nome inválido: precisa ter ao menos uma letra ou número.")

    existente = await conn.fetchrow(
        "SELECT id, nome, slug, tipo FROM motivos_desfecho WHERE tipo = $1 AND slug = $2",
        tipo, slug,
    )
    if existente:
        return dict(existente)

    row = await conn.fetchrow(
        """
        INSERT INTO motivos_desfecho (tipo, nome, slug, criado_por)
        VALUES ($1, $2, $3, $4)
        RETURNING id, nome, slug, tipo
        """,
        tipo, nome, slug, user["id"],
    )
    return dict(row)
