"""
HIPO — CRM: oportunidades (o funil de vendas).

Decisões que este módulo materializa:

  * As regras do funil vivem em services/oportunidade.py, como funções puras.
    Aqui só há orquestração: ler o estado, pedir o novo estado ao serviço,
    gravar e registrar o evento. O CHECK do banco é a última linha de defesa;
    a primeira é o serviço, que explica o erro em português.

  * TODA transição vira linha em oportunidade_eventos, na mesma transação.
    Sem isso não existe "em qual fase a gente perde" nem tempo por fase — e
    esses números não dá para reconstruir depois.

  * A numeração é gerada no próprio INSERT, via nextval + lpad. Ler a
    sequence antes e inserir depois abriria janela para duas requisições
    pegarem o mesmo número.

  * eh_finder é ligado automaticamente na conta indicadora. O usuário não
    precisa marcar "esta conta é parceira" antes de usá-la como finder — o
    sistema aprende do uso.

  * Finalizar exige registrar O QUE fechou o negócio, como tarefa já
    concluída, na mesma transação do desfecho. Ver o schema Desfecho.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
# O registro do fechamento é uma TAREFA, e o schema e o INSERT dela moram no
# router de tarefas. Importar de lá é o preço de não ter duas definições da
# mesma coisa — e é importação de mão única: crm_tarefas não conhece este
# módulo, então não há ciclo.
from routers.crm_tarefas import (
    TarefaDeFinalizacao,
    inserir_tarefa_concluida,
    validar_referencias as validar_referencias_tarefa,
)
from services import cnpj as cnpj_svc
from services import oportunidade as regras
from services.oportunidade import Estado, TransicaoInvalida

router = APIRouter()

PAPEIS = ("EC", "SDR", "EV")

# proxima_acao_em / proxima_acao_tipo saíram: quem responde "qual o próximo
# passo" agora é a tabela `tarefas`. As colunas continuam no banco porque DROP
# é destrutivo e exige export prévio — está no backlog. Fora desta lista, elas
# não são mais escritas por ninguém.
CAMPOS_EDITAVEIS = {
    "conta_id", "contato_id", "valor_mensalidade", "temperatura",
    "previsao_fechamento", "descricao", "observacoes", "origem_id",
    "finder_conta_id",
}

ORDENACOES = {
    "criado_em": "o.criado_em",
    "previsao_fechamento": "o.previsao_fechamento",
    "valor_mensalidade": "o.valor_mensalidade",
    "temperatura": "o.temperatura",
    "numero": "o.numero",
}


# ── Schemas ──────────────────────────────────────────────────────────

class EnvolvidoIn(BaseModel):
    usuario_id: UUID
    papel: str

    @field_validator("papel")
    @classmethod
    def _papel(cls, v: str) -> str:
        p = v.strip().upper()
        if p not in PAPEIS:
            raise ValueError(f"Papel inválido. Use: {', '.join(PAPEIS)}.")
        return p


class Envolvido(BaseModel):
    usuario_id: UUID
    nome: str
    papel: str


class OportunidadeCriar(BaseModel):
    conta_id: UUID
    contato_id: UUID | None = None
    # Nasce na boca do funil. O formulário deixa escolher outra — quem cadastra
    # uma oportunidade que já veio de indicação com reunião marcada não deveria
    # ter que arrastá-la duas colunas depois de criar.
    fase: str = "suspect"
    temperatura: int = 50
    valor_mensalidade: Decimal | None = Field(None, ge=0)
    previsao_fechamento: date | None = None
    descricao: str | None = None
    observacoes: str | None = None
    origem_id: int | None = None
    finder_conta_id: UUID | None = None
    proxima_acao_em: datetime | None = None
    proxima_acao_tipo: str | None = Field(None, max_length=50)
    envolvidos: list[EnvolvidoIn] = []
    concorrentes: list[int] = []

    @field_validator("fase")
    @classmethod
    def _fase(cls, v: str) -> str:
        if v not in regras.FASES_ABERTAS:
            raise ValueError(
                f"Oportunidade nasce em uma fase aberta. Use: "
                f"{', '.join(regras.FASES_ABERTAS)}."
            )
        return v

    @field_validator("temperatura")
    @classmethod
    def _temperatura(cls, v: int) -> int:
        if v not in regras.TEMPERATURAS:
            raise ValueError("Temperatura deve ser múltiplo de 10 entre 0 e 90.")
        return v


class OportunidadeEditar(BaseModel):
    """
    Campos de conteúdo. Fase e status NÃO entram aqui: mudam por endpoints
    próprios, que aplicam as regras do funil e registram evento.
    """
    conta_id: UUID | None = None
    contato_id: UUID | None = None
    valor_mensalidade: Decimal | None = Field(None, ge=0)
    temperatura: int | None = None
    previsao_fechamento: date | None = None
    descricao: str | None = None
    observacoes: str | None = None
    origem_id: int | None = None
    finder_conta_id: UUID | None = None
    proxima_acao_em: datetime | None = None
    proxima_acao_tipo: str | None = Field(None, max_length=50)

    @field_validator("temperatura")
    @classmethod
    def _temperatura(cls, v: int | None) -> int | None:
        if v is not None and v not in regras.TEMPERATURAS:
            raise ValueError("Temperatura deve ser múltiplo de 10 entre 0 e 90.")
        return v


class MoverFase(BaseModel):
    fase: str


class Desfecho(BaseModel):
    """
    Fechar a oportunidade. `tarefa` é OBRIGATÓRIA.

    A regra do módulo de tarefas é que concluir uma exige agendar a próxima —
    e a oportunidade finalizada é a única exceção, porque não há próximo
    passo. Era por essa exceção que o histórico vazava: o negócio fechava e
    ficava registrado o status mais um motivo de lista fechada. Isso
    classifica o desfecho; não conta o que aconteceu.

    Então finalizar passa a exigir o registro do ato do fechamento — a
    reunião, a ligação, a conferência de cadastro — como tarefa JÁ CONCLUÍDA.
    Não cria pendência: nasce fechada, entra na linha do tempo da
    oportunidade e conta na produção do mês, porque foi trabalho feito.

    Vale para os três desfechos, cancelado incluído. Cancelar é erro nosso de
    cadastro, e saber quem descobriu — e como — é o que impede o mesmo erro
    de entrar de novo pela mesma porta.

    Obrigatória NO SCHEMA, e não só na tela: regra que mora só no front vira
    opcional no dia em que alguém chamar a API de outro lugar.
    """

    status: str
    motivo_desfecho_id: int | None = None
    observacoes: str | None = None
    tarefa: TarefaDeFinalizacao


class Reabertura(BaseModel):
    fase: str | None = None
    temperatura: int | None = None


class MudarStatus(BaseModel):
    status: str
    temperatura: int | None = None


class OportunidadeResumo(BaseModel):
    id: UUID
    numero: str
    conta_id: UUID
    conta_razao_social: str
    contato_id: UUID | None
    contato_nome: str | None
    fase: str
    status: str
    fase_desfecho: str | None
    motivo_desfecho: str | None
    valor_mensalidade: Decimal | None
    temperatura: int | None
    previsao_fechamento: date | None
    proxima_acao_em: datetime | None
    proxima_acao_tipo: str | None
    origem_nome: str | None
    finder_conta_id: UUID | None
    finder_razao_social: str | None
    envolvidos: list[Envolvido]
    criado_em: datetime
    atualizado_em: datetime


class OportunidadeDetalhe(OportunidadeResumo):
    descricao: str | None
    observacoes: str | None
    origem_id: int | None
    concorrentes: list[dict]
    # Contagem de tarefas em aberto, para o badge da aba. Vem daqui e não de
    # uma segunda chamada do front porque o modal já carrega o detalhe: o
    # badge precisa estar certo antes de alguém clicar na aba.
    tarefas_abertas: int = 0


class OportunidadeLista(BaseModel):
    total: int
    limit: int
    offset: int
    itens: list[OportunidadeResumo]


class ColunaKanban(BaseModel):
    fase: str
    rotulo: str
    quantidade: int
    ticket_total: Decimal
    itens: list[OportunidadeResumo]
    # A coluna Finalizado existe para dar visibilidade do que fechou, não para
    # operar: ela não recebe cartão arrastado (soltar ali abre o modal de
    # desfecho) e seus cartões não têm seletor de fase.
    somente_leitura: bool = False


class ResumoFunil(BaseModel):
    abertas: int
    ticket_aberto: Decimal
    previsto_no_mes: Decimal
    paradas: int
    ganhas_mes: int
    perdidas_mes: int
    por_fase: list[dict]
    perda_por_fase: list[dict]


# ── SQL compartilhado ────────────────────────────────────────────────
#
# O LATERAL dos envolvidos é agregado por linha da página, não por
# oportunidade do banco — mesma escolha do vendedor derivado em contas.

_SELECT_BASE = """
    SELECT o.id, o.numero, o.conta_id, c.razao_social AS conta_razao_social,
           o.contato_id, ct.nome AS contato_nome,
           o.fase, o.status, o.fase_desfecho, m.nome AS motivo_desfecho,
           o.valor_mensalidade, o.temperatura, o.previsao_fechamento,
           o.proxima_acao_em, o.proxima_acao_tipo,
           o.origem_id, org.nome AS origem_nome,
           o.finder_conta_id, f.razao_social AS finder_razao_social,
           o.descricao, o.observacoes, o.criado_em, o.atualizado_em,
           env.envolvidos
      FROM oportunidades o
      JOIN contas c            ON c.id = o.conta_id
      LEFT JOIN contatos ct    ON ct.id = o.contato_id
      LEFT JOIN motivos_desfecho m ON m.id = o.motivo_desfecho_id
      LEFT JOIN origens org    ON org.id = o.origem_id
      LEFT JOIN contas f       ON f.id = o.finder_conta_id
      LEFT JOIN LATERAL (
          SELECT COALESCE(
              json_agg(json_build_object(
                  'usuario_id', u.id, 'nome', u.nome, 'papel', oe.papel
              ) ORDER BY oe.papel, u.nome),
              '[]'::json
          ) AS envolvidos
          FROM oportunidade_envolvidos oe
          JOIN usuarios u ON u.id = oe.usuario_id
          WHERE oe.oportunidade_id = o.id
      ) env ON TRUE
