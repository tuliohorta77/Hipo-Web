"""
HIPO — CRM: tarefas do funil e da carteira de parceiros.

O que este módulo materializa:

  * Toda tarefa pertence a UM alvo: uma oportunidade ou um parceiro. Não
    existe tarefa solta — é o que mantém o dado servindo para métrica em vez
    de virar lista de afazeres pessoal. E não existe tarefa com dois alvos:
    a primeira métrica que somasse os dois contaria a mesma tarefa duas
    vezes.

  * A tarefa de parceiro NÃO exige a próxima ao concluir. A regra da
    oportunidade se apoia num estado final; parceria não tem um. Ver
    services/tarefa.py: quem cobra cadência do parceiro é o farol semanal.

  * A situação (atrasada / hoje / futura / concluída / cancelada) é DERIVADA
    e calculada no servidor, não no navegador. Duas razões: o relógio do
    cliente pode estar errado, e assim o filtro por situação e a ordenação
    usam exatamente a mesma regra que a tela exibe.

  * Concluir e criar a próxima acontecem na MESMA transação. Se o INSERT da
    próxima falhar, a conclusão não vale — senão a oportunidade ficaria sem
    próximo passo, que é o buraco que a regra existe para tapar.

  * Regras em services/tarefa.py, como funções puras. Aqui só orquestração.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field, field_validator, model_validator

from database import get_conn
from routers.auth import usuario_atual
from services import tarefa as regras
from services.tarefa import EstadoTarefa, TarefaInvalida

router = APIRouter()

CAMPOS_EDITAVEIS = {"tipo", "titulo", "descricao", "responsavel_id", "prazo"}


# ── Schemas ──────────────────────────────────────────────────────────

class TarefaBase(BaseModel):
    tipo: str
    titulo: str = Field(..., max_length=200)
    descricao: str | None = None
    responsavel_id: UUID
    prazo: datetime

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str) -> str:
        if v not in regras.TIPOS:
            raise ValueError(
                f"Tipo inválido. Use: {', '.join(regras.TIPOS)}."
            )
        return v

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str) -> str:
        # Field(max_length) roda ANTES do validator, mas min_length não pega
        # string só de espaço — mesmo tropeço que custou um 500 na Sprint 1.
        limpo = (v or "").strip()
        if not limpo:
            raise ValueError("O título da tarefa não pode ficar em branco.")
        return limpo


class TarefaCriar(TarefaBase):
    """
    Exatamente um alvo. A validação é aqui e não só no CHECK do banco porque
    o CHECK devolveria 500; o usuário precisa de 422 com frase em português.
    """
    oportunidade_id: UUID | None = None
    conta_id: UUID | None = None

    @model_validator(mode="after")
    def _alvo(self):
        try:
            regras.validar_alvo(self.oportunidade_id, self.conta_id)
        except TarefaInvalida as e:
            raise ValueError(str(e)) from e
        return self


class TarefaEditar(BaseModel):
    tipo: str | None = None
    titulo: str | None = Field(None, max_length=200)
    descricao: str | None = None
    responsavel_id: UUID | None = None
    prazo: datetime | None = None

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str | None) -> str | None:
        if v is not None and v not in regras.TIPOS:
            raise ValueError(f"Tipo inválido. Use: {', '.join(regras.TIPOS)}.")
        return v

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpo = v.strip()
        if not limpo:
            raise ValueError("O título da tarefa não pode ficar em branco.")
        return limpo


class ProximaTarefa(TarefaBase):
    """
    A próxima tarefa HERDA o alvo da que está sendo concluída — oportunidade
    ou parceiro. Não aceita alvo próprio de propósito: a corrente de
    follow-up que pulasse de alvo faria `tarefa_anterior_id` apontar para
    fora do histórico que a aba mostra.
    """


class Conclusao(BaseModel):
    resultado: str | None = None
    proxima: ProximaTarefa | None = None


class Cancelamento(BaseModel):
    motivo: str | None = None


class TarefaOut(BaseModel):
    id: UUID
    # 'oportunidade' ou 'parceiro'. Vem pronto do servidor para a tela não
    # inferir de campo nulo — inferência de nulo é a primeira coisa que
    # quebra quando alguém acrescenta um terceiro alvo.
    alvo: str
    alvo_rotulo: str
    oportunidade_id: UUID | None
    oportunidade_numero: str | None
    # O status da oportunidade vem junto porque a tela de gestão precisa
    # saber, ANTES de abrir o formulário, se aquela conclusão vai exigir a
    # próxima tarefa. Buscar por tarefa seria N+1; o JOIN já existe.
    # None em tarefa de parceiro — e é esse None que faz `exige_proxima`
    # devolver False.
    status_oportunidade: str | None
    conta_id: UUID
    # A empresa: a conta da oportunidade, ou o próprio parceiro.
    conta_razao_social: str
    tipo: str
    tipo_rotulo: str
    titulo: str
    descricao: str | None
    responsavel_id: UUID
    responsavel_nome: str | None
    prazo: datetime
    situacao: str
    concluida_em: datetime | None
    resultado: str | None
    cancelada_em: datetime | None
    motivo_cancelamento: str | None
    tarefa_anterior_id: UUID | None
    criado_em: datetime


class TarefaLista(BaseModel):
    total: int
    abertas: int
    atrasadas: int
    itens: list[TarefaOut]


class ColunaTarefas(BaseModel):
    situacao: str
    rotulo: str
    quantidade: int
    itens: list[TarefaOut]
    # Concluídas é retrato, não fila de trabalho: a coluna existe para o
    # gestor ver o que andou, e nela não há nada a fazer.
    somente_leitura: bool = False


# ── SQL compartilhado ────────────────────────────────────────────────

_SELECT_BASE = """
    SELECT t.id, t.oportunidade_id, o.numero AS oportunidade_numero,
           o.status AS status_oportunidade,
           COALESCE(t.conta_id, o.conta_id)                  AS conta_id,
           COALESCE(cp.razao_social, co.razao_social)        AS conta_razao_social,
           t.tipo, t.titulo, t.descricao,
           t.responsavel_id, u.nome AS responsavel_nome,
           t.prazo, t.concluida_em, t.resultado,
           t.cancelada_em, t.motivo_cancelamento,
           t.tarefa_anterior_id, t.criado_em
      FROM tarefas t
      LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
      LEFT JOIN contas co       ON co.id = o.conta_id
      LEFT JOIN contas cp       ON cp.id = t.conta_id
      LEFT JOIN usuarios u      ON u.id = t.responsavel_id
