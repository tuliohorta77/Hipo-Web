"""
HIPO — CRM: contas (empresas-cliente).

Decisões que este módulo materializa:

  * CNPJ é a chave de negócio. Guardado só com dígitos, validado por dígito
    verificador em services/cnpj.py. Duplicata devolve 409 COM o id e a razão
    social da conta existente no payload — o front oferece "abrir a existente"
    em vez de só barrar, senão o usuário bate num erro sobre um registro que
    não consegue enxergar.

  * Não existe coluna de vendedor. O "vendedor da conta" é derivado na leitura:
    os EVs envolvidos nas oportunidades da conta com status='ativa'. Nenhuma
    ativa → lista vazia. Várias → todos, sem repetir. Suspensa não conta.
    Feito com LATERAL agregado, nunca N+1.

  * Base compartilhada: todo usuário com o módulo 'crm' vê e busca todas as
    contas. É isso que impede o CNPJ duplicado invisível. O filtro por
    envolvimento vale para oportunidades, não para contas.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import cnpj as cnpj_svc
from services.texto import limpar_nome

router = APIRouter()

# Colunas que o PATCH aceita mexer. Whitelist explícita: evita que um payload
# inesperado alcance colunas como id, criado_por ou eh_finder (esta última é
# ligada pelo sistema quando a conta é usada como finder de uma oportunidade).
CAMPOS_EDITAVEIS = {
    "razao_social", "nome_fantasia", "vertical_id", "num_funcionarios",
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
    "telefone", "telefone_2", "email", "observacoes", "eh_finder", "ativo",
}

ORDENACOES = {
    "razao_social": "c.razao_social",
    "criado_em": "c.criado_em",
    "cidade": "c.cidade",
}


# ── Schemas ──────────────────────────────────────────────────────────

class ContaBase(BaseModel):
    razao_social: str = Field(..., min_length=1, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)
    vertical_id: int | None = None
    num_funcionarios: int | None = Field(None, ge=0)
    cep: str | None = None
    logradouro: str | None = Field(None, max_length=200)
    numero: str | None = Field(None, max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    uf: str | None = None
    telefone: str | None = Field(None, max_length=20)
    telefone_2: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=150)
    observacoes: str | None = None
    eh_finder: bool = False

    @field_validator("razao_social")
    @classmethod
    def _razao_social(cls, v: str) -> str:
        # min_length=1 do Field não pega "   ": o validator roda depois e
        # devolveria None, furando o NOT NULL do banco com um erro 500 em vez
        # de um 422 honesto.
        limpo = limpar_nome(v)
        if not limpo:
            raise ValueError("Razão social não pode ser vazia.")
        return limpo

    @field_validator("nome_fantasia", "logradouro", "bairro", "cidade")
    @classmethod
    def _limpar(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return limpar_nome(v) or None

    @field_validator("cep")
    @classmethod
    def _cep(cls, v: str | None) -> str | None:
        if not v:
            return None
        digitos = "".join(ch for ch in v if ch.isdigit())
        if len(digitos) != 8:
            raise ValueError("CEP deve ter 8 dígitos.")
        return digitos

    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str | None) -> str | None:
        if not v:
            return None
        uf = v.strip().upper()
        if len(uf) != 2 or not uf.isalpha():
            raise ValueError("UF deve ter 2 letras.")
        return uf


class ContaCriar(ContaBase):
    cnpj: str

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        num = cnpj_svc.normalizar(v)
        if not cnpj_svc.valido(num):
            raise ValueError("CNPJ inválido.")
        return num


class ContaEditar(BaseModel):
    """
    Todos os campos opcionais — PATCH parcial. O CNPJ não está aqui de
    propósito: trocar o CNPJ de uma conta é trocar de empresa, não editar.
    """
    razao_social: str | None = Field(None, min_length=1, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)
    vertical_id: int | None = None
    num_funcionarios: int | None = Field(None, ge=0)
    cep: str | None = None
    logradouro: str | None = Field(None, max_length=200)
    numero: str | None = Field(None, max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    uf: str | None = None
    telefone: str | None = Field(None, max_length=20)
    telefone_2: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=150)
    observacoes: str | None = None
    eh_finder: bool | None = None
    ativo: bool | None = None

    @field_validator("razao_social")
    @classmethod
    def _razao_social(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpo = limpar_nome(v)
        if not limpo:
            raise ValueError("Razão social não pode ser vazia.")
        return limpo

    _limpar = field_validator("nome_fantasia", "logradouro", "bairro", "cidade")(
        ContaBase._limpar.__func__
    )
    _cep = field_validator("cep")(ContaBase._cep.__func__)
    _uf = field_validator("uf")(ContaBase._uf.__func__)


class ContaResumo(BaseModel):
    id: UUID
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    cnpj_formatado: str
    cidade: str | None
    uf: str | None
    vertical_id: int | None
    vertical_nome: str | None
    num_funcionarios: int | None
    eh_finder: bool
    ativo: bool
    vendedores: list[str]
    qtd_oportunidades_ativas: int
    criado_em: datetime


class ContaLista(BaseModel):
    total: int
    limit: int
    offset: int
    itens: list[ContaResumo]


class ContatoDaConta(BaseModel):
    id: UUID
    nome: str
    telefone: str | None
    email: str | None
    data_nascimento: date | None
    cargo: str | None
    principal: bool


class OportunidadeDaConta(BaseModel):
    id: UUID
    numero: str
    fase: str
    status: str
    valor_mensalidade: float | None
    temperatura: int | None
    previsao_fechamento: date | None


class ContaDetalhe(ContaResumo):
    cep: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    telefone: str | None
    telefone_2: str | None
    email: str | None
    observacoes: str | None
    atualizado_em: datetime
    contatos: list[ContatoDaConta]
    oportunidades: list[OportunidadeDaConta]


class ContaBusca(BaseModel):
    """Payload enxuto para a lupa do EntityPicker."""
    id: UUID
    razao_social: str
    nome_fantasia: str | None
    cnpj_formatado: str
    cidade: str | None
    uf: str | None
    eh_finder: bool
    ativo: bool


class EventoHistorico(BaseModel):
    """Uma linha da timeline da conta."""
    tipo: str
    quando: datetime
    usuario: str | None
    titulo: str
    detalhe: str | None


class ResumoContas(BaseModel):
    total: int
    ativas: int
    inativas: int
    finders: int
    sem_oportunidade_ativa: int
    sem_vertical: int
    por_vertical: list[dict]


# ── SQL compartilhado ────────────────────────────────────────────────
#
# O LATERAL abaixo é o "vendedor derivado". Ele roda uma vez por linha da
# página (não por conta do banco inteiro), e o índice parcial
# idx_opp_ativas (conta_id) WHERE status='ativa' cobre o filtro.

#
# O FILTER não é opcional: com LEFT JOIN, uma oportunidade ativa sem EV
# vinculado faz o array_agg produzir {NULL} em vez de {} — e o array chega no
# front como [null], quebrando a exibição.
#
# O DISTINCT é por nome, não por usuario_id: a lista existe para exibição, e
# repetir o mesmo nome numa célula não informa nada. O efeito colateral é que
# dois EVs homônimos aparecem como um só.

_LATERAL_EVS = """
    LEFT JOIN LATERAL (
        SELECT
            COALESCE(
                array_agg(DISTINCT u.nome) FILTER (WHERE u.nome IS NOT NULL),
                ARRAY[]::text[]
            )                        AS vendedores,
            count(DISTINCT o.id)     AS qtd_ativas
        FROM oportunidades o
        LEFT JOIN oportunidade_envolvidos oe
               ON oe.oportunidade_id = o.id AND oe.papel = 'EV'
        LEFT JOIN usuarios u ON u.id = oe.usuario_id
        WHERE o.conta_id = c.id AND o.status = 'ativa'
    ) ev ON TRUE
