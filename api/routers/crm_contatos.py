"""
HIPO — CRM: contatos (pessoas nas empresas-cliente).

Decisões que este módulo materializa:

  * Contato é entidade independente, N:N com conta. A mesma pessoa pode ser
    contato de mais de uma empresa (sócio de duas, contador que atende várias)
    e o cargo pertence ao VÍNCULO, não à pessoa.

  * Duplicata NÃO bloqueia. Diferente do CNPJ, não existe documento que sirva
    de chave natural para pessoa: e-mail é compartilhado (contato@empresa),
    telefone é da recepção, nome se repete. Barrar geraria falso positivo
    constante. Em vez disso, GET /duplicatas devolve os candidatos e o usuário
    escolhe entre vincular o existente ou criar outro.

  * Um contato principal por conta, no máximo — garantido pelo índice único
    parcial uq_conta_contato_principal. Promover alguém a principal rebaixa o
    anterior na MESMA transação, senão o índice rejeita a operação.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import auditoria
from services.texto import limpar_nome, normalizar_emails

router = APIRouter()

CAMPOS_EDITAVEIS = {
    "nome", "telefone", "email", "data_nascimento", "observacoes", "ativo",
    # 045: editar é o caminho para trocar telefone — antes era preciso
    # excluir o contato e cadastrar de novo, perdendo o histórico.
    "telefone_whatsapp", "telefone_2", "telefone_2_whatsapp", "linkedin",
}


def _limpar_linkedin(v: str | None) -> str | None:
    """
    Aceita o que a pessoa cola: 'linkedin.com/in/fulano', com ou sem
    https, com ou sem www. Guarda sempre com https:// na frente, para o
    link da tela abrir direto.

    Exige 'linkedin.com' no endereço: o campo é o perfil, e um site
    qualquer colado ali viraria link quebrado que ninguém percebe.
    """
    if v is None:
        return None
    limpo = v.strip()
    if not limpo:
        return None
    if "linkedin.com" not in limpo.lower():
        raise ValueError(
            "Informe o endereço do perfil no LinkedIn (linkedin.com/in/...)."
        )
    if not limpo.lower().startswith(("http://", "https://")):
        limpo = "https://" + limpo
    return limpo


# ── Schemas ──────────────────────────────────────────────────────────

class ContatoBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=150)
    telefone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=150)
    data_nascimento: date | None = None
    observacoes: str | None = None
    telefone_whatsapp: bool = False
    telefone_2: str | None = Field(None, max_length=20)
    telefone_2_whatsapp: bool = False
    linkedin: str | None = Field(None, max_length=300)

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        limpo = limpar_nome(v)
        if not limpo:
            raise ValueError("Nome não pode ser vazio.")
        return limpo

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return normalizar_emails(v)

    @field_validator("telefone", "telefone_2")
    @classmethod
    def _telefone(cls, v: str | None) -> str | None:
        if not v:
            return None
        return limpar_nome(v) or None

    @field_validator("linkedin")
    @classmethod
    def _linkedin(cls, v: str | None) -> str | None:
        return _limpar_linkedin(v)


class ContatoCriar(ContatoBase):
    """
    conta_id opcional: quando o contato nasce de dentro do formulário de uma
    conta (o botão '+' do EntityPicker), criar e vincular precisam acontecer
    na mesma transação — senão um erro no vínculo deixa um contato órfão que
    o usuário não pediu.
    """
    conta_id: UUID | None = None
    cargo: str | None = Field(None, max_length=100)
    principal: bool = False


class ContatoEditar(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=150)
    telefone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=150)
    data_nascimento: date | None = None
    observacoes: str | None = None
    ativo: bool | None = None
    telefone_whatsapp: bool | None = None
    telefone_2: str | None = Field(None, max_length=20)
    telefone_2_whatsapp: bool | None = None
    linkedin: str | None = Field(None, max_length=300)

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpo = limpar_nome(v)
        if not limpo:
            raise ValueError("Nome não pode ser vazio.")
        return limpo

    _email = field_validator("email")(ContatoBase._email.__func__)
    _telefone = field_validator("telefone", "telefone_2")(ContatoBase._telefone.__func__)
    _linkedin = field_validator("linkedin")(ContatoBase._linkedin.__func__)

    @field_validator("telefone_whatsapp", "telefone_2_whatsapp")
    @classmethod
    def _flag(cls, v: bool | None) -> bool:
        # A coluna é NOT NULL: null vindo do formulário é "não é WhatsApp".
        return bool(v)


class VinculoCriar(BaseModel):
    conta_id: UUID
    cargo: str | None = Field(None, max_length=100)
    principal: bool = False


class VinculoEditar(BaseModel):
    cargo: str | None = Field(None, max_length=100)
    principal: bool | None = None


class ContaVinculada(BaseModel):
    conta_id: UUID
    razao_social: str
    cnpj: str
    cargo: str | None
    principal: bool
    ativo: bool


class ContatoResumo(BaseModel):
    id: UUID
    nome: str
    telefone: str | None
    email: str | None
    data_nascimento: date | None
    ativo: bool
    qtd_contas: int
    criado_em: datetime
    telefone_whatsapp: bool = False
    telefone_2: str | None = None
    telefone_2_whatsapp: bool = False
    linkedin: str | None = None


class ContatoDetalhe(ContatoResumo):
    observacoes: str | None
    atualizado_em: datetime
    contas: list[ContaVinculada]


class ContatoLista(BaseModel):
    total: int
    limit: int
    offset: int
    itens: list[ContatoResumo]


class ContatoBusca(BaseModel):
    """Payload enxuto para a lupa do EntityPicker."""
    id: UUID
    nome: str
    telefone: str | None
    email: str | None
    ativo: bool
    ja_vinculado: bool


class ContatoDoAlvo(BaseModel):
    """
    Uma pessoa que pode ser o contato de uma tarefa daquele alvo.

    `no_comite`, `papel` e `principal` só fazem sentido para oportunidade:
    é o que deixa o seletor da tarefa mostrar primeiro quem já está na
    negociação e, depois, o resto da empresa.
    """
    id: UUID
    nome: str
    cargo: str | None
    telefone: str | None
    telefone_whatsapp: bool
    telefone_2: str | None
    telefone_2_whatsapp: bool
    email: str | None
    no_comite: bool
    papel: str | None
    principal: bool


class Duplicata(BaseModel):
    id: UUID
    nome: str
    telefone: str | None
    email: str | None
    motivo: str
    contas: list[str]


# ── SQL compartilhado ────────────────────────────────────────────────

_QTD_CONTAS = """
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd_contas
        FROM conta_contatos cc
        WHERE cc.contato_id = ct.id AND cc.ativo
    ) v ON TRUE