"""


def _linha(row) -> dict:
    import json

    d = dict(row)
    env = d.pop("envolvidos", None)
    d["envolvidos"] = json.loads(env) if isinstance(env, str) else (env or [])
    return d


async def _estado_atual(conn, oportunidade_id: UUID) -> tuple[dict, Estado]:
    row = await conn.fetchrow(
        """
        SELECT fase, status, fase_desfecho, motivo_desfecho_id, temperatura
          FROM oportunidades WHERE id = $1
        """,
        oportunidade_id,
    )
    if not row:
        raise HTTPException(404, "Oportunidade não encontrada.")
    return dict(row), Estado(**dict(row))


async def _aplicar(conn, oportunidade_id: UUID, novo: Estado, usuario_id,
                   anterior: Estado, tipo_evento: str) -> None:
    """
    Grava o novo estado e registra os eventos correspondentes — sempre juntos.

    Um evento por dimensão que mudou: quem quiser medir tempo por fase lê os
    eventos de 'fase'; quem quiser medir suspensões lê os de 'status'.
    """
    await conn.execute(
        """
        UPDATE oportunidades
           SET fase = $2, status = $3, fase_desfecho = $4,
               motivo_desfecho_id = $5, temperatura = $6, atualizado_em = NOW()
         WHERE id = $1
        """,
        oportunidade_id, novo.fase, novo.status, novo.fase_desfecho,
        novo.motivo_desfecho_id, novo.temperatura,
    )
    eventos = []
    if novo.fase != anterior.fase:
        eventos.append(("fase", anterior.fase, novo.fase))
    if novo.status != anterior.status:
        eventos.append(("status", anterior.status, novo.status))
    # Reabrir muda fase E status, entao os dois eventos precisam existir
    # com o tipo certo: sao eles que sustentam tempo por fase e
    # conquistadas/perdidas. O marcador de reabertura vem ALEM deles,
    # nunca no lugar deles.
    if tipo_evento == "reabertura":
        eventos.append(("reabertura", anterior.status, novo.status))

    for tipo, de, para in eventos:
        await conn.execute(
            """
            INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para, usuario_id)
            VALUES ($1, $2, $3, $4, $5)
            """,
            oportunidade_id, tipo,
            de, para, usuario_id,
        )


async def _marcar_finder(conn, finder_conta_id: UUID | None) -> None:
    """
    A conta usada como indicadora vira finder automaticamente.

    Exigir que alguém marque a caixinha antes criaria um passo extra que o
    usuário só descobre quando o picker não encontra a empresa.
    """
    if finder_conta_id is not None:
        await conn.execute(
            "UPDATE contas SET eh_finder = TRUE WHERE id = $1 AND NOT eh_finder",
            finder_conta_id,
        )


async def _validar_prospeccao(conn, conta_id: UUID | None) -> None:
    """
    Recusa abrir negócio novo em conta marcada como "não prospectar".

    Vale só para a CRIAÇÃO e para a troca de conta de uma oportunidade —
    nunca para editar uma que já existe. Bloquear a edição prenderia as
    oportunidades que já estavam abertas quando a conta foi marcada: quem
    quisesse encerrá-las direito não conseguiria nem mexer nelas.

    O finder também não passa por aqui de propósito. Indicar é outro eixo:
    um cliente da MedSeg pode perfeitamente nos indicar alguém.

    O 422 sai no formato estruturado (dict em `detail`), e não como string,
    porque o front usa `detail.mensagem` e o `conta_id` para oferecer o
    caminho de saída — pedir a liberação a um gestor.
    """
    if conta_id is None:
        return
    row = await conn.fetchrow(
        """
        SELECT razao_social, nao_prospectar, nao_prospectar_motivo
          FROM contas WHERE id = $1
        """,
        conta_id,
    )
    if row is None or not row["nao_prospectar"]:
        return

    motivo = row["nao_prospectar_motivo"] or "sem motivo registrado"
    raise HTTPException(
        422,
        detail={
            "erro": "conta_nao_prospectar",
            "mensagem": (
                f"{row['razao_social']} está bloqueada para prospecção "
                f"({motivo}). Um gestor pode liberar pela tela de Contas."
            ),
            "conta_id": str(conta_id),
            "razao_social": row["razao_social"],
            "motivo": motivo,
        },
    )


async def _validar_referencias(conn, conta_id, contato_id, origem_id,
                               finder_conta_id, motivo_id=None) -> None:
    if conta_id is not None:
        if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
            raise HTTPException(422, "conta_id não existe.")
    if contato_id is not None:
        if not await conn.fetchval("SELECT 1 FROM contatos WHERE id = $1", contato_id):
            raise HTTPException(422, "contato_id não existe.")
        if conta_id is not None:
            vinculado = await conn.fetchval(
                """
                SELECT 1 FROM conta_contatos
                 WHERE conta_id = $1 AND contato_id = $2 AND ativo
                """,
                conta_id, contato_id,
            )
            if not vinculado:
                raise HTTPException(
                    422, "O contato precisa estar vinculado à conta da oportunidade."
                )
    if origem_id is not None:
        if not await conn.fetchval("SELECT 1 FROM origens WHERE id = $1", origem_id):
            raise HTTPException(422, "origem_id não existe.")
    if finder_conta_id is not None:
        if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", finder_conta_id):
            raise HTTPException(422, "finder_conta_id não existe.")
        if conta_id is not None and finder_conta_id == conta_id:
            raise HTTPException(422, "Uma conta não pode indicar a si mesma.")
    if motivo_id is not None:
        if not await conn.fetchval(
            "SELECT 1 FROM motivos_desfecho WHERE id = $1", motivo_id
        ):
            raise HTTPException(422, "motivo_desfecho_id não existe.")


async def _substituir_envolvidos(conn, oportunidade_id: UUID,
                                 envolvidos: list[EnvolvidoIn]) -> None:
    ids = [e.usuario_id for e in envolvidos]
    if ids:
        achados = await conn.fetchval(
            "SELECT count(*) FROM usuarios WHERE id = ANY($1::uuid[])", ids
        )
        if achados != len(set(ids)):
            raise HTTPException(422, "Algum usuário informado não existe.")

    await conn.execute(
        "DELETE FROM oportunidade_envolvidos WHERE oportunidade_id = $1", oportunidade_id
    )
    for e in envolvidos:
        await conn.execute(
            """
            INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            oportunidade_id, e.usuario_id, e.papel,
        )