"""


def _para_resumo(row) -> dict:
    d = dict(row)
    d["cnpj_formatado"] = cnpj_svc.formatar(d["cnpj"])
    d["vendedores"] = list(d.pop("vendedores") or [])
    d["qtd_oportunidades_ativas"] = d.pop("qtd_ativas") or 0
    return d


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/resumo", response_model=ResumoContas)
async def resumo(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    KPIs do topo da tela de Contas. Cada número é clicável no front e abre o
    drawer com os registros que o compõem — por isso os filtros equivalentes
    existem em GET /crm/contas.
    """
    row = await conn.fetchrow(
        """
        SELECT
            count(*)                                        AS total,
            count(*) FILTER (WHERE ativo)                   AS ativas,
            count(*) FILTER (WHERE NOT ativo)               AS inativas,
            count(*) FILTER (WHERE eh_finder)               AS finders,
            count(*) FILTER (WHERE vertical_id IS NULL)     AS sem_vertical,
            count(*) FILTER (
                WHERE ativo AND NOT EXISTS (
                    SELECT 1 FROM oportunidades o
                    WHERE o.conta_id = c.id AND o.status = 'ativa'
                )
            ) AS sem_oportunidade_ativa
        FROM contas c
        """
    )
    por_vertical = await conn.fetch(
        """
        SELECT v.id AS vertical_id, v.nome AS vertical_nome, count(c.id) AS qtd
        FROM verticais v
        JOIN contas c ON c.vertical_id = v.id AND c.ativo
        GROUP BY v.id, v.nome
        ORDER BY qtd DESC, v.nome
        LIMIT 10
        """
    )
    return {**dict(row), "por_vertical": [dict(r) for r in por_vertical]}


