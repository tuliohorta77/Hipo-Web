"""
HIPO — CRM: tarefas do funil e da carteira de parceiros.

O que este módulo materializa:

  * Toda tarefa pertence a UM alvo: uma oportunidade ou um parceiro. Não
    existe tarefa solta — é o que mantém o dado servindo para métrica em vez
    de virar lista de afazeres pessoal. E não existe tarefa com dois alvos:
    a primeira métrica que somasse os dois contaria a mesma tarefa duas
    vezes.

  * A tarefa de parceiro exige a próxima SEMPRE ao concluir. A regra da
    oportunidade se apoia num estado final que dispensa o próximo passo;
    parceria não tem um, e sem próximo contato marcado a relação some da
    agenda de todo mundo. Quem não tem próximo passo cancela a tarefa ou
    tira o parceiro da carteira. Ver services/tarefa.exige_proxima.

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

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field, field_validator, model_validator

from database import get_conn
from routers.auth import usuario_atual
from services import agenda as agenda_regras
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


class TarefaDeFinalizacao(TarefaBase):
    """
    O registro do fechamento de uma oportunidade: a tarefa que POST
    /crm/oportunidades/{id}/desfecho cria já concluída.

    Vive aqui, e não no router de oportunidades, porque é uma tarefa — o dia
    em que o vocabulário de tipo mudar, ela muda junto sem ninguém precisar
    lembrar que existe uma segunda definição do outro lado.

    Dois campos são opcionais, e por motivos diferentes dos da tarefa comum:

      responsavel_id — em branco, é quem está finalizando. Quem fecha o
                       negócio é quase sempre quem esteve na reunião, e um
                       seletor obrigatório nesse momento é atrito puro.
      prazo          — em branco, é agora. O registro é relato do que acabou
                       de acontecer, não compromisso futuro.
    """

    responsavel_id: UUID | None = None
    prazo: datetime | None = None


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
    #
    # None em tarefa de parceiro — e `exige_proxima(None)` devolve True, não
    # False. A tela precisa ler `alvo` junto com este campo: olhar só para o
    # status e tratar o nulo como "não exige" foi o bug que travou a
    # conclusão de tarefa de parceiro no módulo de tarefas.
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
    # Preenchido quando esta tarefa já está na agenda. É o que permite à aba
    # da oportunidade mostrar "Agendar" em umas e "Ver na agenda" em outras
    # sem uma segunda chamada por tarefa — o JOIN já está aqui, e um N+1 na
    # linha do tempo de uma negociação antiga custaria dezenas de idas ao
    # banco.
    reuniao_id: UUID | None = None
    # Quantas OUTRAS tarefas do mesmo alvo estão em aberto.
    #
    # A tela precisa deste número junto do `status_oportunidade` para saber,
    # antes de abrir o formulário, se a conclusão vai exigir a próxima:
    # exige só quem está fechando a ÚLTIMA aberta. Ler só o status voltaria
    # a cobrar a próxima de toda tarefa — o comportamento que fazia a
    # oportunidade acumular tarefa aberta sem parar.
    outras_abertas: int = 0
    # ── A reunião, vista da tarefa ──
    # Reunião e visita são a MESMA coisa na agenda e aqui. Antes, a tela de
    # Tarefas mostrava "Reunião · cancelado" para um no-show e oferecia
    # Concluir/Cancelar sem perguntar o que aconteceu, enquanto a Agenda
    # perguntava. Estes campos levam para a tarefa o que a agenda sabe, com a
    # mesma conta de services/agenda — nenhuma das duas telas deduz nada.
    #
    # `reuniao_tipo_sigla`  DG, AP, FC... (None fora da agenda ou sem tipo)
    # `desfecho_efetivo`    o que vale para contagem; só em tarefa na agenda
    # `desfecho_rotulo`     "Realizada", "Cancelada", "No-show"
    # `desfecho_sugerido`   o que o formulário pré-seleciona; só em reunião
    #                       ou visita AINDA ABERTA, com ou sem agenda
    agendavel: bool = False
    reuniao_tipo_sigla: str | None = None
    reuniao_duracao_min: int | None = None
    desfecho_efetivo: str | None = None
    desfecho_rotulo: str | None = None
    desfecho_sugerido: str | None = None
    # Só na resposta de POST /concluir: o id da próxima tarefa criada junto.
    # A tela precisa dele para pôr na agenda a próxima que é uma reunião —
    # e buscá-la depois pela corrente seria uma segunda ida ao banco.
    proxima_id: UUID | None = None
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


class ProducaoTipo(BaseModel):
    tipo: str
    rotulo: str
    realizadas: int
    agendadas: int
    canceladas: int


class ProducaoResponsavel(BaseModel):
    usuario_id: UUID
    nome: str | None
    realizadas: int
    agendadas: int


class ResumoTarefas(BaseModel):
    de: date | None
    ate: date | None
    realizadas: int
    agendadas: int
    canceladas: int
    por_tipo: list[ProducaoTipo]
    por_responsavel: list[ProducaoResponsavel]


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
           t.tarefa_anterior_id, t.criado_em,
           rn.id AS reuniao_id,
           rn.desfecho AS reuniao_desfecho,
           rn.duracao_min AS reuniao_duracao_min,
           trn.sigla AS reuniao_tipo_sigla,
           -- Quantas OUTRAS tarefas do mesmo alvo estão em aberto. A tela
           -- lê isto para saber, ANTES de abrir o formulário, se aquela
           -- conclusão vai exigir a próxima — a mesma conta que
           -- `contar_outras_abertas` faz no momento de gravar.
           --
           -- Subconsulta correlacionada e não um JOIN agregado: com JOIN,
           -- a contagem precisaria de GROUP BY na query inteira, e as seis
           -- telas que usam este SELECT passariam a carregar um GROUP BY
           -- que nenhuma delas pediu. O plano usa
           -- `idx_tarefas_abertas_por_opp` (parcial, só as abertas) e
           -- `idx_tarefas_conta`.
           (SELECT count(*) FROM tarefas x
             WHERE x.id <> t.id
               AND x.concluida_em IS NULL AND x.cancelada_em IS NULL
               AND (CASE WHEN t.oportunidade_id IS NOT NULL
                         THEN x.oportunidade_id = t.oportunidade_id
                         ELSE x.conta_id = t.conta_id END)
           ) AS outras_abertas
      FROM tarefas t
      LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
      LEFT JOIN contas co       ON co.id = o.conta_id
      LEFT JOIN contas cp       ON cp.id = t.conta_id
      LEFT JOIN usuarios u      ON u.id = t.responsavel_id
      LEFT JOIN reunioes rn     ON rn.tarefa_id = t.id
      LEFT JOIN tipos_reuniao trn ON trn.id = rn.tipo_id
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

    d["agendavel"] = agenda_regras.eh_agendavel(d["tipo"])
    desfecho_registrado = d.pop("reuniao_desfecho", None)
    if d["agendavel"]:
        if d["reuniao_id"] is not None:
            d["desfecho_efetivo"] = agenda_regras.desfecho_efetivo(
                desfecho=desfecho_registrado,
                concluida_em=d["concluida_em"],
                cancelada_em=d["cancelada_em"],
                inicio=d["prazo"],
            )
            d["desfecho_rotulo"] = agenda_regras.ROTULO_DESFECHO.get(
                d["desfecho_efetivo"]
            )
        if d["situacao"] in regras.SITUACOES_ABERTAS:
            d["desfecho_sugerido"] = agenda_regras.sugestao_de_desfecho(
                d["prazo"],
                d["reuniao_duracao_min"] or agenda_regras.DURACAO_PADRAO_MIN,
                agora,
            )
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


MSG_REUNIAO_PELO_DESFECHO = (
    "Esta tarefa é uma reunião da agenda: registre o que aconteceu "
    "(Realizada, Cancelada ou No-show) em vez de concluir ou cancelar."
)


async def _reuniao_da_tarefa(conn, tarefa_id: UUID) -> UUID | None:
    return await conn.fetchval(
        "SELECT id FROM reunioes WHERE tarefa_id = $1", tarefa_id
    )


async def _travar_alvo(
    conn, oportunidade_id: UUID | None, conta_id: UUID | None
) -> None:
    """
    Trava a linha do ALVO para serializar as conclusões dele.

    Sem isto, duas pessoas fechando as duas últimas tarefas da mesma
    oportunidade ao mesmo tempo leriam, cada uma, "ainda sobra outra
    aberta". As duas passariam sem próxima e a oportunidade acabaria sem
    próximo passo — a única coisa que a regra existe para impedir.

    Trava o ALVO e não as tarefas: é o alvo que tem a invariante, e é ele
    que uma tarefa nova poderia estar entrando enquanto a contagem roda.
    A tranca vale só até o fim da transação, e como a oportunidade é
    disputada por duas ou três pessoas no máximo, ninguém espera.
    """
    if oportunidade_id is not None:
        await conn.execute(
            "SELECT 1 FROM oportunidades WHERE id = $1 FOR UPDATE",
            oportunidade_id,
        )
    elif conta_id is not None:
        await conn.execute(
            "SELECT 1 FROM contas WHERE id = $1 FOR UPDATE", conta_id
        )


async def contar_outras_abertas(
    conn,
    tarefa_id: UUID | None,
    oportunidade_id: UUID | None,
    conta_id: UUID | None,
) -> int:
    """
    Quantas OUTRAS tarefas do mesmo alvo estão em aberto.

    É o número que decide se concluir esta aqui obriga a marcar a próxima
    (ver services/tarefa.exige_proxima). Zero significa "esta é a última" —
    e é só nesse caso que a próxima é cobrada.

    "Aberta" aqui é a mesma definição de `esta_aberta`: nem concluída nem
    cancelada. Não passa pelo relógio de propósito — atrasada continua
    sendo um próximo passo, só que atrasado, e tratá-la como inexistente
    faria a tela cobrar uma tarefa nova de quem já está devendo uma.

    `tarefa_id` None conta TODAS as abertas do alvo: é o que a lista usa
    para avisar quantas existem, sem excluir nenhuma.

    Usa `idx_tarefas_abertas_por_opp` (parcial, só as abertas) no caminho da
    oportunidade, e `idx_tarefas_conta` no do parceiro.
    """
    if oportunidade_id is not None:
        return await conn.fetchval(
            """
            SELECT count(*) FROM tarefas
             WHERE oportunidade_id = $1
               AND concluida_em IS NULL AND cancelada_em IS NULL
               AND ($2::uuid IS NULL OR id <> $2)
            """,
            oportunidade_id, tarefa_id,
        )
    if conta_id is not None:
        return await conn.fetchval(
            """
            SELECT count(*) FROM tarefas
             WHERE conta_id = $1
               AND concluida_em IS NULL AND cancelada_em IS NULL
               AND ($2::uuid IS NULL OR id <> $2)
            """,
            conta_id, tarefa_id,
        )
    # Sem alvo não deveria existir (ck_tarefa_alvo), mas devolver 0 aqui
    # falha para o lado SEGURO: exige a próxima em vez de dispensá-la.
    return 0


async def validar_referencias(
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


async def inserir_tarefa_concluida(
    conn,
    dados: TarefaDeFinalizacao,
    *,
    oportunidade_id: UUID,
    criado_por,
) -> UUID:
    """
    Grava o registro do fechamento: tarefa que NASCE concluída.

    Chamada por POST /crm/oportunidades/{id}/desfecho, dentro da transação
    dele. Mora aqui, junto do resto da escrita de tarefa, para o INSERT ter
    uma versão só — duas cópias do mesmo INSERT divergem na primeira coluna
    nova, e a que divergir vai ser a que ninguém está olhando.

    `concluida_em` é NOW() e não o prazo informado de propósito: prazo é
    QUANDO a coisa aconteceu (a pessoa pode registrar hoje a reunião de
    ontem), e concluída_em é quando o sistema soube. Misturar os dois faria
    a produção do mês mudar conforme a data que alguém digitou.

    Sem `tarefa_anterior_id`: o registro do fechamento não continua corrente
    de follow-up nenhuma. Ele a encerra.
    """
    responsavel_id = dados.responsavel_id or criado_por
    prazo = dados.prazo or _agora()
    return await conn.fetchval(
        """
        INSERT INTO tarefas (
            oportunidade_id, conta_id, tipo, titulo, descricao,
            responsavel_id, prazo, tarefa_anterior_id, criado_por,
            concluida_em
        )
        VALUES ($1, NULL, $2, $3, $4, $5, $6, NULL, $7, NOW())
        RETURNING id
        """,
        oportunidade_id, dados.tipo, dados.titulo,
        (dados.descricao or "").strip() or None,
        responsavel_id, prazo, criado_por,
    )


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class _Params:
    """
    Acumulador de parâmetros posicionais do asyncpg.

    Existe porque a numeração manual (`f"${len(params) + 1}"`) já produziu
    dois bugs neste arquivo: um filtro novo no meio da lista desloca todos os
    índices abaixo dele, e o erro não aparece como exceção — aparece como
    consulta que devolve a linha errada. Aqui o número sai do próprio append.
    """

    def __init__(self) -> None:
        self.valores: list = []

    def add(self, valor) -> str:
        self.valores.append(valor)
        return f"${len(self.valores)}"


def _clausula_busca(q: str | None, p: _Params) -> str | None:
    """
    Busca livre por título, empresa ou número da oportunidade.

    COALESCE em vez de `co.razao_social`: com o LEFT JOIN da 006, a tarefa de
    parceiro tem `co` inteiro nulo, e `co.razao_social ILIKE` devolve NULL —
    que numa cláusula OR não é falso, é ausência. A busca simplesmente nunca
    encontraria tarefa de parceiro.
    """
    if not q or not q.strip():
        return None
    n = p.add(f"%{q.strip()}%")
    return (
        f"(t.titulo ILIKE {n}"
        f" OR COALESCE(cp.razao_social, co.razao_social) ILIKE {n}"
        f" OR COALESCE(o.numero, '') ILIKE {n})"
    )


def _dentro(coluna: str, ini: str | None, fim: str | None) -> str:
    """
    Fragmento SQL "esta coluna de data caiu na janela".

    Sem janela, a resposta é "a coluna está preenchida" — que é o que faz
    `realizadas` continuar significando "concluídas" quando o período pedido
    é 'desde sempre', em vez de virar a contagem de todas as tarefas.
    """
    if ini is None and fim is None:
        return f"{coluna} IS NOT NULL"
    partes = [f"{coluna} IS NOT NULL"]
    if ini is not None:
        partes.append(f"{coluna} >= {ini}")
    if fim is not None:
        partes.append(f"{coluna} < {fim}")
    return "(" + " AND ".join(partes) + ")"


# ── Leitura ──────────────────────────────────────────────────────────

BASES_DATA = {"prazo": "t.prazo", "conclusao": "t.concluida_em"}


@router.get("", response_model=TarefaLista)
async def listar(
    oportunidade_id: UUID | None = None,
    conta_id: UUID | None = None,
    responsavel_id: UUID | None = None,
    tipo: str | None = Query(None),
    de: date | None = Query(None),
    ate: date | None = Query(None),
    base: str = Query("prazo"),
    q: str | None = Query(None, max_length=200),
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

    `tipo`, `de`, `ate` e `base` existem para o drilldown do resumo: clicar em
    "12 reuniões realizadas em agosto" tem que abrir exatamente aquelas doze,
    e não uma lista parecida. Por isso o recorte é o MESMO dos dois lados —
    services/tarefa.py:janela_utc.

    `base` diz QUAL data a janela recorta, e o default não é inocente:

      * 'prazo'     — quando a tarefa está marcada. É a pergunta da agenda.
      * 'conclusao' — quando ela foi feita. É a pergunta da produção.

    São números diferentes de propósito. Uma reunião marcada para 28/08 e
    feita em 02/09 é de agosto na agenda e de setembro na produção; um único
    filtro de data teria que escolher uma das duas e mentir na outra.

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
    if base not in BASES_DATA:
        raise HTTPException(
            422, f"base inválida. Use: {', '.join(BASES_DATA)}."
        )
    if tipo is not None and tipo not in regras.TIPOS:
        raise HTTPException(
            422, f"Tipo inválido: '{tipo}'. Use: {', '.join(regras.TIPOS)}."
        )
    for s in situacao or []:
        if s not in regras.SITUACOES:
            raise HTTPException(
                422, f"Situação inválida: '{s}'. Use: {', '.join(regras.SITUACOES)}."
            )
    try:
        inicio, fim = regras.janela_utc(de, ate)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    p = _Params()
    where = []
    if oportunidade_id is not None:
        where.append(f"t.oportunidade_id = {p.add(oportunidade_id)}")
    if conta_id is not None:
        where.append(f"t.conta_id = {p.add(conta_id)}")
    if responsavel_id is not None:
        where.append(f"t.responsavel_id = {p.add(responsavel_id)}")
    if tipo is not None:
        where.append(f"t.tipo = {p.add(tipo)}")
    if inicio is not None or fim is not None:
        where.append(_dentro(
            BASES_DATA[base],
            p.add(inicio) if inicio is not None else None,
            p.add(fim) if fim is not None else None,
        ))
    busca = _clausula_busca(q, p)
    if busca:
        where.append(busca)
    clausula = f"WHERE {' AND '.join(where)}" if where else ""

    rows = await conn.fetch(
        f"{_SELECT_BASE} {clausula} ORDER BY t.prazo"
        f" LIMIT {p.add(limit)} OFFSET {p.add(offset)}",
        *p.valores,
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


async def _itens_por_situacao(conn, responsavel_id, q, dias_concluidas) -> dict[str, list]:
    """
    Todas as tarefas do kanban já separadas e ordenadas por coluna.

    Compartilhado entre /kanban e /kanban/coluna para que as duas rotas vejam
    exatamente o mesmo conjunto, na mesma ordem — é isso que garante que a
    página seguinte continue de onde a anterior parou.
    """
    p = _Params()
    where = [
        f"(t.concluida_em IS NULL AND t.cancelada_em IS NULL"
        f" OR t.concluida_em >= NOW() - ({p.add(str(dias_concluidas))} || ' days')::interval)"
    ]
    if responsavel_id is not None:
        where.append(f"t.responsavel_id = {p.add(responsavel_id)}")
    busca = _clausula_busca(q, p)
    if busca:
        where.append(busca)

    # `t.id` desempata prazos iguais: sem ele a ordem entre duas tarefas das
    # 14h é do Postgres, e uma página poderia repetir o cartão da outra.
    rows = await conn.fetch(
        f"{_SELECT_BASE} WHERE {' AND '.join(where)} ORDER BY t.prazo, t.id",
        *p.valores,
    )

    agora = _agora()
    itens = [_linha(r, agora) for r in rows]

    por_situacao = {}
    for chave, _rotulo in COLUNAS_KANBAN:
        # Atrasada e hoje: mais antiga primeiro, que é a ordem de atacar.
        # Futura: a mais próxima primeiro. Concluída: a mais recente primeiro,
        # porque ali a pergunta é "o que acabou de andar". O sort do Python é
        # estável, então o desempate por id do SQL sobrevive.
        da_coluna = [i for i in itens if i["situacao"] == chave]
        da_coluna.sort(key=lambda i: i["prazo"], reverse=(chave == "concluida"))
        por_situacao[chave] = da_coluna
    return por_situacao


def _coluna(chave, rotulo, itens, offset, limit) -> dict:
    return {
        "situacao": chave,
        "rotulo": rotulo,
        "quantidade": len(itens),
        "itens": itens[offset:offset + limit],
        "somente_leitura": chave == "concluida",
    }


@router.get("/kanban", response_model=list[ColunaTarefas])
async def kanban(
    responsavel_id: UUID | None = None,
    q: str | None = Query(None, max_length=200),
    por_coluna: int = Query(100, ge=1, le=500),
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

    A contagem é da coluna inteira; os cartões são os primeiros `por_coluna`.
    O resto vem página a página por GET /kanban/coluna — nenhuma tarefa fica
    inalcançável atrás de um "+46 não exibidas".

    Este endpoint precisa vir declarado ANTES de /{tarefa_id}: com o wildcard
    primeiro, "kanban" é lido como id e a resposta vira 422. Mesma armadilha
    que já custou um 404 em /crm/dominio/usuarios.
    """
    por_situacao = await _itens_por_situacao(conn, responsavel_id, q, dias_concluidas)
    return [
        _coluna(chave, rotulo, por_situacao[chave], 0, por_coluna)
        for chave, rotulo in COLUNAS_KANBAN
    ]