async def _substituir_concorrentes(conn, oportunidade_id: UUID, ids: list[int]) -> None:
    if ids:
        achados = await conn.fetchval(
            "SELECT count(*) FROM concorrentes WHERE id = ANY($1::int[])", ids
        )
        if achados != len(set(ids)):
            raise HTTPException(422, "Algum concorrente informado não existe.")

    await conn.execute(
        "DELETE FROM oportunidade_concorrentes WHERE oportunidade_id = $1", oportunidade_id
    )
    for cid in set(ids):
        await conn.execute(
            """
            INSERT INTO oportunidade_concorrentes (oportunidade_id, concorrente_id)
            VALUES ($1, $2)
            """,
            oportunidade_id, cid,
        )


async def _detalhe(conn, oportunidade_id: UUID) -> dict:
    row = await conn.fetchrow(f"{_SELECT_BASE} WHERE o.id = $1", oportunidade_id)
    if not row:
        raise HTTPException(404, "Oportunidade não encontrada.")
    d = _linha(row)
    concorrentes = await conn.fetch(
        """
        SELECT c.id, c.nome
          FROM oportunidade_concorrentes oc
          JOIN concorrentes c ON c.id = oc.concorrente_id
         WHERE oc.oportunidade_id = $1
         ORDER BY c.nome
        """,
        oportunidade_id,
    )
    d["concorrentes"] = [dict(c) for c in concorrentes]

    # Índice parcial idx_tarefas_abertas_por_opp cobre exatamente este WHERE.
    d["tarefas_abertas"] = await conn.fetchval(
        """
        SELECT count(*) FROM tarefas
         WHERE oportunidade_id = $1
           AND concluida_em IS NULL
           AND cancelada_em IS NULL
        """,
        oportunidade_id,
    ) or 0
    return d


# ── Filtros do funil ─────────────────────────────────────────────────
#
# UM conjunto de filtros para as quatro leituras da tela (resumo, kanban,
# coluna do kanban e tabela). Declarado uma vez, como dependência: antes cada
# rota repetia sete parâmetros na assinatura, e bastava esquecer um em uma
# delas para o KPI do topo contar uma coisa e a lista embaixo mostrar outra.
#
# Espelha o que o módulo de Relatórios oferece para oportunidades — situação,
# fase, temperatura, datas, mensalidade, equipe, origem, parceiro, vertical —
# mas com SQL fixo e parâmetro posicional. Nada vindo do cliente vira SQL: a
# data escolhida é chave de dicionário, não nome de coluna.

# Data de referência do filtro de período -> expressão SQL e se é timestamptz.
# O desfecho vem da trilha de eventos, como no Relatórios: `atualizado_em`
# muda a cada edição e diria "fechou hoje" para quem só corrigiu o telefone.
_EXPR_DESFECHO = (
    "(SELECT max(e_d.criado_em) FROM oportunidade_eventos e_d"
    " WHERE e_d.oportunidade_id = o.id AND e_d.tipo = 'status'"
    " AND e_d.para IN ('conquistado','perdido','cancelado'))"
)
DATAS_FILTRO: dict[str, tuple[str, bool]] = {
    "criacao": ("o.criado_em", True),
    "previsao": ("o.previsao_fechamento", False),
    "desfecho": (_EXPR_DESFECHO, True),
    "atualizacao": ("o.atualizado_em", True),
}
FUSO = "America/Sao_Paulo"