"""


async def _detalhe(conn, contato_id: UUID) -> dict:
    row = await conn.fetchrow(
        f"""
        SELECT ct.*, v.qtd_contas
        FROM contatos ct
        {_QTD_CONTAS}
        WHERE ct.id = $1
        """,
        contato_id,
    )
    if not row:
        raise HTTPException(404, "Contato não encontrado.")

    contas = await conn.fetch(
        """
        SELECT c.id AS conta_id, c.razao_social, c.cnpj, cc.cargo, cc.principal, cc.ativo
        FROM conta_contatos cc
        JOIN contas c ON c.id = cc.conta_id
        WHERE cc.contato_id = $1
        ORDER BY cc.principal DESC, c.razao_social
        """,
        contato_id,
    )
    d = dict(row)
    d.pop("criado_por", None)
    d["contas"] = [dict(c) for c in contas]
    return d


async def _promover_principal(conn, conta_id: UUID, contato_id: UUID) -> None:
    """
    Rebaixa o principal atual da conta antes de promover o novo.

    Sem isso o índice uq_conta_contato_principal rejeita o UPDATE, e o
    usuário recebe um erro de constraint em vez de a troca simplesmente
    acontecer — que é o que ele espera ao clicar em "tornar principal".
    """
    await conn.execute(
        """
        UPDATE conta_contatos SET principal = FALSE
        WHERE conta_id = $1 AND principal AND contato_id <> $2
        """,
        conta_id, contato_id,
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/duplicatas", response_model=list[Duplicata])
async def duplicatas(
    request: Request,
    email: str | None = Query(None, max_length=150),
    telefone: str | None = Query(None, max_length=20),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Candidatos a duplicata por e-mail ou telefone.

    O front chama isto ao sair do campo, antes de submeter. O resultado é uma
    SUGESTÃO — quem decide é o usuário, porque e-mail e telefone corporativos
    são legitimamente compartilhados entre pessoas da mesma empresa.
    """
    if not email and not telefone:
        return []

    rows = await conn.fetch(
        """
        SELECT ct.id, ct.nome, ct.telefone, ct.email,
               CASE
                   WHEN $1::text IS NOT NULL
                        AND regexp_split_to_array(lower(ct.email), '[;,[:space:]]+')
                         && regexp_split_to_array($1, '[;,[:space:]]+') THEN 'email'
                   ELSE 'telefone'
               END AS motivo,
               COALESCE(
                   array_agg(c.razao_social) FILTER (WHERE c.razao_social IS NOT NULL),
                   ARRAY[]::text[]
               ) AS contas
        FROM contatos ct
        LEFT JOIN conta_contatos cc ON cc.contato_id = ct.id AND cc.ativo
        LEFT JOIN contas c ON c.id = cc.conta_id
        WHERE ct.ativo
          AND (
                ($1::text IS NOT NULL
                        AND regexp_split_to_array(lower(ct.email), '[;,[:space:]]+')
                         && regexp_split_to_array($1, '[;,[:space:]]+'))
             OR ($2::text IS NOT NULL AND (ct.telefone = $2 OR ct.telefone_2 = $2))
          )
        GROUP BY ct.id, ct.nome, ct.telefone, ct.email
        ORDER BY ct.nome
        LIMIT 10
        """,
        email.strip().lower() if email else None,
        telefone.strip() if telefone else None,
    )
    # Contexto sem o e-mail/telefone digitado: ele E o dado pessoal. Basta
    # saber que a checagem rodou e por qual campo.
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO, [r["id"] for r in rows],
        {"por_email": bool(email), "por_telefone": bool(telefone)},
    )
    return [dict(r) for r in rows]