"""

# Os JOINs viraram LEFT na 006. Com INNER, toda tarefa de parceiro sumiria
# das listas em silêncio — o pior modo de falha possível para uma tela cuja
# única promessa é "não deixar nada cair".
#
# `conta_id` e `conta_razao_social` são COALESCE de propósito: quem lê a
# lista quer a EMPRESA da tarefa, e ela é a conta da oportunidade num caso e
# o próprio parceiro no outro. Duas colunas separadas empurrariam esse
# `if` para dentro de cada tela.


def _linha(row, agora: datetime) -> dict:
    d = dict(row)
    d["situacao"] = regras.situacao(
        EstadoTarefa(
            prazo=d["prazo"],
            concluida_em=d["concluida_em"],
            cancelada_em=d["cancelada_em"],
        ),
        agora,
    )
    d["tipo_rotulo"] = regras.ROTULOS_TIPO.get(d["tipo"], d["tipo"])
    d["alvo"] = "oportunidade" if d["oportunidade_id"] is not None else "parceiro"
    d["alvo_rotulo"] = regras.ROTULOS_ALVO[d["alvo"]]
    return d


async def _obter(conn, tarefa_id: UUID) -> dict:
    row = await conn.fetchrow(
        f"{_SELECT_BASE} WHERE t.id = $1", tarefa_id
    )
    if row is None:
        raise HTTPException(404, "Tarefa não encontrada.")
    return _linha(row, _agora())


async def _estado_e_alvo(
    conn, tarefa_id: UUID
) -> tuple[EstadoTarefa, str | None, UUID | None, UUID | None]:
    """
    Estado da tarefa mais o alvo dela.

    `status_oportunidade` vem None quando a tarefa é de parceiro, e é esse
    None que faz `exige_proxima` devolver False — a regra fica num lugar só.
    """
    row = await conn.fetchrow(
        """
        SELECT t.prazo, t.concluida_em, t.cancelada_em,
               t.oportunidade_id, t.conta_id, o.status AS status_oportunidade
          FROM tarefas t
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
         WHERE t.id = $1
        """,
        tarefa_id,
    )
    if row is None:
        raise HTTPException(404, "Tarefa não encontrada.")
    estado = EstadoTarefa(
        prazo=row["prazo"],
        concluida_em=row["concluida_em"],
        cancelada_em=row["cancelada_em"],
    )
    return (
        estado,
        row["status_oportunidade"],
        row["oportunidade_id"],
        row["conta_id"],
    )


async def _validar_referencias(
    conn,
    oportunidade_id: UUID | None,
    conta_id: UUID | None,
    responsavel_id: UUID,
) -> None:
    if oportunidade_id is not None and not await conn.fetchval(
        "SELECT 1 FROM oportunidades WHERE id = $1", oportunidade_id
    ):
        raise HTTPException(422, "Oportunidade não encontrada.")
    if conta_id is not None:
        # Exige `eh_finder`: tarefa presa a conta existe para cultivar a
        # PARCERIA. Aceitar qualquer conta abriria a porta para o follow-up
        # de cliente sem oportunidade — que é a lista de afazeres pessoal
        # que o módulo recusa, só que com outro nome.
        eh_parceiro = await conn.fetchval(
            "SELECT eh_finder FROM contas WHERE id = $1", conta_id
        )
        if eh_parceiro is None:
            raise HTTPException(422, "Conta não encontrada.")
        if not eh_parceiro:
            raise HTTPException(
                422,
                "Só conta marcada como parceira aceita tarefa. "
                "Marque como parceiro primeiro.",
            )
    if not await conn.fetchval(
        "SELECT 1 FROM usuarios WHERE id = $1 AND ativo", responsavel_id
    ):
        raise HTTPException(422, "Responsável não encontrado ou inativo.")


async def _inserir(conn, dados, oportunidade_id: UUID | None,
                   conta_id: UUID | None, criado_por,
                   anterior_id: UUID | None) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO tarefas (
            oportunidade_id, conta_id, tipo, titulo, descricao,
            responsavel_id, prazo, tarefa_anterior_id, criado_por
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        oportunidade_id, conta_id, dados.tipo, dados.titulo,
        (dados.descricao or "").strip() or None,
        dados.responsavel_id, dados.prazo, anterior_id, criado_por,
    )


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ── Leitura ──────────────────────────────────────────────────────────

@router.get("", response_model=TarefaLista)
async def listar(
    oportunidade_id: UUID | None = None,
    conta_id: UUID | None = None,
    responsavel_id: UUID | None = None,
    situacao: list[str] | None = Query(None),
    ordenar: str = Query("urgencia"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Tarefas de uma oportunidade ou de um parceiro — passadas, em aberto e
    futuras, na mesma lista.

    `conta_id` recorta as tarefas de um PARCEIRO (t.conta_id), não as da
    conta por trás de uma oportunidade. São duas perguntas diferentes: a
    primeira é "o que fizemos por esse parceiro", a segunda seria "o que
    fizemos nos negócios dessa empresa" — e essa segunda já é respondida
    pela visão 360 da conta.

    O filtro por situação acontece em Python e não em SQL de propósito: a
    regra de 'hoje' é dia de calendário e vive em services/tarefa.py. Duplicar
    essa lógica em SQL criaria duas fontes de verdade que divergem no primeiro
    ajuste. O recorte por oportunidade já limita o conjunto a dezenas de
    linhas, então não há custo real.

    Duas ordens, porque são duas perguntas diferentes:

      * 'urgencia'    — atrasada, hoje, futura, concluída, cancelada. É a
                        ordem de quem vai TRABALHAR a lista. Será a da agenda
                        por pessoa.
      * 'cronologico' — prazo decrescente, futuro no topo. É a ordem de quem
                        vai LER a história da negociação, e é a que a linha do
                        tempo da aba usa.

    A ordem vem do servidor nas duas para não existir uma segunda regra de
    ordenação no navegador.
    """
    if ordenar not in ("urgencia", "cronologico"):
        raise HTTPException(
            422, "ordenar inválido. Use: urgencia, cronologico."
        )
    for s in situacao or []:
        if s not in regras.SITUACOES:
            raise HTTPException(
                422, f"Situação inválida: '{s}'. Use: {', '.join(regras.SITUACOES)}."
            )

    where, params = [], []
    if oportunidade_id is not None:
        params.append(oportunidade_id)
        where.append(f"t.oportunidade_id = ${len(params)}")
    if conta_id is not None:
        params.append(conta_id)
        where.append(f"t.conta_id = ${len(params)}")
    if responsavel_id is not None:
        params.append(responsavel_id)
        where.append(f"t.responsavel_id = ${len(params)}")
    clausula = f"WHERE {' AND '.join(where)}" if where else ""

    rows = await conn.fetch(
        f"{_SELECT_BASE} {clausula} ORDER BY t.prazo LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *params, limit, offset,
    )

    agora = _agora()
    itens = [_linha(r, agora) for r in rows]

    total = len(itens)
    abertas = sum(1 for i in itens if i["situacao"] in regras.SITUACOES_ABERTAS)
    atrasadas = sum(1 for i in itens if i["situacao"] == "atrasada")

    if situacao:
        itens = [i for i in itens if i["situacao"] in situacao]

    if ordenar == "cronologico":
        itens.sort(key=lambda i: i["prazo"], reverse=True)
    else:
        itens.sort(key=lambda i: regras.chave_ordenacao(i["situacao"], i["prazo"]))

    return {
        "total": total,
        "abertas": abertas,
        "atrasadas": atrasadas,
        "itens": itens,
    }


