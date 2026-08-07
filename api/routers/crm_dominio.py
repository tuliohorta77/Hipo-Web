"""
HIPO — Dados de apoio dos formulários do CRM.

Listas de domínio (verticais, origens, concorrentes, motivos) e a lista de
usuários que alimenta o seletor de envolvidos das oportunidades.

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


class UsuarioOut(BaseModel):
    id: str
    nome: str
    cargo: str | None


class PreferenciaIn(BaseModel):
    valor: str = Field(..., max_length=500)


class PreferenciaOut(BaseModel):
    chave: str
    valor: str


def _validar_tabela(tabela: str) -> str:
    if tabela not in TABELAS_SIMPLES:
        raise HTTPException(404, f"Lista de domínio desconhecida: '{tabela}'.")
    return tabela


@router.get("/preferencias", response_model=list[PreferenciaOut])
async def listar_preferencias(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Preferências de UI do usuário logado (ex.: crm_oportunidades_visao).

    Ficam no banco, não no localStorage: o HIPO é a fonte primária, e a
    escolha de ver o funil em tabela ou kanban deve acompanhar a pessoa entre
    máquinas.
    """
    rows = await conn.fetch(
        "SELECT chave, valor FROM usuarios_preferencias WHERE usuario_id = $1 ORDER BY chave",
        user["id"],
    )
    return [dict(r) for r in rows]


@router.put("/preferencias/{chave}", response_model=PreferenciaOut)
async def definir_preferencia(
    chave: str,
    payload: PreferenciaIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Grava (ou sobrescreve) uma preferência do usuário logado."""
    if not chave.strip() or len(chave) > 60:
        raise HTTPException(422, "Chave de preferência inválida.")
    row = await conn.fetchrow(
        """
        INSERT INTO usuarios_preferencias (usuario_id, chave, valor)
        VALUES ($1, $2, $3)
        ON CONFLICT (usuario_id, chave)
        DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = NOW()
        RETURNING chave, valor
        """,
        user["id"], chave.strip(), payload.valor,
    )
    return dict(row)


# ATENÇÃO À ORDEM: esta rota precisa vir ANTES de /{tabela}. O FastAPI casa
# por ordem de declaração, então com /{tabela} na frente o caminho
# /crm/dominio/usuarios seria interpretado como a tabela "usuarios" — que não
# está na whitelist — e devolveria 404.
@router.get("/usuarios", response_model=list[UsuarioOut])
async def listar_usuarios(
    q: str | None = Query(None, max_length=150),
    cargo: str | None = Query(None, max_length=80),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Usuários ativos, para o seletor de envolvidos (EC/SDR/EV) das
    oportunidades.

    Vive aqui e não sob o módulo 'usuarios' de propósito: escolher quem está
    envolvido num negócio é parte de operar o CRM, não de administrar contas
    de acesso. Exigir o módulo de gestão travaria o vendedor no meio do
    formulário.

    Devolve só id, nome e cargo — nada de e-mail nem hash de senha.
    """
    rows = await conn.fetch(
        """
        SELECT id::text, nome, cargo
          FROM usuarios
         WHERE ativo
           AND ($1::text IS NULL OR nome ILIKE $1)
           AND ($2::text IS NULL OR cargo = $2)
         ORDER BY nome
         LIMIT 200
        """,
        f"%{q.strip()}%" if q else None,
        cargo,
    )
    return [dict(r) for r in rows]


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