@router.get("/busca", response_model=list[ContatoBusca])
async def busca(
    request: Request,
    q: str = Query(..., min_length=1, max_length=150),
    conta_id: UUID | None = None,
    excluir_vinculados: bool = False,
    limit: int = Query(20, ge=1, le=50),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Alimenta a lupa do EntityPicker de contatos.

    `conta_id` não filtra: marca quais já estão vinculados àquela conta, para
    o picker mostrar "já vinculado" em vez de deixar o usuário selecionar
    alguém que já está lá. Use `excluir_vinculados=true` para escondê-los.
    """
    rows = await conn.fetch(
        """
        SELECT ct.id, ct.nome, ct.telefone, ct.email, ct.ativo,
               ($2::uuid IS NOT NULL AND EXISTS (
                    SELECT 1 FROM conta_contatos cc
                    WHERE cc.contato_id = ct.id AND cc.conta_id = $2 AND cc.ativo
               )) AS ja_vinculado
        FROM contatos ct
        WHERE (ct.nome ILIKE $1 OR ct.email ILIKE $1 OR ct.telefone ILIKE $1)
          AND ($4::bool IS NOT TRUE OR NOT EXISTS (
                    SELECT 1 FROM conta_contatos cc
                    WHERE cc.contato_id = ct.id AND cc.conta_id = $2 AND cc.ativo
              ))
        ORDER BY ct.ativo DESC, ct.nome
        LIMIT $3
        """,
        f"%{q.strip()}%", conta_id, limit, excluir_vinculados,
    )
    # O termo buscado entra: "quem procurou por Fulana" e pergunta legitima
    # da trilha, e a tabela tem o mesmo acesso restrito que ela.
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO, [r["id"] for r in rows],
        {"q": q.strip()[:150], "conta_id": conta_id},
    )
    return [dict(r) for r in rows]


@router.get("/por-alvo", response_model=list[ContatoDoAlvo])
async def por_alvo(
    request: Request,
    oportunidade_id: UUID | None = None,
    conta_id: UUID | None = None,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Quem pode ser o contato de uma tarefa deste alvo (045).

    Oportunidade: as pessoas ATIVAS vinculadas à conta principal ou a um
    CNPJ adicional, mais as que já estão no comitê. Ordem: o principal, o
    resto do comitê, e depois o resto da empresa — é a ordem em que o
    vendedor procura.

    Parceiro (conta): as pessoas ativas vinculadas àquela conta.
    """
    if (oportunidade_id is None) == (conta_id is None):
        raise HTTPException(422, "Informe a oportunidade OU a conta.")

    if oportunidade_id is not None:
        if not await conn.fetchval(
            "SELECT 1 FROM oportunidades WHERE id = $1", oportunidade_id
        ):
            raise HTTPException(404, "Oportunidade não encontrada.")
        rows = await conn.fetch(
            """
            WITH contas_opp AS (
                SELECT o.conta_id FROM oportunidades o WHERE o.id = $1
                UNION
                SELECT oc.conta_id FROM oportunidade_contas oc
                 WHERE oc.oportunidade_id = $1 AND oc.removido_em IS NULL
            ),
            pessoas AS (
                SELECT cc.contato_id FROM conta_contatos cc
                 WHERE cc.conta_id IN (SELECT conta_id FROM contas_opp) AND cc.ativo
                UNION
                SELECT x.contato_id FROM oportunidade_contatos x
                 WHERE x.oportunidade_id = $1
            )
            SELECT ct.id, ct.nome, ct.telefone, ct.telefone_whatsapp,
                   ct.telefone_2, ct.telefone_2_whatsapp, ct.email,
                   (SELECT cc.cargo FROM conta_contatos cc
                     WHERE cc.contato_id = ct.id AND cc.cargo IS NOT NULL
                       AND cc.conta_id IN (SELECT conta_id FROM contas_opp)
                     ORDER BY cc.ativo DESC LIMIT 1) AS cargo,
                   (oc.contato_id IS NOT NULL)        AS no_comite,
                   oc.papel,
                   COALESCE(oc.principal, FALSE)      AS principal
              FROM pessoas p
              JOIN contatos ct ON ct.id = p.contato_id AND ct.ativo
              LEFT JOIN oportunidade_contatos oc
                     ON oc.oportunidade_id = $1 AND oc.contato_id = ct.id
             ORDER BY COALESCE(oc.principal, FALSE) DESC,
                      (oc.contato_id IS NOT NULL) DESC,
                      ct.nome
            """,
            oportunidade_id,
        )
        await auditoria.registrar_leitura(
            conn, request, user, auditoria.RECURSO_CONTATO, [r["id"] for r in rows],
            {"oportunidade_id": oportunidade_id},
        )
        return [dict(r) for r in rows]

    if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
        raise HTTPException(404, "Conta não encontrada.")
    rows = await conn.fetch(
        """
        SELECT ct.id, ct.nome, ct.telefone, ct.telefone_whatsapp,
               ct.telefone_2, ct.telefone_2_whatsapp, ct.email, cc.cargo,
               FALSE AS no_comite, NULL::varchar AS papel,
               cc.principal
          FROM conta_contatos cc
          JOIN contatos ct ON ct.id = cc.contato_id AND ct.ativo
         WHERE cc.conta_id = $1 AND cc.ativo
         ORDER BY cc.principal DESC, ct.nome
        """,
        conta_id,
    )
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO, [r["id"] for r in rows],
        {"conta_id": conta_id},
    )
    return [dict(r) for r in rows]