@dataclass(frozen=True)
class FiltrosFunil:
    q: str | None = None
    fase: tuple[str, ...] | None = None
    status: tuple[str, ...] | None = None
    conta_id: UUID | None = None
    envolvido_id: UUID | None = None
    papel: str | None = None
    finder_conta_id: UUID | None = None
    origem_id: int | None = None
    vertical_id: int | None = None
    veio_de_parceiro: bool | None = None
    temperatura_min: int | None = None
    temperatura_max: int | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    previsao_ate: date | None = None
    data_campo: str | None = None
    data_de: date | None = None
    data_ate: date | None = None

    @property
    def tem_periodo(self) -> bool:
        return self.data_campo is not None and (
            self.data_de is not None or self.data_ate is not None
        )

    def montar(self, *, fase=None, status=None, apenas_abertas=False,
               ignorar_fase=False, ignorar_status=False):
        """
        WHERE + parâmetros. `fase`/`status` explícitos SUBSTITUEM os do
        filtro — é como o kanban pede uma coluna só, já intersectada.
        """
        return _montar_filtros(
            self.q,
            None if ignorar_fase else (fase if fase is not None else self.fase),
            None if ignorar_status else (status if status is not None else self.status),
            self.conta_id, self.envolvido_id, self.finder_conta_id,
            self.origem_id, self.temperatura_min, self.previsao_ate,
            apenas_abertas,
            temperatura_max=self.temperatura_max,
            valor_min=self.valor_min, valor_max=self.valor_max,
            papel=self.papel, vertical_id=self.vertical_id,
            veio_de_parceiro=self.veio_de_parceiro,
            data_campo=self.data_campo, data_de=self.data_de, data_ate=self.data_ate,
        )

    # ── Recorte das colunas do kanban ──
    #
    # O kanban tem colunas FIXAS por fase e por natureza: as cinco abertas só
    # mostram ativa/suspensa, a Finalizado só os três desfechos. Filtro de
    # situação e de fase escolhe QUAIS colunas existem e o que cada uma
    # mostra; coluna que o filtro exclui inteira não é consultada.

    def status_da_coluna(self, fase: str) -> tuple[str, ...] | None:
        """Situações que a coluna mostra; () = a coluna sai do recorte."""
        naturais = regras.STATUS_DESFECHO if fase == "finalizado" else regras.STATUS_ABERTOS
        if not self.status:
            return None
        return tuple(s for s in naturais if s in self.status)

    def coluna_visivel(self, fase: str) -> bool:
        if self.fase and fase not in self.fase:
            return False
        return self.status_da_coluna(fase) != ()


def filtros_funil(
    q: str | None = Query(None, max_length=200),
    fase: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    conta_id: UUID | None = None,
    envolvido_id: UUID | None = None,
    papel: str | None = None,
    finder_conta_id: UUID | None = None,
    origem_id: int | None = None,
    vertical_id: int | None = None,
    veio_de_parceiro: bool | None = None,
    temperatura_min: int | None = Query(None, ge=0, le=90),
    temperatura_max: int | None = Query(None, ge=0, le=90),
    valor_min: Decimal | None = Query(None, ge=0),
    valor_max: Decimal | None = Query(None, ge=0),
    previsao_ate: date | None = None,
    data_campo: str | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
) -> FiltrosFunil:
    """Lê e valida os filtros do funil. Erro é 422 com mensagem em português."""
    for v in fase or []:
        if v not in regras.FASES:
            raise HTTPException(422, f"Fase inválida: '{v}'.")
    for v in status or []:
        if v not in regras.STATUS:
            raise HTTPException(422, f"Situação inválida: '{v}'.")
    if papel is not None and papel not in PAPEIS:
        raise HTTPException(422, f"Papel inválido: '{papel}'. Use: {', '.join(PAPEIS)}.")
    if data_campo is not None and data_campo not in DATAS_FILTRO:
        raise HTTPException(
            422, f"Data de referência inválida: '{data_campo}'. Use: {', '.join(DATAS_FILTRO)}."
        )
    # Período sem data de referência: vale a criação, que é a leitura mais
    # comum ("o que entrou no funil em setembro").
    if data_campo is None and (data_de is not None or data_ate is not None):
        data_campo = "criacao"
    for nome, mn, mx in (
        ("Temperatura", temperatura_min, temperatura_max),
        ("Mensalidade", valor_min, valor_max),
        ("Período", data_de, data_ate),
    ):
        if mn is not None and mx is not None and mn > mx:
            raise HTTPException(422, f"{nome}: o início da faixa é maior que o fim.")

    return FiltrosFunil(
        q=q or None,
        fase=tuple(dict.fromkeys(fase)) if fase else None,
        status=tuple(dict.fromkeys(status)) if status else None,
        conta_id=conta_id, envolvido_id=envolvido_id, papel=papel,
        finder_conta_id=finder_conta_id, origem_id=origem_id,
        vertical_id=vertical_id, veio_de_parceiro=veio_de_parceiro,
        temperatura_min=temperatura_min, temperatura_max=temperatura_max,
        valor_min=valor_min, valor_max=valor_max, previsao_ate=previsao_ate,
        data_campo=data_campo, data_de=data_de, data_ate=data_ate,
    )


# ── Leitura ──────────────────────────────────────────────────────────

