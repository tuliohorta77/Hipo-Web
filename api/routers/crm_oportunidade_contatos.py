"""
HIPO — CRM: o comitê da oportunidade (ABM / multithreading). Entrega 045.

Antes, a oportunidade tinha UM contato (`oportunidades.contato_id`). A venda
de medicina ocupacional passa por várias pessoas da mesma empresa — RH, DP,
Compras, SESMT, médico do trabalho, diretoria — e depender de uma só é o
jeito mais comum de perder negócio em silêncio. Agora a oportunidade tem uma
LISTA de contatos, cada um com o seu papel na decisão.

Decisões que este módulo materializa:

  * `oportunidades.contato_id` CONTINUA e é o ESPELHO do principal.
    Relatório, busca, proposta, RPeR e importadores leem a coluna; tirá-la
    seria refator amplo sem ganho para quem usa a tela. O espelho é escrito
    SÓ por `definir_principal`, sempre na transação de quem mexe na lista —
    duas escritas em lugares diferentes divergem na primeira vez que alguém
    esquece uma delas.

  * O contato precisa ser DA CONTA. A pessoa entra no comitê se estiver
    vinculada (ativa) à conta principal ou a um dos CNPJs adicionais da
    oportunidade. Quem ainda não está vinculado é vinculado à conta
    principal na mesma transação — é o caminho de quem descobre uma pessoa
    nova no meio da negociação e não quer ir até a ficha da empresa.

  * O primeiro a entrar vira principal sozinho. Oportunidade com gente no
    comitê e sem principal deixaria o espelho vazio, e a busca e a proposta
    voltariam a dizer "sem contato" para uma negociação com três pessoas.

  * Tarefa conta como envolvimento. Quem cria tarefa com um contato que
    ainda não está no comitê o põe lá (`incluir_no_comite`), sem papel —
    conversar com alguém É envolver essa pessoa, e a lista que a tela mostra
    precisa contar isso sem depender de alguém lembrar de cadastrar.

Regras puras em services/contato_oportunidade.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import auditoria
from services import contato_oportunidade as regras
from services import temperatura_contato as temp
from services.contato_oportunidade import ContatoOportunidadeInvalido

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class _ComPapel(BaseModel):
    @field_validator("papel", check_fields=False)
    @classmethod
    def _papel(cls, v: str | None) -> str | None:
        try:
            return regras.validar_papel(v)
        except ContatoOportunidadeInvalido as e:
            raise ValueError(str(e)) from e


class ContatoNoComiteCriar(_ComPapel):
    contato_id: UUID
    papel: str | None = None
    principal: bool = False
    # Só usado quando a pessoa ainda não está vinculada à conta: é o cargo
    # do vínculo que nasce junto.
    cargo: str | None = Field(None, max_length=100)


class ContatoNoComiteEditar(_ComPapel):
    papel: str | None = None
    principal: bool | None = None


class ContatoDoComite(BaseModel):
    contato_id: UUID
    nome: str
    cargo: str | None
    telefone: str | None
    telefone_whatsapp: bool
    telefone_2: str | None
    telefone_2_whatsapp: bool
    email: str | None
    linkedin: str | None
    ativo: bool
    papel: str | None
    papel_rotulo: str | None
    principal: bool
    # Quantas interações concluídas com esta pessoa NESTA oportunidade, e
    # quando foi a última. É o que mostra se o "multithreading" é real ou só
    # cadastro: três nomes na lista e todas as conversas com um só é
    # single-thread com outro nome.
    interacoes: int
    ultima_interacao: datetime | None
    criado_em: datetime
    # 046: a temperatura da PESSOA (todas as conversas com ela, em qualquer
    # oportunidade) — `interacoes` acima é só desta negociação.
    temperatura: str = "frio"
    temperatura_rotulo: str = "Frio"
    temperatura_pontos: int = 0
    interacoes_60d: int = 0
    ultima_conversa: datetime | None = None
    dias_desde_ultima_conversa: int | None = None


class FarolOut(BaseModel):
    nivel: str
    tom: str
    rotulo: str
    dica: str
    tem_decisor: bool
    minimo_ideal: int
    maximo_ideal: int


class ComiteOut(BaseModel):
    oportunidade_id: UUID
    itens: list[ContatoDoComite]
    farol: FarolOut


# ── Temperatura do contato (046) ─────────────────────────────────────

async def temperaturas(
    conn, contato_ids, agora: datetime | None = None,
) -> dict:
    """
    Temperatura (quente/morno/frio) de cada contato, a partir das tarefas
    CONCLUÍDAS com ele em qualquer alvo. Regra em services/temperatura_contato.

    Duas consultas e não uma por contato: a ficha da conta pode ter dezenas
    de pessoas, e N+1 aqui seria uma ida ao banco por linha da lista.
    """
    ids = list({i for i in contato_ids if i is not None})
    agora = agora or datetime.now(timezone.utc)
    if not ids:
        return {}
    desde = agora - timedelta(days=temp.JANELA_DIAS + 1)
    janela = await conn.fetch(
        """
        SELECT contato_id, tipo, concluida_em
          FROM tarefas
         WHERE contato_id = ANY($1::uuid[])
           AND concluida_em IS NOT NULL AND cancelada_em IS NULL
           AND concluida_em >= $2
        """,
        ids, desde,
    )
    ultimas = await conn.fetch(
        """
        SELECT contato_id, max(concluida_em) AS ultima
          FROM tarefas
         WHERE contato_id = ANY($1::uuid[])
           AND concluida_em IS NOT NULL AND cancelada_em IS NULL
         GROUP BY contato_id
        """,
        ids,
    )
    por_contato: dict = {i: [] for i in ids}
    for r in janela:
        por_contato[r["contato_id"]].append(
            temp.Interacao(tipo=r["tipo"], concluida_em=r["concluida_em"])
        )
    ultima = {r["contato_id"]: r["ultima"] for r in ultimas}
    return {
        i: temp.como_dict(temp.calcular(por_contato[i], agora, ultima.get(i)))
        for i in ids
    }


# ── Helpers reaproveitados por oportunidades e tarefas ───────────────

async def contas_da_oportunidade(conn, oportunidade_id: UUID) -> list[UUID]:
    """A conta principal e os CNPJs adicionais vivos da oportunidade."""
    rows = await conn.fetch(
        """
        SELECT o.conta_id FROM oportunidades o WHERE o.id = $1
        UNION
        SELECT oc.conta_id FROM oportunidade_contas oc
         WHERE oc.oportunidade_id = $1 AND oc.removido_em IS NULL
        """,
        oportunidade_id,
    )
    return [r["conta_id"] for r in rows]


async def contato_vinculado(conn, contato_id: UUID, contas: list[UUID]) -> bool:
    if not contas:
        return False
    return bool(await conn.fetchval(
        """
        SELECT 1 FROM conta_contatos
         WHERE contato_id = $1 AND conta_id = ANY($2::uuid[]) AND ativo
         LIMIT 1
        """,
        contato_id, contas,
    ))


async def contato_ativo(conn, contato_id: UUID) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM contatos WHERE id = $1 AND ativo", contato_id
    ))


async def definir_principal(
    conn, oportunidade_id: UUID, contato_id: UUID | None
) -> None:
    """
    Marca `contato_id` como principal do comitê e atualiza o espelho
    `oportunidades.contato_id`. None desmarca o principal e zera o espelho.

    Rebaixa o anterior ANTES de promover — senão o índice único parcial
    `uq_opp_contato_principal` rejeita a troca. Chamar DENTRO de transação.
    """
    await conn.execute(
        """
        UPDATE oportunidade_contatos
           SET principal = FALSE, atualizado_em = NOW()
         WHERE oportunidade_id = $1 AND principal
           AND ($2::uuid IS NULL OR contato_id <> $2)
        """,
        oportunidade_id, contato_id,
    )
    if contato_id is not None:
        await conn.execute(
            """
            UPDATE oportunidade_contatos
               SET principal = TRUE, atualizado_em = NOW()
             WHERE oportunidade_id = $1 AND contato_id = $2 AND NOT principal
            """,
            oportunidade_id, contato_id,
        )
    await conn.execute(
        """
        UPDATE oportunidades
           SET contato_id = $2, atualizado_em = NOW()
         WHERE id = $1 AND contato_id IS DISTINCT FROM $2
        """,
        oportunidade_id, contato_id,
    )


async def incluir_no_comite(
    conn,
    oportunidade_id: UUID,
    contato_id: UUID,
    *,
    criado_por,
    papel: str | None = None,
    principal: bool = False,
) -> None:
    """
    Põe a pessoa no comitê (idempotente) e, se o comitê ainda não tem
    principal, faz dela a principal. Chamar DENTRO de transação.

    Já estando lá, só o papel muda — e só se um papel veio. Uma tarefa
    criada com a pessoa não pode apagar o papel que alguém classificou.
    """
    await conn.execute(
        """
        INSERT INTO oportunidade_contatos
               (oportunidade_id, contato_id, papel, criado_por)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (oportunidade_id, contato_id) DO UPDATE
           SET papel = COALESCE(EXCLUDED.papel, oportunidade_contatos.papel),
               atualizado_em = NOW()
        """,
        oportunidade_id, contato_id, papel, criado_por,
    )
    tem_principal = await conn.fetchval(
        """
        SELECT 1 FROM oportunidade_contatos
         WHERE oportunidade_id = $1 AND principal
        """,
        oportunidade_id,
    )
    if principal or not tem_principal:
        await definir_principal(conn, oportunidade_id, contato_id)


async def _travar(conn, oportunidade_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT id, conta_id FROM oportunidades WHERE id = $1 FOR UPDATE",
        oportunidade_id,
    )
    if row is None:
        raise HTTPException(404, "Oportunidade não encontrada.")
    return dict(row)


async def comite(conn, oportunidade_id: UUID) -> dict:
    """O comitê inteiro com o farol. Usado pelo GET e pela resposta da escrita."""
    if not await conn.fetchval(
        "SELECT 1 FROM oportunidades WHERE id = $1", oportunidade_id
    ):
        raise HTTPException(404, "Oportunidade não encontrada.")

    rows = await conn.fetch(
        """
        SELECT ct.id AS contato_id, ct.nome, ct.telefone, ct.telefone_whatsapp,
               ct.telefone_2, ct.telefone_2_whatsapp, ct.email, ct.linkedin,
               ct.ativo, oc.papel, oc.principal, oc.criado_em,
               -- O cargo mora no VÍNCULO com a conta. Prefere o da conta
               -- principal; num CNPJ adicional, o de lá.
               (SELECT cc.cargo FROM conta_contatos cc
                 WHERE cc.contato_id = ct.id AND cc.cargo IS NOT NULL
                   AND cc.conta_id IN (
                       SELECT o.conta_id FROM oportunidades o WHERE o.id = $1
                       UNION
                       SELECT x.conta_id FROM oportunidade_contas x
                        WHERE x.oportunidade_id = $1 AND x.removido_em IS NULL)
                 ORDER BY (cc.conta_id = (SELECT conta_id FROM oportunidades
                                           WHERE id = $1)) DESC,
                          cc.ativo DESC
                 LIMIT 1) AS cargo,
               (SELECT count(*) FROM tarefas t
                 WHERE t.oportunidade_id = $1 AND t.contato_id = ct.id
                   AND t.concluida_em IS NOT NULL) AS interacoes,
               (SELECT max(t.concluida_em) FROM tarefas t
                 WHERE t.oportunidade_id = $1 AND t.contato_id = ct.id
                   AND t.concluida_em IS NOT NULL) AS ultima_interacao
          FROM oportunidade_contatos oc
          JOIN contatos ct ON ct.id = oc.contato_id
         WHERE oc.oportunidade_id = $1
         ORDER BY oc.principal DESC,
                  array_position(
                      ARRAY['decisor','campeao','influenciador',
                            'operacional','compras','tecnico']::varchar[],
                      oc.papel),
                  ct.nome
        """,
        oportunidade_id,
    )
    temps = await temperaturas(conn, [r["contato_id"] for r in rows])
    itens = []
    for r in rows:
        d = dict(r)
        d["papel_rotulo"] = regras.ROTULOS_PAPEL.get(d["papel"]) if d["papel"] else None
        d.update(temps.get(d["contato_id"], {}))
        itens.append(d)

    ativos = [i for i in itens if i["ativo"]]
    farol = regras.farol_multithreading(len(ativos), [i["papel"] for i in ativos])
    return {
        "oportunidade_id": oportunidade_id,
        "itens": itens,
        "farol": {
            **farol.__dict__,
            "minimo_ideal": regras.MINIMO_IDEAL,
            "maximo_ideal": regras.MAXIMO_IDEAL,
        },
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/{oportunidade_id}/contatos", response_model=ComiteOut)
async def listar(
    oportunidade_id: UUID,
    request: Request,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    resultado = await comite(conn, oportunidade_id)
    await auditoria.registrar_leitura(
        conn, request, user, auditoria.RECURSO_CONTATO,
        [i["contato_id"] for i in resultado["itens"]],
        {"oportunidade_id": oportunidade_id},
    )
    return resultado


@router.post(
    "/{oportunidade_id}/contatos",
    response_model=ComiteOut,
    status_code=http.HTTP_201_CREATED,
)
async def adicionar(
    oportunidade_id: UUID,
    payload: ContatoNoComiteCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Põe uma pessoa no comitê. Se ela ainda não é contato da conta, vira —
    vinculada à conta principal, com o `cargo` informado.
    """
    if not await contato_ativo(conn, payload.contato_id):
        raise HTTPException(422, "Contato não encontrado ou inativo.")

    async with conn.transaction():
        opp = await _travar(conn, oportunidade_id)
        ja_esta = await conn.fetchval(
            """
            SELECT 1 FROM oportunidade_contatos
             WHERE oportunidade_id = $1 AND contato_id = $2
            """,
            oportunidade_id, payload.contato_id,
        )
        if ja_esta:
            raise HTTPException(409, "Este contato já está nesta oportunidade.")

        contas = await contas_da_oportunidade(conn, oportunidade_id)
        if not await contato_vinculado(conn, payload.contato_id, contas):
            # Religa um vínculo antigo em vez de bater na PK.
            await conn.execute(
                """
                INSERT INTO conta_contatos (conta_id, contato_id, cargo)
                VALUES ($1, $2, $3)
                ON CONFLICT (conta_id, contato_id) DO UPDATE
                   SET ativo = TRUE,
                       cargo = COALESCE(EXCLUDED.cargo, conta_contatos.cargo)
                """,
                opp["conta_id"], payload.contato_id,
                (payload.cargo or "").strip() or None,
            )

        await incluir_no_comite(
            conn, oportunidade_id, payload.contato_id,
            criado_por=user["id"], papel=payload.papel,
            principal=payload.principal,
        )
    return await comite(conn, oportunidade_id)