@router.get("", response_model=ContatoLista)
async def listar(
    request: Request,
    q: str | None = Query(None, max_length=150),
    conta_id: UUID | None = None,
    ativo: bool | None = None,
    sem_conta: bool = False,
    aniversariantes_mes: int | None = Query(None, ge=1, le=12),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Listagem paginada. `sem_conta` acha contatos que ficaram órfãos."""
    where: list[str] = []
    params: list = []

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if q:
        add("(ct.nome ILIKE ${n} OR ct.email ILIKE ${n} OR ct.telefone ILIKE ${n})",
            f"%{q.strip()}%")
    if conta_id is not None:
        add(
            "EXISTS (SELECT 1 FROM conta_contatos cc"
            " WHERE cc.contato_id = ct.id AND cc.conta_id = ${n} AND cc.ativo)",
            conta_id,
        )
    if ativo is not None:
        add("ct.ativo = ${n}", ativo)
    if aniversariantes_mes is not None:
        add("EXTRACT(MONTH FROM ct.data_nascimento) = ${n}", aniversariantes_mes)
    if sem_conta:
        where.append(
            "NOT EXISTS (SELECT 1 FROM conta_contatos cc"
            " WHERE cc.contato_id = ct.id AND cc.ativo)"
        )

    clausula = f"WHERE {' AND '.join(where)}" if where else ""
    total = await conn.fetchval(f"SELECT count(*) FROM contatos ct {clausula}", *params)
    rows = await conn.fetch(
        f"""
        SELECT ct.id, ct.nome, ct.telefone, ct.email, ct.data_nascimento,
               ct.ativo, ct.criado_em, v.qtd_contas,
               ct.telefone_whatsapp, ct.telefone_2, ct.telefone_2_whatsapp,
               ct.linkedin
        FROM contatos ct
        {_QTD_CONTAS}
        {clausula}
        ORDER BY ct.nome, ct.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO, [r["id"] for r in rows],
        {
            "q": q.strip()[:150] if q else None,
            "conta_id": conta_id,
            "aniversariantes_mes": aniversariantes_mes,
            "sem_conta": sem_conta or None,
            "offset": offset or None,
        },
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "itens": [dict(r) for r in rows],
    }