@router.get("/resumo", response_model=ResumoFunil)
async def resumo(
    dias_parada: int = Query(14, ge=1, le=365),
    f: FiltrosFunil = Depends(filtros_funil),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    KPIs do topo da tela e o corte por fase que alimenta a visão de funil.

    Cada número tem filtro equivalente na listagem — é o que permite o
    drilldown.

    Aceita EXATAMENTE os mesmos filtros do kanban e da tabela, fase e
    situação inclusive. Sem isso, trocar de visão com um filtro ativo
    mostrava um funil global ao lado de uma lista filtrada — dois números
    diferentes para a mesma pergunta na mesma tela. Com fase filtrada, as
    outras faixas do funil saem zeradas: é o retrato fiel do recorte.
    Chamado sem parâmetro nenhum, o resultado é idêntico ao de antes.

    'paradas' usa a data do último EVENTO, não `atualizado_em`: corrigir um
    telefone não significa que a negociação andou.
    """
    # `apenas_abertas=False` aqui: os KPIs de ganhas/perdidas do mês precisam
    # enxergar as finalizadas. O recorte por status é feito com FILTER dentro
    # de cada agregado.
    where, params = f.montar()
    clausula = f"WHERE {' AND '.join(where)}" if where else ""

    # O JOIN com contas é obrigatório mesmo sem busca textual: `_montar_filtros`
    # referencia `c.razao_social` no filtro `q`, e manter uma só forma da
    # consulta evita que o SQL divirja conforme o filtro em uso.
    row = await conn.fetchrow(
        f"""
        SELECT
            count(*) FILTER (WHERE o.status IN ('ativa','suspensa'))        AS abertas,
            COALESCE(sum(o.valor_mensalidade) FILTER (
                WHERE o.status = 'ativa'), 0)                                AS ticket_aberto,
            COALESCE(sum(o.valor_mensalidade) FILTER (
                WHERE o.status = 'ativa'
                  AND date_trunc('month', o.previsao_fechamento)
                      = date_trunc('month', CURRENT_DATE)), 0)              AS previsto_no_mes,
            count(*) FILTER (
                WHERE o.status = 'conquistado'
                  AND date_trunc('month', o.atualizado_em)
                      = date_trunc('month', CURRENT_DATE))                  AS ganhas_mes,
            count(*) FILTER (
                WHERE o.status = 'perdido'
                  AND date_trunc('month', o.atualizado_em)
                      = date_trunc('month', CURRENT_DATE))                  AS perdidas_mes
        FROM oportunidades o
        JOIN contas c ON c.id = o.conta_id
        {clausula}
        """,
        *params,
    )

    paradas = await conn.fetchval(
        f"""
        SELECT count(*)
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
        {clausula + ' AND ' if clausula else 'WHERE '} o.status IN ('ativa','suspensa')
           AND COALESCE(
                 (SELECT max(e.criado_em) FROM oportunidade_eventos e
                   WHERE e.oportunidade_id = o.id),
                 o.criado_em
               ) < NOW() - (${len(params) + 1} || ' days')::interval
        """,
        *params, str(dias_parada),
    )

    por_fase = await conn.fetch(
        f"""
        SELECT o.fase,
               count(*)                                    AS quantidade,
               COALESCE(sum(o.valor_mensalidade), 0)       AS ticket
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
        {clausula + ' AND ' if clausula else 'WHERE '} o.status IN ('ativa','suspensa')
         GROUP BY o.fase
        """,
        *params,
    )

    # Só 'perdido' entra: 'cancelado' é erro de CRM e distorceria a leitura
    # de onde o funil realmente perde negócio.
    perda_por_fase = await conn.fetch(
        f"""
        SELECT o.fase_desfecho AS fase, count(*) AS quantidade
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
        {clausula + ' AND ' if clausula else 'WHERE '} o.status = 'perdido'
           AND o.fase_desfecho IS NOT NULL
         GROUP BY o.fase_desfecho
        """,
        *params,
    )

    mapa_fase = {r["fase"]: r for r in por_fase}
    mapa_perda = {r["fase"]: r["quantidade"] for r in perda_por_fase}

    return {
        **dict(row),
        "paradas": paradas or 0,
        "por_fase": [
            {
                "fase": f,
                "rotulo": regras.ROTULOS_FASE[f],
                "quantidade": mapa_fase.get(f, {}).get("quantidade", 0),
                "ticket": mapa_fase.get(f, {}).get("ticket", 0),
            }
            for f in regras.FASES_ABERTAS
        ],
        "perda_por_fase": [
            {"fase": f, "rotulo": regras.ROTULOS_FASE[f], "quantidade": mapa_perda.get(f, 0)}
            for f in regras.FASES_ABERTAS
        ],
    }


# Mínimo de dígitos para o termo ser tratado TAMBÉM como CNPJ. Abaixo disso a
# busca por documento vira ruído: "5" casaria com quase toda a base, e o
# resultado ficaria pior do que se o CNPJ não fosse consultado.
_MIN_DIGITOS_CNPJ = 3

# Teto de cartões por página de coluna do kanban. O front pede de 100 em 100;
# o teto só impede alguém de pedir a tabela inteira numa request.
POR_COLUNA_MAX = 500


def _montar_filtros(
    q, fase, status, conta_id, envolvido_id, finder_conta_id, origem_id,
    temperatura_min, previsao_ate, apenas_abertas,
    *,
    temperatura_max=None, valor_min=None, valor_max=None, papel=None,
    vertical_id=None, veio_de_parceiro=None,
    data_campo=None, data_de=None, data_ate=None,
) -> tuple[list[str], list]:
    where: list[str] = []
    params: list = []

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if q:
        # Uma caixa de busca só: quem procura no funil não sabe (nem deveria
        # precisar saber) se o que tem na mão é o número da oportunidade, a
        # razão social, o nome de quem atendeu ou o CNPJ do cadastro. O termo
        # entra por todos os caminhos e o primeiro que casar responde.
        #
        # O CNPJ é comparado por DÍGITOS, não pelo texto digitado: a coluna é
        # CHAR(14) sem pontuação, então "11.222.333/0001-81" e "11222333"
        # precisam achar a mesma conta.
        termo = q.strip()
        params.append(f"%{termo}%")
        i_texto = len(params)

        digitos = cnpj_svc.normalizar(termo)
        params.append(f"%{digitos}%" if len(digitos) >= _MIN_DIGITOS_CNPJ else None)
        i_cnpj = len(params)

        where.append(
            f"(o.numero ILIKE ${i_texto}"
            f" OR c.razao_social ILIKE ${i_texto}"
            f" OR c.nome_fantasia ILIKE ${i_texto}"
            f" OR o.descricao ILIKE ${i_texto}"
            f" OR (${i_cnpj}::text IS NOT NULL AND c.cnpj LIKE ${i_cnpj})"
            # Contato da própria oportunidade: é por ele que o vendedor lembra
            # da negociação ("aquela da Maria").
            f" OR EXISTS (SELECT 1 FROM contatos ct_o"
            f" WHERE ct_o.id = o.contato_id AND ct_o.nome ILIKE ${i_texto})"
            # E qualquer contato ativo da conta: oportunidade sem contato
            # preenchido ainda tem que ser encontrada pelo nome de quem
            # atende naquela empresa.
            f" OR EXISTS (SELECT 1 FROM conta_contatos cc_q"
            f" JOIN contatos ct_q ON ct_q.id = cc_q.contato_id"
            f" WHERE cc_q.conta_id = o.conta_id AND cc_q.ativo"
            f" AND ct_q.nome ILIKE ${i_texto}))"
        )
    if fase:
        add("o.fase = ANY(${n}::text[])", list(fase))
    if status:
        add("o.status = ANY(${n}::text[])", list(status))
    if conta_id is not None:
        add("o.conta_id = ${n}", conta_id)
    if envolvido_id is not None and papel is not None:
        params.append(envolvido_id)
        params.append(papel)
        where.append(
            "EXISTS (SELECT 1 FROM oportunidade_envolvidos oe"
            f" WHERE oe.oportunidade_id = o.id AND oe.usuario_id = ${len(params) - 1}"
            f" AND oe.papel = ${len(params)})"
        )
    elif envolvido_id is not None:
        add(
            "EXISTS (SELECT 1 FROM oportunidade_envolvidos oe"
            " WHERE oe.oportunidade_id = o.id AND oe.usuario_id = ${n})",
            envolvido_id,
        )
    elif papel is not None:
        # Papel sem pessoa: "tem SDR nesta oportunidade".
        add(
            "EXISTS (SELECT 1 FROM oportunidade_envolvidos oe"
            " WHERE oe.oportunidade_id = o.id AND oe.papel = ${n})",
            papel,
        )
    if finder_conta_id is not None:
        add("o.finder_conta_id = ${n}", finder_conta_id)
    if origem_id is not None:
        add("o.origem_id = ${n}", origem_id)
    if vertical_id is not None:
        add("c.vertical_id = ${n}", vertical_id)
    if veio_de_parceiro is True:
        where.append("o.finder_conta_id IS NOT NULL")
    elif veio_de_parceiro is False:
        where.append("o.finder_conta_id IS NULL")
    if temperatura_min is not None:
        add("o.temperatura >= ${n}", temperatura_min)
    if temperatura_max is not None:
        add("o.temperatura <= ${n}", temperatura_max)
    if valor_min is not None:
        add("o.valor_mensalidade >= ${n}", valor_min)
    if valor_max is not None:
        add("o.valor_mensalidade <= ${n}", valor_max)
    if previsao_ate is not None:
        add("o.previsao_fechamento <= ${n}", previsao_ate)
    if data_campo is not None and (data_de is not None or data_ate is not None):
        expr, com_hora = DATAS_FILTRO[data_campo]
        # Timestamp: faixa semiaberta no fuso de São Paulo — "até 30/09"
        # inclui o dia 30 inteiro, e a comparação direta usa o índice.
        if data_de is not None:
            if com_hora:
                add(f"{expr} >= (${{n}}::date)::timestamp AT TIME ZONE '{FUSO}'", data_de)
            else:
                add(f"{expr} >= ${{n}}", data_de)
        if data_ate is not None:
            if com_hora:
                add(f"{expr} < (${{n}}::date + 1)::timestamp AT TIME ZONE '{FUSO}'", data_ate)
            else:
                add(f"{expr} <= ${{n}}", data_ate)
    if apenas_abertas:
        where.append("o.status IN ('ativa','suspensa')")

    return where, params


@router.get("/kanban", response_model=list[ColunaKanban])
async def kanban(
    por_coluna: int = Query(100, ge=1, le=POR_COLUNA_MAX),
    f: FiltrosFunil = Depends(filtros_funil),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    As 5 colunas abertas do funil mais a coluna Finalizado, cada uma com
    contagem, ticket somado e os primeiros N cartões.

    A contagem e o ticket são do total da coluna, não dos cartões devolvidos:
    o topo precisa mostrar o pipeline inteiro mesmo quando a coluna tem mais
    itens do que cabe na tela. O resto da coluna vem, página a página, por
    GET /kanban/coluna — nenhum cartão fica inalcançável.

    Com filtro de fase ou de situação, só vêm as colunas que o recorte
    alcança: filtrar "perdidas" devolve só a Finalizado, filtrar "Lead"
    devolve só a Lead. Cinco colunas vazias ao lado da única cheia seriam
    ruído ocupando a largura que o cartão precisa.

    A coluna Finalizado é diferente das outras em três pontos, e cada um tem
    motivo:

      * Só o mês corrente — A MENOS que haja filtro de período, que então
        manda. O funil aberto é um estoque e cresce devagar; o finalizado é
        um fluxo e cresce para sempre. Sem recorte a coluna viraria um
        arquivo morto que ninguém lê.
      * O ticket somado conta só as conquistadas. Somar mensalidade de
        perdida com ganha produz um número que não significa nada.
      * `somente_leitura=True`. Fechar exige status e motivo, então o front
        não deixa soltar cartão ali — abre o modal de desfecho.
    """
    colunas = [
        await _coluna_aberta(conn, fase, f, por_coluna, 0)
        for fase in regras.FASES_ABERTAS
        if f.coluna_visivel(fase)
    ]
    if f.coluna_visivel("finalizado"):
        colunas.append(await _coluna_finalizado(conn, f, por_coluna, 0))
    return colunas


@router.get("/kanban/coluna", response_model=ColunaKanban)
async def kanban_coluna(
    fase: str = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=POR_COLUNA_MAX),
    f: FiltrosFunil = Depends(filtros_funil),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Uma coluna do kanban, a partir de `offset`. É o "carregar mais".

    Existe porque a coluna com 1.124 suspects mostrava os primeiros cartões e
    um "+1074 não exibidas" sem caminho nenhum até eles. Cartão que existe e
    não pode ser alcançado é dado perdido para quem opera a tela.

    Mesmos filtros e MESMA ordenação do /kanban — com desempate por id —, para
    que a página N+1 continue exatamente de onde a N parou, sem repetir nem
    pular cartão. O `fase` aqui é a COLUNA; o filtro de fase da tela não se
    aplica (a coluna pedida já está dentro dele).
    """
    if fase != "finalizado" and fase not in regras.FASES_ABERTAS:
        raise HTTPException(
            422,
            f"Fase inválida: '{fase}'. Use: "
            f"{', '.join([*regras.FASES_ABERTAS, 'finalizado'])}.",
        )
    if fase == "finalizado":
        return await _coluna_finalizado(conn, f, limit, offset)
    return await _coluna_aberta(conn, fase, f, limit, offset)


def _coluna_vazia(fase: str) -> dict:
    return {
        "fase": fase,
        "rotulo": regras.ROTULOS_FASE[fase],
        "quantidade": 0,
        "ticket_total": 0,
        "itens": [],
        "somente_leitura": fase == "finalizado",
    }


async def _coluna_aberta(conn, fase, f: FiltrosFunil, limit, offset) -> dict:
    """Uma das cinco colunas abertas: totais da coluna inteira + uma página."""
    status_col = f.status_da_coluna(fase)
    if status_col == ():
        return _coluna_vazia(fase)
    where, params = f.montar(fase=[fase], status=status_col, apenas_abertas=True,
                             ignorar_status=status_col is None)
    clausula = f"WHERE {' AND '.join(where)}"

    totais = await conn.fetchrow(
        f"""
        SELECT count(*) AS quantidade,
               COALESCE(sum(o.valor_mensalidade), 0) AS ticket_total
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
          {clausula}
        """,
        *params,
    )
    rows = await conn.fetch(
        f"""
        {_SELECT_BASE}
        {clausula}
        ORDER BY o.temperatura DESC NULLS LAST, o.previsao_fechamento NULLS LAST,
                 o.criado_em, o.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    return {
        "fase": fase,
        "rotulo": regras.ROTULOS_FASE[fase],
        "quantidade": totais["quantidade"],
        "ticket_total": totais["ticket_total"],
        "itens": [_linha(r) for r in rows],
    }


async def _coluna_finalizado(conn, f: FiltrosFunil, limit, offset) -> dict:
    """
    A sexta coluna: o que fechou no mês corrente, em qualquer dos três
    desfechos. Só leitura.

    O recorte é por `atualizado_em` e não por `criado_em`: o que interessa é
    quando fechou, não quando nasceu. Uma oportunidade aberta em maio e ganha
    em agosto pertence a agosto. Com filtro de período ativo, o mês corrente
    sai e vale o período escolhido.
    """
    status_col = f.status_da_coluna("finalizado")
    if status_col == ():
        return _coluna_vazia("finalizado")
    where, params = f.montar(status=status_col, ignorar_fase=True,
                             ignorar_status=status_col is None)
    where = where + ["o.fase = 'finalizado'"]
    if not f.tem_periodo:
        where.append(
            "date_trunc('month', o.atualizado_em) = date_trunc('month', CURRENT_DATE)"
        )
    clausula = f"WHERE {' AND '.join(where)}"

    totais = await conn.fetchrow(
        f"""
        SELECT count(*) AS quantidade,
               COALESCE(sum(o.valor_mensalidade) FILTER (
                   WHERE o.status = 'conquistado'), 0) AS ticket_total
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
          {clausula}
        """,
        *params,
    )

    rows = await conn.fetch(
        f"""
        {_SELECT_BASE}
        {clausula}
        ORDER BY o.atualizado_em DESC, o.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )

    return {
        "fase": "finalizado",
        "rotulo": regras.ROTULOS_FASE["finalizado"],
        "quantidade": totais["quantidade"],
        "ticket_total": totais["ticket_total"],
        "itens": [_linha(r) for r in rows],
        "somente_leitura": True,
    }


@router.get("", response_model=OportunidadeLista)
async def listar(
    f: FiltrosFunil = Depends(filtros_funil),
    apenas_abertas: bool = False,
    ordenar_por: str = Query("criado_em"),
    desc: bool = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if ordenar_por not in ORDENACOES:
        raise HTTPException(422, f"ordenar_por inválido. Use: {sorted(ORDENACOES)}")

    where, params = f.montar(apenas_abertas=apenas_abertas)
    clausula = f"WHERE {' AND '.join(where)}" if where else ""

    total = await conn.fetchval(
        f"SELECT count(*) FROM oportunidades o JOIN contas c ON c.id = o.conta_id {clausula}",
        *params,
    )
    rows = await conn.fetch(
        f"""
        {_SELECT_BASE}
        {clausula}
        ORDER BY {ORDENACOES[ordenar_por]} {'DESC' if desc else 'ASC'} NULLS LAST, o.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "itens": [_linha(r) for r in rows],
    }


@router.get("/{oportunidade_id}", response_model=OportunidadeDetalhe)
async def obter(
    oportunidade_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    return await _detalhe(conn, oportunidade_id)


async def inserir_oportunidade(
    conn,
    *,
    conta_id: UUID,
    fase: str,
    temperatura: int,
    criado_por,
    contato_id: UUID | None = None,
    valor_mensalidade: Decimal | None = None,
    previsao_fechamento: date | None = None,
    descricao: str | None = None,
    observacoes: str | None = None,
    origem_id: int | None = None,
    finder_conta_id: UUID | None = None,
    proxima_acao_em: datetime | None = None,
    proxima_acao_tipo: str | None = None,
    envolvidos: list[EnvolvidoIn] | None = None,
    concorrentes: list[int] | None = None,
) -> UUID:
    """
    O INSERT da oportunidade, com envolvidos, concorrentes, finder e o
    evento de criacao. Chamar DENTRO de uma transacao.

    Existe separado do POST porque a Prospeccao (routers/crm_prospeccao.py)
    abre oportunidades em lote. Duas copias do mesmo INSERT divergem na
    primeira coluna nova -- e a que divergir vai ser a que ninguem esta
    olhando. Mesmo raciocinio de `inserir_tarefa_concluida`.

    Validacao de referencias e de prospeccao NAO mora aqui: cada chamador
    decide o que checar e com qual mensagem.
    """
    # Numeração gerada dentro do INSERT: ler a sequence antes abriria
    # janela para duas requisições pegarem o mesmo número.
    novo_id = await conn.fetchval(
        """
        INSERT INTO oportunidades (
            numero, conta_id, contato_id, fase, status, temperatura,
            valor_mensalidade, previsao_fechamento, descricao, observacoes,
            origem_id, finder_conta_id, proxima_acao_em, proxima_acao_tipo,
            criado_por
        ) VALUES (
            'OPP-' || EXTRACT(YEAR FROM NOW())::int || '-'
                   || lpad(nextval('oportunidade_numero_seq')::text, 5, '0'),
            $1, $2, $3, 'ativa', $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        RETURNING id
        """,
        conta_id, contato_id, fase, temperatura,
        valor_mensalidade, previsao_fechamento,
        descricao, observacoes, origem_id,
        finder_conta_id, proxima_acao_em,
        proxima_acao_tipo, criado_por,
    )
    await _substituir_envolvidos(conn, novo_id, envolvidos or [])
    await _substituir_concorrentes(conn, novo_id, concorrentes or [])
    await _marcar_finder(conn, finder_conta_id)
    await conn.execute(
        """
        INSERT INTO oportunidade_eventos (oportunidade_id, tipo, para, usuario_id)
        VALUES ($1, 'criacao', $2, $3)
        """,
        novo_id, fase, criado_por,
    )
    return novo_id


# ── Escrita ──────────────────────────────────────────────────────────

@router.post("", response_model=OportunidadeDetalhe, status_code=http.HTTP_201_CREATED)
async def criar(
    payload: OportunidadeCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria a oportunidade. Nasce sempre 'ativa' numa fase aberta — desfecho é
    transição, não estado inicial.
    """
    await _validar_referencias(
        conn, payload.conta_id, payload.contato_id,
        payload.origem_id, payload.finder_conta_id,
    )
    await _validar_prospeccao(conn, payload.conta_id)

    async with conn.transaction():
        novo_id = await inserir_oportunidade(
            conn,
            conta_id=payload.conta_id,
            contato_id=payload.contato_id,
            fase=payload.fase,
            temperatura=payload.temperatura,
            valor_mensalidade=payload.valor_mensalidade,
            previsao_fechamento=payload.previsao_fechamento,
            descricao=payload.descricao,
            observacoes=payload.observacoes,
            origem_id=payload.origem_id,
            finder_conta_id=payload.finder_conta_id,
            proxima_acao_em=payload.proxima_acao_em,
            proxima_acao_tipo=payload.proxima_acao_tipo,
            envolvidos=payload.envolvidos,
            concorrentes=payload.concorrentes,
            criado_por=user["id"],
        )
    return await _detalhe(conn, novo_id)


@router.patch("/{oportunidade_id}", response_model=OportunidadeDetalhe)
async def editar(
    oportunidade_id: UUID,
    payload: OportunidadeEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Campos de conteúdo. Fase e status têm endpoints próprios."""
    atual, estado = await _estado_atual(conn, oportunidade_id)

    dados = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in CAMPOS_EDITAVEIS
    }
    if not dados:
        raise HTTPException(422, "Nenhum campo para atualizar.")

    if "temperatura" in dados and dados["temperatura"] is None and estado.status == "ativa":
        raise HTTPException(422, "Oportunidade ativa precisa de temperatura.")

    conta_id = dados.get("conta_id")
    contato_id = dados.get("contato_id")
    if contato_id is not None and conta_id is None:
        conta_id = await conn.fetchval(
            "SELECT conta_id FROM oportunidades WHERE id = $1", oportunidade_id
        )
    await _validar_referencias(
        conn, conta_id, contato_id, dados.get("origem_id"), dados.get("finder_conta_id"),
    )
    # Só quando a conta está SENDO trocada. `conta_id` acima também é
    # preenchido para validar o vínculo do contato, e usá-lo aqui travaria
    # a edição de qualquer oportunidade já aberta numa conta bloqueada.
    if "conta_id" in dados:
        await _validar_prospeccao(conn, dados["conta_id"])

    async with conn.transaction():
        sets = [f"{col} = ${i}" for i, col in enumerate(dados, start=1)]
        sets.append("atualizado_em = NOW()")
        await conn.execute(
            f"UPDATE oportunidades SET {', '.join(sets)} WHERE id = ${len(dados) + 1}",
            *dados.values(), oportunidade_id,
        )
        await _marcar_finder(conn, dados.get("finder_conta_id"))
    return await _detalhe(conn, oportunidade_id)


@router.patch("/{oportunidade_id}/fase", response_model=OportunidadeDetalhe)
async def mover_fase(
    oportunidade_id: UUID,
    payload: MoverFase,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    O endpoint do drag-and-drop do kanban.

    Soltar na coluna Finalizado é recusado de propósito: o front precisa
    abrir o modal de desfecho e chamar POST /desfecho.
    """
    _, estado = await _estado_atual(conn, oportunidade_id)
    try:
        novo = regras.mover_para_fase(estado, payload.fase)
    except TransicaoInvalida as e:
        raise HTTPException(422, str(e))

    async with conn.transaction():
        await _aplicar(conn, oportunidade_id, novo, user["id"], estado, "fase")
    return await _detalhe(conn, oportunidade_id)


@router.post("/{oportunidade_id}/desfecho", response_model=OportunidadeDetalhe)
async def desfecho(
    oportunidade_id: UUID,
    payload: Desfecho,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Fecha a oportunidade, guarda de qual fase ela saiu e grava o registro do
    fechamento — tudo na mesma transação.

    A tarefa é criada AQUI, e não por uma segunda chamada do navegador, pela
    mesma razão que concluir-e-agendar-a-próxima é uma transação só: se o
    segundo passo falhasse, sobraria oportunidade finalizada sem registro do
    que a fechou, que é exatamente o buraco que a regra existe para tapar.

    Ordem importa: valida o responsável ANTES de abrir a transação. Descobrir
    responsável inativo já com o UPDATE do desfecho aplicado obrigaria a
    desfazer, e o erro que o usuário lê seria sobre a tarefa depois de a
    oportunidade ter parecido fechar.
    """
    _, estado = await _estado_atual(conn, oportunidade_id)
    await _validar_referencias(conn, None, None, None, None, payload.motivo_desfecho_id)

    try:
        novo = regras.finalizar(estado, payload.status, payload.motivo_desfecho_id)
    except TransicaoInvalida as e:
        raise HTTPException(422, str(e))

    # Sem responsável informado, é quem está finalizando — e esse já passou
    # pela autenticação, então não há o que validar.
    if payload.tarefa.responsavel_id is not None:
        await validar_referencias_tarefa(
            conn, oportunidade_id, None, payload.tarefa.responsavel_id
        )

    async with conn.transaction():
        await _aplicar(conn, oportunidade_id, novo, user["id"], estado, "status")
        if payload.observacoes:
            await conn.execute(
                """
                UPDATE oportunidades
                   SET observacoes = COALESCE(observacoes || E'\\n', '') || $2
                 WHERE id = $1
                """,
                oportunidade_id, payload.observacoes,
            )
        await inserir_tarefa_concluida(
            conn, payload.tarefa,
            oportunidade_id=oportunidade_id,
            criado_por=user["id"],
        )
    return await _detalhe(conn, oportunidade_id)


@router.post("/{oportunidade_id}/reabrir", response_model=OportunidadeDetalhe)
async def reabrir(
    oportunidade_id: UUID,
    payload: Reabertura,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Traz de volta ao funil. Sem fase informada, volta de onde saiu."""
    _, estado = await _estado_atual(conn, oportunidade_id)
    try:
        novo = regras.reabrir(estado, payload.fase, payload.temperatura)
    except TransicaoInvalida as e:
        raise HTTPException(422, str(e))

    async with conn.transaction():
        await _aplicar(conn, oportunidade_id, novo, user["id"], estado, "reabertura")
    return await _detalhe(conn, oportunidade_id)


@router.patch("/{oportunidade_id}/status", response_model=OportunidadeDetalhe)
async def mudar_status(
    oportunidade_id: UUID,
    payload: MudarStatus,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Suspende ou reativa. Desfecho e reabertura têm endpoints próprios."""
    _, estado = await _estado_atual(conn, oportunidade_id)
    try:
        novo = regras.mudar_status(estado, payload.status, payload.temperatura)
    except TransicaoInvalida as e:
        raise HTTPException(422, str(e))

    async with conn.transaction():
        await _aplicar(conn, oportunidade_id, novo, user["id"], estado, "status")
    return await _detalhe(conn, oportunidade_id)


@router.put("/{oportunidade_id}/envolvidos", response_model=OportunidadeDetalhe)
async def definir_envolvidos(
    oportunidade_id: UUID,
    envolvidos: list[EnvolvidoIn],
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Substitui a lista inteira. A mesma pessoa pode aparecer com mais de um
    papel — quem prospectou como SDR e tocou como EV é o caso comum.
    """
    await _estado_atual(conn, oportunidade_id)
    async with conn.transaction():
        await _substituir_envolvidos(conn, oportunidade_id, envolvidos)
    return await _detalhe(conn, oportunidade_id)


@router.put("/{oportunidade_id}/concorrentes", response_model=OportunidadeDetalhe)
async def definir_concorrentes(
    oportunidade_id: UUID,
    concorrentes: list[int],
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Substitui a lista inteira."""
    await _estado_atual(conn, oportunidade_id)
    async with conn.transaction():
        await _substituir_concorrentes(conn, oportunidade_id, concorrentes)
    return await _detalhe(conn, oportunidade_id)


@router.get("/{oportunidade_id}/eventos")
async def eventos(
    oportunidade_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Trilha completa da oportunidade, do mais recente para o mais antigo."""
    await _estado_atual(conn, oportunidade_id)
    rows = await conn.fetch(
        """
        SELECT e.tipo, e.de, e.para, e.criado_em, u.nome AS usuario
          FROM oportunidade_eventos e
          LEFT JOIN usuarios u ON u.id = e.usuario_id
         WHERE e.oportunidade_id = $1
         ORDER BY e.criado_em DESC, e.id DESC
        """,
        oportunidade_id,
    )
    return [dict(r) for r in rows]