@router.patch("/{oportunidade_id}/contatos/{contato_id}", response_model=ComiteOut)
async def editar(
    oportunidade_id: UUID,
    contato_id: UUID,
    payload: ContatoNoComiteEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Papel e/ou principal. Desmarcar o principal não é aceito: promova outro."""
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(422, "Nenhum campo para atualizar.")
    if dados.get("principal") is False:
        raise HTTPException(
            422,
            "Para trocar o principal, marque outra pessoa como principal.",
        )

    async with conn.transaction():
        await _travar(conn, oportunidade_id)
        existe = await conn.fetchval(
            """
            SELECT 1 FROM oportunidade_contatos
             WHERE oportunidade_id = $1 AND contato_id = $2
            """,
            oportunidade_id, contato_id,
        )
        if not existe:
            raise HTTPException(404, "Este contato não está nesta oportunidade.")

        if "papel" in dados:
            await conn.execute(
                """
                UPDATE oportunidade_contatos
                   SET papel = $3, atualizado_em = NOW()
                 WHERE oportunidade_id = $1 AND contato_id = $2
                """,
                oportunidade_id, contato_id, dados["papel"],
            )
        if dados.get("principal"):
            await definir_principal(conn, oportunidade_id, contato_id)
    return await comite(conn, oportunidade_id)


@router.delete("/{oportunidade_id}/contatos/{contato_id}", response_model=ComiteOut)
async def remover(
    oportunidade_id: UUID,
    contato_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Tira a pessoa do comitê. O vínculo com a CONTA fica — ela continua sendo
    contato da empresa, só não está nesta negociação.

    Tirar o principal promove o próximo (o mais antigo no comitê). As
    tarefas que já foram com ela continuam apontando para ela: o histórico
    de com quem se falou não muda porque a pessoa saiu da lista.
    """
    async with conn.transaction():
        await _travar(conn, oportunidade_id)
        era_principal = await conn.fetchval(
            """
            DELETE FROM oportunidade_contatos
             WHERE oportunidade_id = $1 AND contato_id = $2
            RETURNING principal
            """,
            oportunidade_id, contato_id,
        )
        if era_principal is None:
            raise HTTPException(404, "Este contato não está nesta oportunidade.")
        if era_principal:
            proximo = await conn.fetchval(
                """
                SELECT oc.contato_id
                  FROM oportunidade_contatos oc
                  JOIN contatos ct ON ct.id = oc.contato_id
                 WHERE oc.oportunidade_id = $1
                 ORDER BY ct.ativo DESC, oc.criado_em, ct.nome
                 LIMIT 1
                """,
                oportunidade_id,
            )
            await definir_principal(conn, oportunidade_id, proximo)
    return await comite(conn, oportunidade_id)