COLUNAS_KANBAN = [
    ("atrasada", "Atrasadas"),
    ("hoje", "Para hoje"),
    ("futura", "Futuras"),
    ("concluida", "Concluídas"),
]


@router.get("/kanban", response_model=list[ColunaTarefas])
async def kanban(
    responsavel_id: UUID | None = None,
    q: str | None = Query(None, max_length=200),
    por_coluna: int = Query(100, ge=1, le=300),
    dias_concluidas: int = Query(7, ge=1, le=90),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    As tarefas de TODAS as oportunidades em quatro colunas, para gestão.

    Três decisões que este endpoint materializa:

      * A coluna Concluídas é uma JANELA (7 dias por padrão), não o histórico
        inteiro. Aberto é estoque e cresce devagar; concluído é fluxo e cresce
        para sempre. Sem recorte a coluna vira arquivo morto que ninguém lê e
        que custa uma varredura da tabela a cada carga.

      * Canceladas não têm coluna. São ruído para quem está gerindo carga de
        trabalho — continuam visíveis na linha do tempo da oportunidade, que
        é onde o histórico completo mora.

      * A situação sai de services/tarefa.py, no fuso da operação. Fazer o
        recorte em SQL exigiria repetir a regra de 'hoje' lá, e duas fontes
        de verdade divergem no primeiro ajuste.

    Este endpoint precisa vir declarado ANTES de /{tarefa_id}: com o wildcard
    primeiro, "kanban" é lido como id e a resposta vira 422. Mesma armadilha
    que já custou um 404 em /crm/dominio/usuarios.
    """
    where = [
        "(t.concluida_em IS NULL AND t.cancelada_em IS NULL"
        " OR t.concluida_em >= NOW() - ($1 || ' days')::interval)"
    ]
    params: list = [str(dias_concluidas)]

    if responsavel_id is not None:
        params.append(responsavel_id)
        where.append(f"t.responsavel_id = ${len(params)}")
    if q:
        params.append(f"%{q.strip()}%")
        n = len(params)
        # COALESCE em vez de `co.razao_social`: com o LEFT JOIN da 006, a
        # tarefa de parceiro tem `co` inteiro nulo, e `co.razao_social ILIKE`
        # devolve NULL — que numa cláusula OR não é falso, é ausência. A
        # busca simplesmente nunca encontraria tarefa de parceiro.
        where.append(
            f"(t.titulo ILIKE ${n}"
            f" OR COALESCE(cp.razao_social, co.razao_social) ILIKE ${n}"
            f" OR COALESCE(o.numero, '') ILIKE ${n})"
        )

    rows = await conn.fetch(
        f"{_SELECT_BASE} WHERE {' AND '.join(where)} ORDER BY t.prazo",
        *params,
    )

    agora = _agora()
    itens = [_linha(r, agora) for r in rows]

    colunas = []
    for chave, rotulo in COLUNAS_KANBAN:
        # Atrasada e hoje: mais antiga primeiro, que é a ordem de atacar.
        # Futura: a mais próxima primeiro. Concluída: a mais recente primeiro,
        # porque ali a pergunta é "o que acabou de andar".
        da_coluna = [i for i in itens if i["situacao"] == chave]
        da_coluna.sort(key=lambda i: i["prazo"], reverse=(chave == "concluida"))
        colunas.append({
            "situacao": chave,
            "rotulo": rotulo,
            "quantidade": len(da_coluna),
            "itens": da_coluna[:por_coluna],
            "somente_leitura": chave == "concluida",
        })
    return colunas


@router.get("/{tarefa_id}", response_model=TarefaOut)
async def obter(tarefa_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    return await _obter(conn, tarefa_id)


# ── Escrita ──────────────────────────────────────────────────────────

@router.post("", response_model=TarefaOut, status_code=http.HTTP_201_CREATED)
async def criar(
    payload: TarefaCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    await _validar_referencias(
        conn, payload.oportunidade_id, payload.conta_id, payload.responsavel_id
    )
    novo_id = await _inserir(
        conn, payload, payload.oportunidade_id, payload.conta_id, user["id"], None
    )
    return await _obter(conn, novo_id)


@router.patch("/{tarefa_id}", response_model=TarefaOut)
async def editar(
    tarefa_id: UUID,
    payload: TarefaEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    estado, _, _, _ = await _estado_e_alvo(conn, tarefa_id)
    try:
        regras.validar_edicao(estado)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    campos = payload.model_dump(exclude_unset=True)
    campos = {k: v for k, v in campos.items() if k in CAMPOS_EDITAVEIS}
    if not campos:
        return await _obter(conn, tarefa_id)

    if "responsavel_id" in campos and campos["responsavel_id"] is not None:
        if not await conn.fetchval(
            "SELECT 1 FROM usuarios WHERE id = $1 AND ativo", campos["responsavel_id"]
        ):
            raise HTTPException(422, "Responsável não encontrado ou inativo.")

    sets, params = [], []
    for chave, valor in campos.items():
        params.append(valor)
        sets.append(f"{chave} = ${len(params)}")
    params.append(tarefa_id)

    await conn.execute(
        f"UPDATE tarefas SET {', '.join(sets)}, atualizado_em = NOW()"
        f" WHERE id = ${len(params)}",
        *params,
    )
    return await _obter(conn, tarefa_id)


@router.post("/{tarefa_id}/concluir", response_model=TarefaOut)
async def concluir(
    tarefa_id: UUID,
    payload: Conclusao,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Conclui a tarefa e agenda a próxima na MESMA transação.

    A próxima é obrigatória enquanto a oportunidade está aberta. Quando ela
    já foi finalizada, o campo pode vir nulo — não há próximo passo. Em
    tarefa de PARCEIRO nunca é obrigatória, e continua sendo aceita: quem
    já sabe o próximo contato agenda ali mesmo, e quem não sabe não é
    forçado a inventar um.

    Devolve a tarefa CONCLUÍDA, não a nova. Quem chamou está fechando um
    item; a lista recarrega e mostra as duas.
    """
    estado, status_opp, oportunidade_id, conta_id = await _estado_e_alvo(
        conn, tarefa_id
    )

    try:
        regras.validar_conclusao(estado, status_opp, payload.proxima is not None)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    if payload.proxima is not None:
        await _validar_referencias(
            conn, oportunidade_id, conta_id, payload.proxima.responsavel_id
        )

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE tarefas
               SET concluida_em = NOW(),
                   resultado = $2,
                   atualizado_em = NOW()
             WHERE id = $1
            """,
            tarefa_id, (payload.resultado or "").strip() or None,
        )
        if payload.proxima is not None:
            await _inserir(
                conn, payload.proxima, oportunidade_id, conta_id,
                user["id"], tarefa_id,
            )

    return await _obter(conn, tarefa_id)


@router.post("/{tarefa_id}/cancelar", response_model=TarefaOut)
async def cancelar(
    tarefa_id: UUID,
    payload: Cancelamento,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cancela a tarefa. Não exige próxima: cancelar é dizer que aquilo não
    deveria ter sido agendado, e não que o negócio andou.
    """
    estado, _, _, _ = await _estado_e_alvo(conn, tarefa_id)
    try:
        regras.validar_cancelamento(estado)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    await conn.execute(
        """
        UPDATE tarefas
           SET cancelada_em = NOW(),
               motivo_cancelamento = $2,
               atualizado_em = NOW()
         WHERE id = $1
        """,
        tarefa_id, (payload.motivo or "").strip() or None,
    )
    return await _obter(conn, tarefa_id)