@router.get("/kanban/coluna", response_model=ColunaTarefas)
async def kanban_coluna(
    situacao: str = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    responsavel_id: UUID | None = None,
    q: str | None = Query(None, max_length=200),
    dias_concluidas: int = Query(7, ge=1, le=90),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Uma coluna do kanban de tarefas, a partir de `offset`. É o "carregar mais".

    Mesmos filtros e mesma ordem do /kanban. Também declarado antes de
    /{tarefa_id}, pela mesma armadilha do /kanban.
    """
    rotulos = dict(COLUNAS_KANBAN)
    if situacao not in rotulos:
        raise HTTPException(
            422, f"Situação inválida: '{situacao}'. Use: {', '.join(rotulos)}."
        )
    por_situacao = await _itens_por_situacao(conn, responsavel_id, q, dias_concluidas)
    return _coluna(situacao, rotulos[situacao], por_situacao[situacao], offset, limit)


@router.get("/resumo", response_model=ResumoTarefas)
async def resumo(
    de: date | None = Query(None, description="Primeiro dia, no fuso da operação."),
    ate: date | None = Query(None, description="Último dia, inclusivo."),
    responsavel_id: UUID | None = None,
    q: str | None = Query(None, max_length=200),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Produção do período: quantas tarefas de cada tipo foram REALIZADAS,
    quantas estavam agendadas e quantas foram canceladas.

    Existe porque "quantas reuniões tivemos em agosto" não tinha resposta no
    HIPO. A informação estava lá desde a Sprint 5 — toda tarefa tem tipo,
    prazo e concluída_em — mas só era alcançável tarefa a tarefa, dentro do
    drilldown de cada oportunidade. Dado que só existe no detalhe não é dado
    de gestão.

    TRÊS NÚMEROS, TRÊS DATAS DIFERENTES, e é isso que os torna comparáveis:

      * realizadas — `concluida_em` na janela. O que de fato aconteceu.
      * agendadas  — `prazo` na janela. O que estava marcado para o período,
                     tenha sido feito, esquecido ou ainda por fazer.
      * canceladas — `cancelada_em` na janela. O que foi desmarcado.

    Somar os três daria um número sem significado: a mesma reunião marcada e
    feita em agosto conta nos dois primeiros. Eles respondem perguntas
    diferentes — "produzimos quanto", "planejamos quanto", "desmarcamos
    quanto" — e a distância entre agendadas e realizadas é a leitura que
    interessa.

    Cancelada NÃO conta como realizada mesmo se tiver concluída_em: o CHECK do
    banco impede o par, mas o filtro é explícito porque a contagem de produção
    é a única coisa que este endpoint promete, e ela não pode depender de um
    invariante escrito em outro arquivo.

    A janela vai para o SQL, não para Python: concluídas são fluxo e crescem
    para sempre. Isso NÃO duplica a regra da situação — o recorte por data é
    determinístico e não olha o relógio. Ver services/tarefa.py:janela_utc.

    `por_tipo` devolve SEMPRE os sete tipos, inclusive os zerados e na ordem
    fixa do vocabulário. Omitir o que deu zero faria a barra trocar de ordem
    e de largura a cada mês, e o zero é informação: nenhuma visita em agosto
    é um fato sobre agosto.

    Aceita os mesmos filtros da barra da tela (responsável e busca). Agregado
    que ignora o filtro da tela produz um número global ao lado de uma lista
    filtrada — duas respostas para a mesma pergunta, na mesma tela.

    Precisa vir declarado ANTES de /{tarefa_id}: com o wildcard primeiro,
    "resumo" é lido como id e a resposta vira 422. Mesma armadilha do kanban.
    """
    try:
        inicio, fim = regras.janela_utc(de, ate)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    p = _Params()
    ini_ref = p.add(inicio) if inicio is not None else None
    fim_ref = p.add(fim) if fim is not None else None

    feita = _dentro("t.concluida_em", ini_ref, fim_ref)
    marcada = _dentro("t.prazo", ini_ref, fim_ref)
    desmarcada = _dentro("t.cancelada_em", ini_ref, fim_ref)

    where = [f"({feita} OR {marcada} OR {desmarcada})"]
    if responsavel_id is not None:
        where.append(f"t.responsavel_id = {p.add(responsavel_id)}")
    busca = _clausula_busca(q, p)
    if busca:
        where.append(busca)

    # Um GROUP BY nas duas dimensões de uma vez. Sete tipos vezes o punhado de
    # usuários ativos são dezenas de linhas — agregar as duas visões em Python
    # a partir daqui é mais barato que uma segunda ida ao banco, e garante que
    # os totais das duas tabelas batam entre si por construção.
    rows = await conn.fetch(
        f"""
        SELECT t.tipo, t.responsavel_id, u.nome AS responsavel_nome,
               count(*) FILTER (
                   WHERE {feita} AND t.cancelada_em IS NULL
               ) AS realizadas,
               count(*) FILTER (WHERE {marcada}) AS agendadas,
               count(*) FILTER (WHERE {desmarcada}) AS canceladas
          FROM tarefas t
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
          LEFT JOIN contas co       ON co.id = o.conta_id
          LEFT JOIN contas cp       ON cp.id = t.conta_id
          LEFT JOIN usuarios u      ON u.id = t.responsavel_id
         WHERE {' AND '.join(where)}
         GROUP BY t.tipo, t.responsavel_id, u.nome
        """,
        *p.valores,
    )

    por_tipo = {
        t: {"tipo": t, "rotulo": regras.ROTULOS_TIPO[t],
            "realizadas": 0, "agendadas": 0, "canceladas": 0}
        for t in regras.TIPOS
    }
    por_responsavel: dict[str, dict] = {}

    for r in rows:
        alvo = por_tipo.get(r["tipo"])
        if alvo is None:  # tipo fora do vocabulário atual, gravado antes
            alvo = por_tipo.setdefault(r["tipo"], {
                "tipo": r["tipo"], "rotulo": r["tipo"],
                "realizadas": 0, "agendadas": 0, "canceladas": 0,
            })
        alvo["realizadas"] += r["realizadas"]
        alvo["agendadas"] += r["agendadas"]
        alvo["canceladas"] += r["canceladas"]

        chave = str(r["responsavel_id"])
        pessoa = por_responsavel.setdefault(chave, {
            "usuario_id": r["responsavel_id"],
            "nome": r["responsavel_nome"],
            "realizadas": 0,
            "agendadas": 0,
        })
        pessoa["realizadas"] += r["realizadas"]
        pessoa["agendadas"] += r["agendadas"]

    linhas_tipo = [por_tipo[t] for t in regras.TIPOS] + [
        v for k, v in por_tipo.items() if k not in regras.TIPOS
    ]

    return {
        "de": de,
        "ate": ate,
        "realizadas": sum(x["realizadas"] for x in linhas_tipo),
        "agendadas": sum(x["agendadas"] for x in linhas_tipo),
        "canceladas": sum(x["canceladas"] for x in linhas_tipo),
        "por_tipo": linhas_tipo,
        # Quem não fez nem tinha nada marcado no período não aparece: a lista
        # existe para comparar produção, não para enfileirar zeros.
        "por_responsavel": sorted(
            (v for v in por_responsavel.values()
             if v["realizadas"] or v["agendadas"]),
            key=lambda x: (-x["realizadas"], -x["agendadas"], x["nome"] or ""),
        ),
    }


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
    await validar_referencias(
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

    # ── Tarefa que está na agenda ──
    # Horário, dono e título de uma reunião moram na tarefa, mas mudá-los
    # tem consequência que a tarefa comum não tem: conflito com outra
    # reunião do mesmo anfitrião e convite do Google a refazer. Editar por
    # aqui gravava direto em `tarefas` — a grade mostrava duas reuniões
    # sobrepostas e o cliente continuava com o convite do horário antigo.
    # Agora esses três campos passam pela MESMA edição da agenda.
    reuniao_id = await _reuniao_da_tarefa(conn, tarefa_id)
    if reuniao_id is not None:
        if "tipo" in campos and not agenda_regras.eh_agendavel(campos["tipo"]):
            raise HTTPException(
                422,
                "Esta tarefa está na agenda: o tipo só pode ser Reunião ou "
                "Visita. Para desmarcar, registre o desfecho como Cancelada.",
            )
        da_reuniao = {}
        if campos.get("prazo") is not None:
            da_reuniao["inicio"] = campos.pop("prazo")
        if campos.get("responsavel_id") is not None:
            da_reuniao["anfitriao_id"] = campos.pop("responsavel_id")
        if campos.get("titulo") is not None:
            da_reuniao["titulo"] = campos.pop("titulo")
        if da_reuniao:
            # Import local: crm_agenda importa deste módulo (ver cancelar).
            from routers.crm_agenda import ReuniaoEditar
            from routers.crm_agenda import editar as editar_reuniao
            try:
                edicao = ReuniaoEditar(**da_reuniao)
            except ValueError as e:
                raise HTTPException(422, str(e))
            await editar_reuniao(reuniao_id, edicao, conn=conn, user=user)
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

    A próxima é obrigatória para quem está fechando a ÚLTIMA tarefa aberta
    do alvo — é assim que a oportunidade nunca fica sem próximo passo.
    Sobrando outra aberta, concluir é livre: o próximo passo continua lá.
    Oportunidade já finalizada nunca exige, e quem não tem próximo passo com
    um parceiro cancela a tarefa (que é dizer "isso não ia acontecer") ou
    tira o parceiro da carteira; nenhuma das duas saídas exige próxima.

    A CONTAGEM MORA DENTRO DA TRANSAÇÃO, depois da tranca do alvo. Contada
    fora, duas conclusões simultâneas das duas últimas tarefas leriam
    "sobra uma" cada uma e as duas passariam — deixando a oportunidade sem
    próximo passo, que é a única coisa que a regra impede.

    Devolve a tarefa CONCLUÍDA, não a nova. Quem chamou está fechando um
    item; a lista recarrega e mostra as duas.
    """
    estado, status_opp, oportunidade_id, conta_id = await _estado_e_alvo(
        conn, tarefa_id
    )
    # Reunião na agenda não se fecha por aqui: concluir não diz se ela
    # aconteceu, e o relatório passava a contar como "realizada" uma
    # dedução que ninguém afirmou. A porta é POST /crm/agenda/tarefas/{id}/desfecho.
    if await _reuniao_da_tarefa(conn, tarefa_id) is not None:
        raise HTTPException(422, MSG_REUNIAO_PELO_DESFECHO)

    if payload.proxima is not None:
        await validar_referencias(
            conn, oportunidade_id, conta_id, payload.proxima.responsavel_id
        )

    async with conn.transaction():
        await _travar_alvo(conn, oportunidade_id, conta_id)
        outras = await contar_outras_abertas(
            conn, tarefa_id, oportunidade_id, conta_id
        )
        try:
            regras.validar_conclusao(
                estado, status_opp, payload.proxima is not None,
                outras_abertas=outras,
            )
        except TarefaInvalida as e:
            # Levantar de dentro da transação desfaz tudo — e não há nada
            # gravado ainda, então o rollback é de uma transação vazia.
            raise HTTPException(422, str(e))

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
        proxima_id = None
        if payload.proxima is not None:
            proxima_id = await _inserir(
                conn, payload.proxima, oportunidade_id, conta_id,
                user["id"], tarefa_id,
            )

    return {**await _obter(conn, tarefa_id), "proxima_id": proxima_id}


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
    # Cancelar não diz se foi cancelamento com aviso ou no-show — e é o
    # no-show o número que a operação precisa enxergar.
    if await _reuniao_da_tarefa(conn, tarefa_id) is not None:
        raise HTTPException(422, MSG_REUNIAO_PELO_DESFECHO)

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