@router.get("/busca", response_model=list[ContaBusca])
async def busca(
    q: str = Query(..., min_length=1, max_length=200),
    apenas_finders: bool = False,
    limit: int = Query(20, ge=1, le=50),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Alimenta a lupa do EntityPicker. Casa por razão social, nome fantasia ou
    CNPJ — este último tolerando pontuação, já que o usuário cola o CNPJ como
    veio do documento.

    Devolve contas inativas também: se alguém procura um CNPJ que existe mas
    está desativado, precisa encontrá-lo, não recadastrá-lo.
    """
    termo = f"%{q.strip()}%"
    digitos = cnpj_svc.normalizar(q)
    cnpj_like = f"%{digitos}%" if digitos else None

    rows = await conn.fetch(
        f"""
        SELECT id, razao_social, nome_fantasia, cnpj, cidade, uf, eh_finder, ativo
        FROM contas
        WHERE ($4::bool IS NOT TRUE OR eh_finder)
          AND (
                razao_social ILIKE $1
             OR nome_fantasia ILIKE $1
             OR ($2::text IS NOT NULL AND cnpj LIKE $2)
          )
        ORDER BY eh_finder DESC, ativo DESC, razao_social
        LIMIT $3
        """,
        termo, cnpj_like, limit, apenas_finders,
    )
    return [
        {**dict(r), "cnpj_formatado": cnpj_svc.formatar(r["cnpj"])}
        for r in rows
    ]


@router.get("", response_model=ContaLista)
async def listar(
    q: str | None = Query(None, max_length=200),
    vertical_id: int | None = None,
    uf: str | None = Query(None, max_length=2),
    eh_finder: bool | None = None,
    ativo: bool | None = None,
    sem_oportunidade_ativa: bool = False,
    sem_vertical: bool = False,
    ordenar_por: str = Query("razao_social"),
    desc: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Listagem paginada com os filtros que os KPIs do topo acionam por drilldown.
    """
    if ordenar_por not in ORDENACOES:
        raise HTTPException(422, f"ordenar_por inválido. Use: {sorted(ORDENACOES)}")

    where: list[str] = []
    params: list = []

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if q:
        digitos = cnpj_svc.normalizar(q)
        params.append(f"%{q.strip()}%")
        i_texto = len(params)
        params.append(f"%{digitos}%" if digitos else None)
        i_cnpj = len(params)
        where.append(
            f"(c.razao_social ILIKE ${i_texto} OR c.nome_fantasia ILIKE ${i_texto}"
            f" OR (${i_cnpj}::text IS NOT NULL AND c.cnpj LIKE ${i_cnpj}))"
        )
    if vertical_id is not None:
        add("c.vertical_id = ${n}", vertical_id)
    if uf:
        add("c.uf = ${n}", uf.upper())
    if eh_finder is not None:
        add("c.eh_finder = ${n}", eh_finder)
    if ativo is not None:
        add("c.ativo = ${n}", ativo)
    if sem_oportunidade_ativa:
        where.append(
            "NOT EXISTS (SELECT 1 FROM oportunidades o"
            " WHERE o.conta_id = c.id AND o.status = 'ativa')"
        )
    if sem_vertical:
        where.append("c.vertical_id IS NULL")

    clausula = f"WHERE {' AND '.join(where)}" if where else ""
    total = await conn.fetchval(f"SELECT count(*) FROM contas c {clausula}", *params)

    direcao = "DESC" if desc else "ASC"
    rows = await conn.fetch(
        f"""
        SELECT c.id, c.razao_social, c.nome_fantasia, c.cnpj, c.cidade, c.uf,
               c.vertical_id, v.nome AS vertical_nome, c.num_funcionarios,
               c.eh_finder, c.ativo, c.criado_em,
               ev.vendedores, ev.qtd_ativas
        FROM contas c
        LEFT JOIN verticais v ON v.id = c.vertical_id
        {_LATERAL_EVS}
        {clausula}
        ORDER BY {ORDENACOES[ordenar_por]} {direcao}, c.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "itens": [_para_resumo(r) for r in rows],
    }


@router.get("/{conta_id}", response_model=ContaDetalhe)
async def obter(conta_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Conta com contatos e oportunidades embutidos — base da tela 360."""
    row = await conn.fetchrow(
        f"""
        SELECT c.*, v.nome AS vertical_nome, ev.vendedores, ev.qtd_ativas
        FROM contas c
        LEFT JOIN verticais v ON v.id = c.vertical_id
        {_LATERAL_EVS}
        WHERE c.id = $1
        """,
        conta_id,
    )
    if not row:
        raise HTTPException(404, "Conta não encontrada.")

    contatos = await conn.fetch(
        """
        SELECT ct.id, ct.nome, ct.telefone, ct.email, ct.data_nascimento,
               cc.cargo, cc.principal
        FROM conta_contatos cc
        JOIN contatos ct ON ct.id = cc.contato_id
        WHERE cc.conta_id = $1 AND cc.ativo AND ct.ativo
        ORDER BY cc.principal DESC, ct.nome
        """,
        conta_id,
    )
    oportunidades = await conn.fetch(
        """
        SELECT id, numero, fase, status, valor_mensalidade, temperatura,
               previsao_fechamento
        FROM oportunidades
        WHERE conta_id = $1
        ORDER BY criado_em DESC
        """,
        conta_id,
    )

    detalhe = _para_resumo(row)
    detalhe.pop("criado_por", None)
    detalhe["contatos"] = [dict(c) for c in contatos]
    detalhe["oportunidades"] = [dict(o) for o in oportunidades]
    return detalhe


@router.get("/{conta_id}/historico", response_model=list[EventoHistorico])
async def historico(
    conta_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Linha do tempo da conta, montada por UNION das fontes que já registram
    autoria e data: a criação da conta, os vínculos de contato e os eventos
    de oportunidade.

    Enquanto o router de oportunidades não existe (Sprint 3), a timeline
    mostra apenas os dois primeiros — e é assim mesmo: histórico que inventa
    evento é pior que histórico curto.
    """
    if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
        raise HTTPException(404, "Conta não encontrada.")

    rows = await conn.fetch(
        """
        SELECT * FROM (
            SELECT 'conta_criada'                AS tipo,
                   c.criado_em                   AS quando,
                   u.nome                        AS usuario,
                   'Conta cadastrada'            AS titulo,
                   NULL::text                    AS detalhe
              FROM contas c
              LEFT JOIN usuarios u ON u.id = c.criado_por
             WHERE c.id = $1

            UNION ALL

            SELECT CASE WHEN cc.ativo THEN 'contato_vinculado' ELSE 'contato_desvinculado' END,
                   cc.criado_em,
                   NULL,
                   ct.nome,
                   cc.cargo
              FROM conta_contatos cc
              JOIN contatos ct ON ct.id = cc.contato_id
             WHERE cc.conta_id = $1

            UNION ALL

            SELECT 'oportunidade_' || oe.tipo,
                   oe.criado_em,
                   u.nome,
                   o.numero,
                   CASE
                       WHEN oe.de IS NOT NULL AND oe.para IS NOT NULL
                           THEN oe.de || ' -> ' || oe.para
                       ELSE oe.para
                   END
              FROM oportunidade_eventos oe
              JOIN oportunidades o ON o.id = oe.oportunidade_id
              LEFT JOIN usuarios u ON u.id = oe.usuario_id
             WHERE o.conta_id = $1
        ) t
        ORDER BY quando DESC
        LIMIT $2
        """,
        conta_id, limit,
    )
    return [dict(r) for r in rows]


@router.post("", response_model=ContaDetalhe, status_code=status.HTTP_201_CREATED)
async def criar(
    payload: ContaCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria a conta. CNPJ duplicado devolve 409 com o registro existente no
    corpo, para o front poder oferecer "abrir a conta existente".
    """
    existente = await conn.fetchrow(
        "SELECT id, razao_social, ativo FROM contas WHERE cnpj = $1", payload.cnpj
    )
    if existente:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "erro": "cnpj_duplicado",
                "mensagem": f"O CNPJ {cnpj_svc.formatar(payload.cnpj)} já está cadastrado.",
                "conta_id": str(existente["id"]),
                "razao_social": existente["razao_social"],
                "ativo": existente["ativo"],
            },
        )

    if payload.vertical_id is not None:
        if not await conn.fetchval("SELECT 1 FROM verticais WHERE id = $1", payload.vertical_id):
            raise HTTPException(422, "vertical_id não existe.")

    dados = payload.model_dump()
    colunas = list(dados.keys()) + ["criado_por"]
    valores = list(dados.values()) + [user["id"]]
    marcadores = ", ".join(f"${i}" for i in range(1, len(valores) + 1))

    novo_id = await conn.fetchval(
        f"INSERT INTO contas ({', '.join(colunas)}) VALUES ({marcadores}) RETURNING id",
        *valores,
    )
    return await obter(novo_id, conn=conn, user=user)


@router.patch("/{conta_id}", response_model=ContaDetalhe)
async def editar(
    conta_id: UUID,
    payload: ContaEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """PATCH parcial. O CNPJ não é editável — trocar CNPJ é outra empresa."""
    if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
        raise HTTPException(404, "Conta não encontrada.")

    dados = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in CAMPOS_EDITAVEIS
    }
    if not dados:
        raise HTTPException(422, "Nenhum campo para atualizar.")

    if dados.get("vertical_id") is not None:
        if not await conn.fetchval("SELECT 1 FROM verticais WHERE id = $1", dados["vertical_id"]):
            raise HTTPException(422, "vertical_id não existe.")

    sets = [f"{col} = ${i}" for i, col in enumerate(dados, start=1)]
    sets.append("atualizado_em = NOW()")
    await conn.execute(
        f"UPDATE contas SET {', '.join(sets)} WHERE id = ${len(dados) + 1}",
        *dados.values(), conta_id,
    )
    return await obter(conta_id, conn=conn, user=user)


@router.delete("/{conta_id}", response_model=ContaDetalhe)
async def desativar(
    conta_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Delete lógico (ativo = FALSE). Conta nunca é apagada de verdade: as
    oportunidades apontam para ela com ON DELETE RESTRICT, e o histórico
    comercial precisa continuar legível.
    """
    atualizado = await conn.fetchval(
        "UPDATE contas SET ativo = FALSE, atualizado_em = NOW() WHERE id = $1 RETURNING id",
        conta_id,
    )
    if not atualizado:
        raise HTTPException(404, "Conta não encontrada.")
    return await obter(conta_id, conn=conn, user=user)