@router.get("/{contato_id}", response_model=ContatoDetalhe)
async def obter(
    contato_id: UUID,
    request: Request,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    detalhe = await _detalhe(conn, contato_id)
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO, [contato_id],
    )
    return detalhe


@router.post("", response_model=ContatoDetalhe, status_code=status.HTTP_201_CREATED)
async def criar(
    payload: ContatoCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria o contato e, se `conta_id` vier, já vincula — tudo em uma transação.

    Não checa duplicata: quem decide é o usuário, via GET /duplicatas.
    """
    if payload.conta_id is not None:
        existe = await conn.fetchval(
            "SELECT 1 FROM contas WHERE id = $1", payload.conta_id
        )
        if not existe:
            raise HTTPException(422, "conta_id não existe.")

    async with conn.transaction():
        novo_id = await conn.fetchval(
            """
            INSERT INTO contatos (
                nome, telefone, email, data_nascimento, observacoes, criado_por,
                telefone_whatsapp, telefone_2, telefone_2_whatsapp, linkedin
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            payload.nome, payload.telefone, payload.email,
            payload.data_nascimento, payload.observacoes, user["id"],
            payload.telefone_whatsapp, payload.telefone_2,
            payload.telefone_2_whatsapp, payload.linkedin,
        )
        if payload.conta_id is not None:
            if payload.principal:
                await _promover_principal(conn, payload.conta_id, novo_id)
            await conn.execute(
                """
                INSERT INTO conta_contatos (conta_id, contato_id, cargo, principal)
                VALUES ($1, $2, $3, $4)
                """,
                payload.conta_id, novo_id, payload.cargo, payload.principal,
            )
    return await _detalhe(conn, novo_id)


@router.patch("/{contato_id}", response_model=ContatoDetalhe)
async def editar(
    contato_id: UUID,
    payload: ContatoEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if not await conn.fetchval("SELECT 1 FROM contatos WHERE id = $1", contato_id):
        raise HTTPException(404, "Contato não encontrado.")

    dados = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in CAMPOS_EDITAVEIS
    }
    if not dados:
        raise HTTPException(422, "Nenhum campo para atualizar.")

    sets = [f"{col} = ${i}" for i, col in enumerate(dados, start=1)]
    sets.append("atualizado_em = NOW()")
    await conn.execute(
        f"UPDATE contatos SET {', '.join(sets)} WHERE id = ${len(dados) + 1}",
        *dados.values(), contato_id,
    )
    return await _detalhe(conn, contato_id)


@router.delete("/{contato_id}", response_model=ContatoDetalhe)
async def desativar(
    contato_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Delete lógico. Os vínculos com contas são preservados: o histórico de quem
    era o contato de uma empresa continua legível mesmo depois de a pessoa sair.
    """
    atualizado = await conn.fetchval(
        "UPDATE contatos SET ativo = FALSE, atualizado_em = NOW() WHERE id = $1 RETURNING id",
        contato_id,
    )
    if not atualizado:
        raise HTTPException(404, "Contato não encontrado.")
    return await _detalhe(conn, contato_id)


# ── Vínculos com contas ──────────────────────────────────────────────

@router.post("/{contato_id}/vinculos", response_model=ContatoDetalhe,
             status_code=status.HTTP_201_CREATED)
async def vincular(
    contato_id: UUID,
    payload: VinculoCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Vincula um contato existente a uma conta.

    Se o vínculo já existir mas estiver inativo, reativa em vez de recusar —
    religar alguém que voltou para a empresa não é um conflito.
    """
    if not await conn.fetchval("SELECT 1 FROM contatos WHERE id = $1", contato_id):
        raise HTTPException(404, "Contato não encontrado.")
    if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", payload.conta_id):
        raise HTTPException(422, "conta_id não existe.")

    async with conn.transaction():
        existente = await conn.fetchrow(
            "SELECT ativo FROM conta_contatos WHERE conta_id = $1 AND contato_id = $2",
            payload.conta_id, contato_id,
        )
        if existente and existente["ativo"]:
            raise HTTPException(409, "Este contato já está vinculado a esta conta.")

        if payload.principal:
            await _promover_principal(conn, payload.conta_id, contato_id)

        if existente:
            await conn.execute(
                """
                UPDATE conta_contatos
                   SET ativo = TRUE, cargo = $3, principal = $4
                 WHERE conta_id = $1 AND contato_id = $2
                """,
                payload.conta_id, contato_id, payload.cargo, payload.principal,
            )
        else:
            await conn.execute(
                """
                INSERT INTO conta_contatos (conta_id, contato_id, cargo, principal)
                VALUES ($1, $2, $3, $4)
                """,
                payload.conta_id, contato_id, payload.cargo, payload.principal,
            )
    return await _detalhe(conn, contato_id)


@router.patch("/{contato_id}/vinculos/{conta_id}", response_model=ContatoDetalhe)
async def editar_vinculo(
    contato_id: UUID,
    conta_id: UUID,
    payload: VinculoEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Ajusta cargo e/ou promove o contato a principal daquela conta."""
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(422, "Nenhum campo para atualizar.")

    async with conn.transaction():
        existente = await conn.fetchval(
            "SELECT 1 FROM conta_contatos WHERE conta_id = $1 AND contato_id = $2",
            conta_id, contato_id,
        )
        if not existente:
            raise HTTPException(404, "Vínculo não encontrado.")

        if dados.get("principal"):
            await _promover_principal(conn, conta_id, contato_id)

        sets = [f"{col} = ${i}" for i, col in enumerate(dados, start=1)]
        await conn.execute(
            f"""
            UPDATE conta_contatos SET {', '.join(sets)}
             WHERE conta_id = ${len(dados) + 1} AND contato_id = ${len(dados) + 2}
            """,
            *dados.values(), conta_id, contato_id,
        )
    return await _detalhe(conn, contato_id)


@router.delete("/{contato_id}/vinculos/{conta_id}", response_model=ContatoDetalhe)
async def desvincular(
    contato_id: UUID,
    conta_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Desfaz o vínculo (ativo = FALSE), preservando a linha.

    Também limpa a flag de principal: uma conta não pode ficar com um
    principal desvinculado, senão o próximo a ser promovido bate no índice.
    """
    removido = await conn.fetchval(
        """
        UPDATE conta_contatos SET ativo = FALSE, principal = FALSE
         WHERE conta_id = $1 AND contato_id = $2 AND ativo
        RETURNING contato_id
        """,
        conta_id, contato_id,
    )
    if not removido:
        raise HTTPException(404, "Vínculo não encontrado ou já desfeito.")
    return await _detalhe(conn, contato_id)
