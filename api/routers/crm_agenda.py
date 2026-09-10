"""
HIPO — CRM: agenda de reuniões.

A grade semanal do Executivo de Vendas, presa à tarefa que já existia e
espelhada no Google Calendar.

O que este módulo materializa:

  * TODA REUNIÃO É UMA TAREFA. Não existe reunião sem tarefa, e uma tarefa
    nunca vira duas reuniões. Marcar uma reunião cria as duas na MESMA
    transação; colocar na agenda uma tarefa que já existia reaproveita a
    tarefa. É o que faz a reunião herdar de graça a situação derivada, a
    regra "concluir exige agendar a próxima", a produção do mês e o
    drilldown até a conta — tudo já testado desde a Sprint 5.

  * O HORÁRIO E O DONO MORAM NA TAREFA. `inicio` é `tarefas.prazo` e o
    anfitrião é `tarefas.responsavel_id`. Reagendar é um PATCH no prazo;
    trocar quem conduz é um PATCH no responsável. Duas colunas guardando o
    mesmo instante divergiriam no primeiro reagendamento.

  * A GRADE É PADRÃO, NÃO PRISÃO. Slots de 30 minutos, 08:00–11:30 e
    13:00–17:30. Quem agendou pode ajustar para 09:15 se o cliente só pode
    nesse horário: a reunião é desenhada na linha do slot que a contém e
    marcada como fora da grade. O que a API recusa é sábado e domingo, e
    não por rigor de expediente — a grade não tem coluna para eles, e
    registro que a tela esconde é pior que registro recusado.

  * O MESMO ANFITRIÃO NÃO SE DIVIDE. Duas reuniões sobrepostas da mesma
    pessoa são recusadas com 409 nomeando a que já estava lá. Cancelada
    não ocupa; concluída ocupa, porque aconteceu.

  * O GOOGLE É ESPELHO, NÃO FONTE. A sincronização acontece DEPOIS do
    commit, nunca dentro dele, e a falha vira `google_erro` na linha em vez
    de derrubar a criação. Uma indisponibilidade de terceiro não pode
    apagar o registro do que foi combinado com o cliente.

  * Regras em services/agenda.py, como funções puras. Aqui só orquestração.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field, field_validator, model_validator

from database import get_conn
from routers.auth import usuario_atual
from routers.crm_tarefas import (
    ProximaTarefa, TarefaBase, _inserir, _travar_alvo, contar_outras_abertas,
    validar_referencias,
)
from routers.permissions import requer_qualquer_modulo
from services import agenda as regras
from services import google_agenda
from services import tarefa as regras_tarefa
from services.agenda import AgendaInvalida
from services.tarefa import EstadoTarefa, TarefaInvalida
from services.texto import limpar_nome, slugify

router = APIRouter()

# O que um PATCH pode mexer NA REUNIÃO. Horário e anfitrião não estão aqui
# porque não são colunas de `reunioes` — são da tarefa, e o PATCH os
# encaminha para lá. Ver `editar`.
CAMPOS_EDITAVEIS = {
    "duracao_min", "tipo_id", "modalidade", "endereco", "link_video",
    "contato_id", "convidados", "observacoes", "agendado_por",
}

# Campos cuja mudança precisa chegar ao convite que o cliente já recebeu.
# Trocar a duração ou o link e não reenviar deixaria o cliente entrando na
# sala errada na hora errada — e achando que o erro é dele.
CAMPOS_QUE_REFAZEM_O_CONVITE = {
    "duracao_min", "tipo_id", "modalidade", "endereco", "link_video",
    "contato_id", "convidados", "inicio", "anfitriao_id", "titulo",
}


# ── Schemas ──────────────────────────────────────────────────────────

class TipoReuniaoOut(BaseModel):
    id: int
    sigla: str
    nome: str
    slug: str
    ordem: int
    ativo: bool


class TipoReuniaoIn(BaseModel):
    sigla: str = Field(..., min_length=1, max_length=8)
    nome: str = Field(..., min_length=1, max_length=120)
    ordem: int = Field(100, ge=0, le=999)

    @field_validator("sigla")
    @classmethod
    def _sigla(cls, v: str) -> str:
        limpa = (v or "").strip().upper()
        if not limpa.isalnum():
            raise ValueError("A sigla aceita só letras e números, sem espaço.")
        return limpa


class ParticipanteOut(BaseModel):
    usuario_id: UUID
    nome: str | None
    cargo: str | None


class ReuniaoCampos(BaseModel):
    """O que a reunião acrescenta à tarefa. Compartilhado pelas três entradas."""
    tipo_id: int | None = None
    modalidade: str = "online"
    duracao_min: int = Field(regras.DURACAO_PADRAO_MIN, ge=5, le=480)
    endereco: str | None = None
    link_video: str | None = None
    contato_id: UUID | None = None
    convidados: list[str] = Field(default_factory=list)
    observacoes: str | None = None
    # Os NOSSOS que entram além do anfitrião. O anfitrião não entra aqui:
    # ele é o responsável da tarefa. Ver o comentário da tabela.
    participantes: list[UUID] = Field(default_factory=list)
    # De quem é o CRÉDITO do agendamento. Em branco, é quem está criando —
    # que é o caso quase sempre. O campo existe para o dia em que não é: o
    # SDR marcou por telefone e o ADM lançou, e o número do mês precisa ir
    # para quem marcou. `criado_por` continua guardando quem digitou, e as
    # duas colunas nunca se misturam.
    agendado_por: UUID | None = None

    @field_validator("modalidade")
    @classmethod
    def _modalidade(cls, v: str) -> str:
        try:
            return regras.validar_modalidade(v)
        except AgendaInvalida as e:
            raise ValueError(str(e)) from e

    @field_validator("convidados")
    @classmethod
    def _convidados(cls, v: list[str]) -> list[str]:
        try:
            return regras.normalizar_convidados(v)
        except AgendaInvalida as e:
            raise ValueError(str(e)) from e


class ReuniaoCriar(ReuniaoCampos):
    """
    Marcar uma reunião: cria a tarefa e a reunião de uma vez.

    Exatamente um alvo, igual à tarefa — a validação é aqui, e não só no
    CHECK do banco, porque o CHECK devolveria 500 e o usuário precisa de
    422 com frase em português.

    `titulo` é OPCIONAL, ao contrário da tarefa comum. Quem marca a partir
    de um slot vazio da grade já disse tudo o que importa escolhendo tipo,
    empresa e horário; obrigar a digitar um título nesse momento produziria
    "Reunião" repetido quinze vezes na linha do tempo. Em branco, o
    servidor usa o próprio rótulo da grade.
    """
    oportunidade_id: UUID | None = None
    conta_id: UUID | None = None
    anfitriao_id: UUID
    inicio: datetime
    titulo: str | None = Field(None, max_length=200)
    descricao: str | None = None

    @model_validator(mode="after")
    def _alvo(self):
        try:
            regras_tarefa.validar_alvo(self.oportunidade_id, self.conta_id)
        except TarefaInvalida as e:
            raise ValueError(str(e)) from e
        return self


class ReuniaoDeTarefa(ReuniaoCampos):
    """
    Colocar na agenda uma tarefa que JÁ EXISTE.

    Não aceita alvo, título, anfitrião nem horário: todos vêm da tarefa. É
    o caminho de quem agendou o próximo passo pela oportunidade e só depois
    percebeu que aquilo é uma reunião com hora marcada — e é o que impede
    esse caminho de criar uma SEGUNDA tarefa dizendo a mesma coisa.
    """


class ReuniaoEditar(BaseModel):
    """
    Tudo opcional. `inicio` e `anfitriao_id` são encaminhados para a tarefa
    (prazo e responsável), porque é lá que eles moram.
    """
    tipo_id: int | None = None
    modalidade: str | None = None
    duracao_min: int | None = Field(None, ge=5, le=480)
    endereco: str | None = None
    link_video: str | None = None
    contato_id: UUID | None = None
    convidados: list[str] | None = None
    observacoes: str | None = None
    participantes: list[UUID] | None = None
    inicio: datetime | None = None
    anfitriao_id: UUID | None = None
    agendado_por: UUID | None = None
    titulo: str | None = Field(None, max_length=200)

    @field_validator("modalidade")
    @classmethod
    def _modalidade(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return regras.validar_modalidade(v)
        except AgendaInvalida as e:
            raise ValueError(str(e)) from e

    @field_validator("convidados")
    @classmethod
    def _convidados(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        try:
            return regras.normalizar_convidados(v)
        except AgendaInvalida as e:
            raise ValueError(str(e)) from e

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpo = v.strip()
        if not limpo:
            raise ValueError("O título da reunião não pode ficar em branco.")
        return limpo


class Cancelamento(BaseModel):
    motivo: str | None = None


class DesfechoIn(BaseModel):
    """
    O que aconteceu com a reunião.

    `realizada` conclui a tarefa e, com a oportunidade viva, EXIGE a
    próxima — é a mesma regra da Sprint 5, e é ela que faz a reunião
    empurrar o funil em vez de virar um fato isolado.

    `cancelada` e `no_show` cancelam a tarefa e não exigem próxima:
    cancelar é dizer que aquilo não ia acontecer, não que o negócio andou.
    `proxima` continua ACEITA nos dois, porque remarcar é o desfecho
    natural de um no-show — só não é obrigatória.
    """
    desfecho: str
    observacao: str | None = None
    proxima: ProximaTarefa | None = None

    @field_validator("desfecho")
    @classmethod
    def _desfecho(cls, v: str) -> str:
        try:
            return regras.validar_desfecho(v)
        except AgendaInvalida as e:
            raise ValueError(str(e)) from e


class ReuniaoOut(BaseModel):
    id: UUID
    tarefa_id: UUID

    # Derivados, prontos do servidor. `fim`, `slot`, `fora_da_grade` e
    # `rotulo` poderiam ser calculados no navegador — e é justamente por
    # isso que não são: a grade, o convite do Google e o cartão precisam
    # concordar, e três implementações da mesma conta divergem.
    inicio: datetime
    fim: datetime
    duracao_min: int
    slot: str | None
    fora_da_grade: bool
    rotulo: str

    tipo_id: int | None
    tipo_sigla: str | None
    tipo_nome: str | None
    modalidade: str
    modalidade_rotulo: str
    endereco: str | None
    link_video: str | None

    anfitriao_id: UUID
    anfitriao_nome: str | None
    agendado_por: UUID | None
    agendado_por_nome: str | None
    participantes: list[ParticipanteOut]

    # ── O desfecho ──
    # `desfecho` é o REGISTRADO (None enquanto ninguém marcou).
    # `desfecho_efetivo` é o que vale para contagem: o registrado, ou o
    # deduzido de uma tarefa fechada por outra tela. A tela mostra o
    # efetivo e usa o registrado para saber se ainda pode perguntar.
    desfecho: str | None
    desfecho_efetivo: str | None
    desfecho_rotulo: str | None
    desfecho_em: datetime | None
    desfecho_por_nome: str | None
    desfecho_observacao: str | None
    # Quantas horas antes do início a reunião foi desmarcada, no momento do
    # registro. Negativo = depois da hora.
    desfecho_antecedencia_horas: float | None
    # O que o formulário pré-seleciona. Reunião que já terminou sugere
    # `realizada`; a que ainda não começou, o que o relógio disser entre
    # cancelada e no-show. Some depois de registrado.
    desfecho_sugerido: str | None
    # Já terminou e ninguém disse o que aconteceu. É o que alimenta o
    # contador "N sem desfecho" da barra.
    pendente_de_desfecho: bool

    contato_id: UUID | None
    contato_nome: str | None
    contato_email: str | None
    convidados: list[str]

    # Da tarefa. `situacao` e `status_oportunidade` vêm juntos porque a
    # tela precisa saber, antes de abrir o cartão, se aquilo ainda pode ser
    # mexido — e buscar por reunião seria N+1 num JOIN que já existe.
    # Quantas OUTRAS tarefas do mesmo alvo estão em aberto. O painel de
    # desfecho lê isto junto de `status_oportunidade`: "Realizada" só exige
    # a próxima quando esta é a última aberta.
    outras_abertas: int = 0

    titulo: str
    descricao: str | None
    situacao: str
    concluida_em: datetime | None
    cancelada_em: datetime | None
    oportunidade_id: UUID | None
    oportunidade_numero: str | None
    status_oportunidade: str | None
    conta_id: UUID | None
    conta_razao_social: str | None

    # A previa do que o cliente vai receber. Vem do servidor, e nao montada
    # no navegador, porque e literalmente o texto que sai no convite --
    # duas versoes da mesma string deixariam a tela prometer um convite e o
    # Google entregar outro.
    convite_titulo: str
    convite_descricao: str

    google_event_id: str | None
    google_link: str | None
    google_sincronizado_em: datetime | None
    google_erro: str | None

    observacoes: str | None
    criado_em: datetime


class DiaDaAgenda(BaseModel):
    data: date
    dia_semana: str
    # Feriado NÃO bloqueia o agendamento, só pinta a coluna. O calendário
    # de `dia_nao_util` é mantido à mão e pode estar desatualizado; recusar
    # com base nele transformaria uma tabela esquecida em erro para o
    # usuário. Avisar é barato, bloquear cobra caro quando o dado erra.
    nao_util: bool
    motivo: str | None
    reunioes: list[ReuniaoOut]


class SemanaOut(BaseModel):
    inicio: date
    fim: date
    anfitriao_id: UUID | None
    anfitriao_nome: str | None
    slots: list[str]
    dias: list[DiaDaAgenda]
    total: int
    concluidas: int
    canceladas: int
    # Reuniões que já terminaram e ninguém registrou o desfecho. Fica na
    # barra porque a decisão foi NÃO adivinhar depois de N horas: sem um
    # número visível cobrando, a reunião esquecida sairia de toda
    # estatística em silêncio.
    pendentes: int
    # Só existe com UM anfitrião escolhido: "slots livres" da equipe
    # inteira somaria a agenda de cinco pessoas num número que não responde
    # a pergunta de ninguém.
    livres: int | None
    nao_sincronizadas: int
    google_configurado: bool


class DiaDoSdr(BaseModel):
    dia: date
    agendamentos: int


class LinhaSdr(BaseModel):
    usuario_id: UUID | None
    nome: str | None
    total: int
    por_dia: list[DiaDoSdr]


class DiaDoEv(BaseModel):
    dia: date
    total: int
    realizadas: int
    canceladas: int
    no_show: int
    pendentes: int


class LinhaEv(BaseModel):
    usuario_id: UUID
    nome: str | None
    total: int
    realizadas: int
    canceladas: int
    no_show: int
    pendentes: int
    por_dia: list[DiaDoEv]


class ProdutividadeOut(BaseModel):
    """
    As duas perguntas de rastreio, e elas recortam por DATAS DIFERENTES.

      por_sdr — quantos agendamentos a pessoa FEZ em cada dia. Recorta por
                `reunioes.criado_em`: é o dia em que o trabalho aconteceu.
      por_ev  — quantas reuniões a pessoa TEVE em cada dia, e com que
                resultado. Recorta por `tarefas.prazo`: é o dia da reunião.

    São números diferentes de propósito, e a distância entre eles é
    informação: uma reunião marcada dia 3 para o dia 20 conta no dia 3 do
    SDR e no dia 20 do EV. Um único eixo de data teria que escolher um dos
    dois e mentir no outro — a mesma escolha que `realizadas` × `agendadas`
    já faz no resumo de tarefas.
    """
    de: date
    ate: date
    dias: list[date]
    por_sdr: list[LinhaSdr]
    por_ev: list[LinhaEv]

    agendamentos: int
    realizadas: int
    canceladas: int
    no_show: int
    pendentes: int

    # Duas taxas, e o denominador é o mesmo: o que CHEGOU A UM RESULTADO
    # (realizadas + canceladas + no-show). Pendente fica de fora — ainda
    # não é resultado, e contá-lo como fracasso puniria quem marcou ontem.
    #
    # `None` quando não há denominador, e não 0%. Mesma regra das taxas de
    # parceiro: "0%" e "ainda não deu para saber" são coisas diferentes, e
    # a tela mostra `—` na segunda.
    taxa_realizacao: float | None
    taxa_no_show: float | None


# ── SQL compartilhado ────────────────────────────────────────────────

_SELECT_BASE = """
    SELECT r.id, r.tarefa_id, r.duracao_min, r.tipo_id,
           tr.sigla AS tipo_sigla, tr.nome AS tipo_nome,
           r.modalidade, r.endereco, r.link_video,
           r.contato_id, ct.nome AS contato_nome, ct.email AS contato_email,
           ct.telefone AS contato_telefone,
           r.convidados, r.observacoes,
           r.google_calendar_id, r.google_event_id, r.google_link,
           r.google_sincronizado_em, r.google_erro,
           r.criado_em,
           r.agendado_por, ag.nome AS agendado_por_nome,
           r.desfecho, r.desfecho_em, r.desfecho_observacao,
           r.desfecho_antecedencia_horas,
           dp.nome AS desfecho_por_nome,
           t.titulo, t.descricao, t.prazo AS inicio,
           t.concluida_em, t.cancelada_em,
           t.responsavel_id AS anfitriao_id,
           u.nome  AS anfitriao_nome,
           u.email AS anfitriao_email,
           -- Sai no convite, na linha "Consultor / Cel". Mesmo campo que a
           -- proposta comercial ja usa, e pelo mesmo motivo: o cliente
           -- precisa de um numero para ligar antes da reuniao.
           u.telefone AS anfitriao_telefone,
           t.oportunidade_id, o.numero AS oportunidade_numero,
           -- O alvo CRU da tarefa, ao lado do `conta_id` de exibicao logo
           -- abaixo (que e COALESCE e vira a empresa da oportunidade).
           -- Quem cria a proxima tarefa precisa do par exato -- passar a
           -- empresa da oportunidade como alvo manda DOIS alvos e o
           -- `validar_referencias` recusa exigindo conta parceira.
           t.conta_id AS alvo_conta_id,
           o.status AS status_oportunidade,
           COALESCE(t.conta_id, o.conta_id)           AS conta_id,
           COALESCE(cp.razao_social, co.razao_social) AS conta_razao_social,
           COALESCE(cp.nome_fantasia, co.nome_fantasia) AS conta_nome_fantasia,
           -- Vai para o TITULO do evento: grupos com varias razoes sociais
           -- parecidas sao comuns na carteira, e e o CNPJ que diz de qual
           -- filial e a reuniao.
           COALESCE(cp.cnpj, co.cnpj)                 AS conta_cnpj,
           -- Quantas OUTRAS tarefas do mesmo alvo estao em aberto. E o que
           -- diz ao painel de desfecho se registrar "Realizada" vai exigir
           -- a proxima tarefa: exige so quem fecha a ULTIMA aberta.
           --
           -- Sem isto, a reuniao -- que e uma tarefa a mais na oportunidade
           -- -- cobrava a proxima toda vez, e o numero de tarefas abertas
           -- nunca voltava para uma. Mesma conta de
           -- `contar_outras_abertas`, que valida no momento de gravar.
           (SELECT count(*) FROM tarefas x
             WHERE x.id <> t.id
               AND x.concluida_em IS NULL AND x.cancelada_em IS NULL
               AND (CASE WHEN t.oportunidade_id IS NOT NULL
                         THEN x.oportunidade_id = t.oportunidade_id
                         ELSE x.conta_id = t.conta_id END)
           ) AS outras_abertas
      FROM reunioes r
      JOIN tarefas  t  ON t.id = r.tarefa_id
      LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
      LEFT JOIN contatos ct      ON ct.id = r.contato_id
      LEFT JOIN usuarios u       ON u.id  = t.responsavel_id
      LEFT JOIN oportunidades o  ON o.id  = t.oportunidade_id
      LEFT JOIN contas co        ON co.id = o.conta_id
      LEFT JOIN contas cp        ON cp.id = t.conta_id
      LEFT JOIN usuarios ag      ON ag.id = r.agendado_por
      LEFT JOIN usuarios dp      ON dp.id = r.desfecho_por
"""

# O JOIN com `tarefas` é INNER, e é o único do arquivo que pode ser: a FK é
# NOT NULL. Todos os outros são LEFT pelo mesmo motivo da 006 — com INNER,
# uma reunião sem tipo, sem contato ou de parceiro (sem oportunidade)
# sumiria da grade EM SILÊNCIO, o pior modo de falha possível para uma tela
# cuja única promessa é mostrar a semana inteira.


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t is not None else None


def _linha(row, agora: datetime, participantes: dict[str, list[dict]]) -> dict:
    d = dict(row)
    d["convidados"] = list(d.get("convidados") or [])
    d["fim"] = regras.fim_de(d["inicio"], d["duracao_min"])
    d["slot"] = _hhmm(regras.slot_ancora(d["inicio"]))
    d["fora_da_grade"] = regras.fora_da_grade(d["inicio"])
    d["modalidade_rotulo"] = regras.ROTULO_MODALIDADE.get(
        d["modalidade"], d["modalidade"]
    )
    d["rotulo"] = regras.rotulo(
        sigla_tipo=d.get("tipo_sigla"),
        # Nome fantasia primeiro: é como a equipe chama a empresa, e é o
        # que cabe no cartão. Razão social é o nome do contrato.
        empresa=d.get("conta_nome_fantasia") or d.get("conta_razao_social"),
        anfitriao=d.get("anfitriao_nome"),
        modalidade=d["modalidade"],
    )
    d["situacao"] = regras_tarefa.situacao(
        EstadoTarefa(
            prazo=d["inicio"],
            concluida_em=d["concluida_em"],
            cancelada_em=d["cancelada_em"],
        ),
        agora,
    )
    d["participantes"] = participantes.get(str(d["id"]), [])
    d["convite_titulo"], d["convite_descricao"] = _texto_do_convite(d)

    # O desfecho que VALE para contagem: o registrado, ou o deduzido de uma
    # tarefa que outra tela fechou. Calculado aqui e não no navegador
    # porque é o mesmo número que o relatório soma — duas implementações
    # da mesma dedução divergem, e a que divergir é a que alguém está
    # olhando na reunião de segunda.
    d["desfecho_efetivo"] = regras.desfecho_efetivo(
        desfecho=d["desfecho"],
        concluida_em=d["concluida_em"],
        cancelada_em=d["cancelada_em"],
        inicio=d["inicio"],
    )
    d["desfecho_rotulo"] = regras.ROTULO_DESFECHO.get(d["desfecho_efetivo"])
    d["pendente_de_desfecho"] = regras.pendente_de_desfecho(
        desfecho=d["desfecho"],
        concluida_em=d["concluida_em"],
        cancelada_em=d["cancelada_em"],
        inicio=d["inicio"],
        duracao_min=d["duracao_min"],
        agora=agora,
    )
    # A sugestão que a tela pré-seleciona. Some depois de registrado: uma
    # sugestão ao lado de uma resposta já dada só convida a mexer no que
    # está certo.
    d["desfecho_sugerido"] = (
        None if d["desfecho_efetivo"]
        else regras.sugestao_de_desfecho(d["inicio"], d["duracao_min"], agora)
    )
    if d["desfecho_antecedencia_horas"] is not None:
        d["desfecho_antecedencia_horas"] = float(d["desfecho_antecedencia_horas"])
    return d


async def _participantes(conn, reuniao_ids: list) -> dict[str, list[dict]]:
    """
    Os participantes de VÁRIAS reuniões numa consulta só.

    Uma query por reunião faria a grade de uma semana cheia disparar
    dezenas de idas ao banco — o N+1 clássico, e numa tela que carrega a
    cada seta de navegação.
    """
    if not reuniao_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT rp.reuniao_id, rp.usuario_id, u.nome, u.cargo
          FROM reuniao_participantes rp
          LEFT JOIN usuarios u ON u.id = rp.usuario_id
         WHERE rp.reuniao_id = ANY($1::uuid[])
         ORDER BY u.nome
        """,
        reuniao_ids,
    )
    saida: dict[str, list[dict]] = {}
    for r in rows:
        saida.setdefault(str(r["reuniao_id"]), []).append({
            "usuario_id": r["usuario_id"],
            "nome": r["nome"],
            "cargo": r["cargo"],
        })
    return saida


async def _obter_row(conn, reuniao_id: UUID):
    row = await conn.fetchrow(f"{_SELECT_BASE} WHERE r.id = $1", reuniao_id)
    if row is None:
        raise HTTPException(404, "Reunião não encontrada.")
    return row


async def _obter(conn, reuniao_id: UUID) -> dict:
    row = await _obter_row(conn, reuniao_id)
    parts = await _participantes(conn, [row["id"]])
    return _linha(row, _agora(), parts)


# ── Conflito de agenda ───────────────────────────────────────────────


async def _checar_conflito(
    conn,
    anfitriao_id: UUID,
    inicio: datetime,
    duracao_min: int,
    ignorar_reuniao_id: UUID | None = None,
) -> None:
    """
    Recusa com 409 se o anfitrião já tem reunião sobrepondo este intervalo.

    A verificação é só do ANFITRIÃO, não dos participantes. A grade é a
    coluna de uma pessoa: é o dono da coluna que não pode estar em dois
    lugares. Bloquear por participante impediria o gestor que acompanha
    quatro reuniões de ser adicionado à quinta — e a decisão de acompanhar
    duas ao mesmo tempo é dele, não do sistema.

    CANCELADA NÃO OCUPA; CONCLUÍDA OCUPA. Cancelar é dizer que aquilo não
    vai acontecer, e o slot volta a valer. Concluída aconteceu: o horário
    esteve ocupado de verdade, e deixar marcar por cima reescreveria o
    passado da agenda.

    A sobreposição é meio-aberta, então 09:00–09:30 e 09:30–10:00 convivem
    — é a grade cheia funcionando, não conflito.
    """
    fim = regras.fim_de(inicio, duracao_min)
    row = await conn.fetchrow(
        """
        SELECT r.id, t.titulo, t.prazo
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
         WHERE t.responsavel_id = $1
           AND t.cancelada_em IS NULL
           AND ($4::uuid IS NULL OR r.id <> $4)
           AND t.prazo < $3
           AND (t.prazo + (r.duracao_min || ' minutes')::interval) > $2
         ORDER BY t.prazo
         LIMIT 1
        """,
        anfitriao_id, inicio, fim, ignorar_reuniao_id,
    )
    if row is None:
        return
    quando = regras.no_fuso(row["prazo"]).strftime("%d/%m às %H:%M")
    raise HTTPException(
        409,
        f"Esse horário já está ocupado: “{row['titulo']}” em {quando}.",
    )


async def _validar_horario(
    conn, anfitriao_id: UUID, inicio: datetime, duracao_min: int,
    ignorar_reuniao_id: UUID | None = None,
) -> None:
    try:
        regras.validar_duracao(duracao_min)
        regras.validar_dia_da_semana(inicio)
    except AgendaInvalida as e:
        raise HTTPException(422, str(e))
    await _checar_conflito(
        conn, anfitriao_id, inicio, duracao_min, ignorar_reuniao_id
    )


async def _validar_apoio(
    conn, tipo_id: int | None, contato_id: UUID | None,
    participantes: list[UUID] | None,
    agendado_por: UUID | None = None,
) -> None:
    if tipo_id is not None and not await conn.fetchval(
        "SELECT 1 FROM tipos_reuniao WHERE id = $1", tipo_id
    ):
        raise HTTPException(422, "Tipo de reunião não encontrado.")
    if contato_id is not None and not await conn.fetchval(
        "SELECT 1 FROM contatos WHERE id = $1 AND ativo", contato_id
    ):
        raise HTTPException(422, "Contato não encontrado ou inativo.")
    for uid in participantes or []:
        if not await conn.fetchval(
            "SELECT 1 FROM usuarios WHERE id = $1 AND ativo", uid
        ):
            raise HTTPException(422, "Participante não encontrado ou inativo.")
    if agendado_por is not None and not await conn.fetchval(
        "SELECT 1 FROM usuarios WHERE id = $1 AND ativo", agendado_por
    ):
        raise HTTPException(422, "Quem agendou não foi encontrado ou está inativo.")


async def _gravar_participantes(conn, reuniao_id: UUID, ids: list[UUID]) -> None:
    """
    Substitui a lista inteira. Chamado sempre dentro da transação de quem
    chama — a lista e a reunião precisam nascer (ou mudar) juntas.
    """
    await conn.execute(
        "DELETE FROM reuniao_participantes WHERE reuniao_id = $1", reuniao_id
    )
    unicos = list(dict.fromkeys(ids or []))
    for uid in unicos:
        await conn.execute(
            """
            INSERT INTO reuniao_participantes (reuniao_id, usuario_id)
            VALUES ($1, $2) ON CONFLICT DO NOTHING
            """,
            reuniao_id, uid,
        )


# ── Sincronização com o Google ───────────────────────────────────────


async def _emails_dos_participantes(conn, reuniao_id: UUID) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT u.email
          FROM reuniao_participantes rp
          JOIN usuarios u ON u.id = rp.usuario_id
         WHERE rp.reuniao_id = $1 AND u.email IS NOT NULL
        """,
        reuniao_id,
    )
    return [r["email"] for r in rows]


def _texto_do_convite(row) -> tuple[str, str]:
    """
    Título e corpo do evento, no formato que a operação já manda hoje à mão.

    NÃO é o `rotulo` da grade. São dois leitores diferentes: o rótulo é
    lido por quem já conhece o negócio, numa célula de 13rem; isto é lido
    pelo CLIENTE, na agenda dele, ao lado de compromissos de outras
    empresas. Ver a nota em services/agenda.py.
    """
    titulo = regras.titulo_evento(
        razao_social=row["conta_razao_social"],
        cnpj=row["conta_cnpj"],
        tipo_nome=row["tipo_nome"],
    )
    corpo = regras.descricao_evento(
        titulo=titulo,
        inicio=row["inicio"],
        modalidade=row["modalidade"],
        contato_nome=row["contato_nome"],
        contato_telefone=row["contato_telefone"],
        contato_email=row["contato_email"],
        anfitriao_nome=row["anfitriao_nome"],
        anfitriao_telefone=row["anfitriao_telefone"],
        endereco=row["endereco"] if row["modalidade"] == "presencial" else None,
        observacoes=row["observacoes"],
    )
    return titulo, corpo


async def _sincronizar(conn, reuniao_id: UUID) -> dict:
    """
    Manda a reunião para o Google e grava o resultado NA LINHA.

    Chamada SEMPRE fora da transação de escrita, e nunca dentro dela: uma
    chamada de rede de ~1s com transação aberta segura locks em `tarefas` e
    `reunioes` pelo tempo inteiro, e quem estiver salvando outra coisa
    espera junto.

    Nunca levanta. Falha vira `google_erro`, a tela mostra e oferece
    "sincronizar de novo". Mesma escolha da narrativa da IA no fechamento
    diário: recurso acessório não derruba o registro principal.
    """
    row = await _obter_row(conn, reuniao_id)

    # Reunião cancelada não vira convite; se já tinha evento, ele é
    # removido por quem cancelou. Nada a fazer aqui.
    if row["cancelada_em"] is not None:
        return await _obter(conn, reuniao_id)

    if not row["anfitriao_email"]:
        await conn.execute(
            "UPDATE reunioes SET google_erro = $2, atualizado_em = NOW() WHERE id = $1",
            reuniao_id,
            "O anfitrião não tem e-mail cadastrado — o convite não pode ser criado.",
        )
        return await _obter(conn, reuniao_id)

    convidados = await _emails_dos_participantes(conn, reuniao_id)
    if row["contato_email"]:
        convidados.append(row["contato_email"])
    convidados.extend(list(row["convidados"] or []))

    inicio = regras.no_fuso(row["inicio"])
    titulo_evento, descricao_evento = _texto_do_convite(row)
    dados = google_agenda.DadosEvento(
        titulo=titulo_evento,
        inicio=inicio,
        fim=regras.fim_de(inicio, row["duracao_min"]),
        anfitriao_email=row["anfitriao_email"],
        descricao=descricao_evento,
        endereco=row["endereco"],
        convidados=convidados,
        # Meet só quando é online E ainda não há um link colado à mão:
        # gerar uma sala nova por cima do link que o cliente já recebeu
        # mandaria duas salas diferentes para a mesma reunião.
        criar_meet=row["modalidade"] == "online" and not row["link_video"],
    )

    if row["google_event_id"]:
        resultado = await google_agenda.atualizar_evento(
            row["google_event_id"], row["google_calendar_id"], dados
        )
    else:
        resultado = await google_agenda.criar_evento(dados)

    if resultado.ok:
        await conn.execute(
            """
            UPDATE reunioes
               SET google_event_id = $2,
                   google_calendar_id = $3,
                   google_link = COALESCE($4, google_link),
                   google_sincronizado_em = NOW(),
                   google_erro = NULL,
                   atualizado_em = NOW()
             WHERE id = $1
            """,
            reuniao_id, resultado.event_id, resultado.calendar_id, resultado.link,
        )
    else:
        # O event_id ANTIGO é preservado de propósito. Uma atualização que
        # falhou não apaga o evento que já está na agenda do cliente —
        # limpar a coluna faria a próxima sincronização criar um SEGUNDO
        # evento, e o cliente ficaria com dois convites para a mesma
        # reunião sem saber qual vale.
        await conn.execute(
            "UPDATE reunioes SET google_erro = $2, atualizado_em = NOW() WHERE id = $1",
            reuniao_id, resultado.erro,
        )

    return await _obter(conn, reuniao_id)


async def remover_evento_da_tarefa(conn, tarefa_id: UUID) -> None:
    """
    Apaga o evento do Google da reunião desta tarefa, se houver.

    Existe para ser chamada de FORA da agenda: cancelar uma tarefa pela
    aba da oportunidade ou pela tela de gestão também precisa desmarcar o
    compromisso com o cliente. Sem isto, a reunião sumiria do HIPO e
    continuaria na agenda de todo mundo — e alguém entraria numa sala
    vazia.

    Melhor-esforço: silenciosa. Quem chamou está cancelando uma tarefa, e
    um erro do Google não pode fazer o cancelamento falhar.
    """
    row = await conn.fetchrow(
        """
        SELECT id, google_event_id, google_calendar_id
          FROM reunioes WHERE tarefa_id = $1
        """,
        tarefa_id,
    )
    if row is None or not row["google_event_id"]:
        return
    resultado = await google_agenda.remover_evento(
        row["google_event_id"], row["google_calendar_id"]
    )
    if resultado.ok:
        await conn.execute(
            """
            UPDATE reunioes
               SET google_event_id = NULL, google_link = NULL,
                   google_sincronizado_em = NULL, google_erro = NULL,
                   atualizado_em = NOW()
             WHERE id = $1
            """,
            row["id"],
        )
    else:
        await conn.execute(
            "UPDATE reunioes SET google_erro = $2, atualizado_em = NOW() WHERE id = $1",
            row["id"], resultado.erro,
        )


# ── Tipos de reunião ─────────────────────────────────────────────────


@router.get("/tipos", response_model=list[TipoReuniaoOut])
async def listar_tipos(
    incluir_inativos: bool = Query(False),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Os tipos disponíveis, na ordem do funil (diagnóstico antes de
    fechamento) — não alfabética, que embaralharia a sequência natural.
    """
    rows = await conn.fetch(
        """
        SELECT id, sigla, nome, slug, ordem, ativo
          FROM tipos_reuniao
         WHERE ($1::bool OR ativo)
         ORDER BY ordem, nome
        """,
        incluir_inativos,
    )
    return [dict(r) for r in rows]


@router.post(
    "/tipos",
    response_model=TipoReuniaoOut,
    # Ler e usar é de todo mundo com 'crm' (o guard do router); CRIAR exige
    # também 'usuarios', que só a gestão tem. É a guarda contra a deriva de
    # vocabulário que o CHECK fechado dá de graça no tipo de TAREFA: se
    # cada vendedor inventar a sigla dele, "quantas CF por mês" para de ser
    # uma pergunta respondível.
    dependencies=[Depends(requer_qualquer_modulo(["usuarios"]))],
)
async def criar_tipo(
    payload: TipoReuniaoIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Idempotente pelo slug, como as outras listas de domínio: criar algo que
    já existe é o mesmo que selecionar o que existe, e devolver 409 só
    obrigaria o front a tratar um caso que não é erro.

    A sigla, essa, é conflito de verdade: duas siglas iguais com nomes
    diferentes deixariam o rótulo da grade ambíguo.
    """
    nome = limpar_nome(payload.nome)
    slug = slugify(nome)
    if not slug:
        raise HTTPException(422, "Nome inválido: precisa ter ao menos uma letra ou número.")

    existente = await conn.fetchrow(
        "SELECT id, sigla, nome, slug, ordem, ativo FROM tipos_reuniao WHERE slug = $1",
        slug,
    )
    if existente:
        return dict(existente)

    if await conn.fetchval(
        "SELECT 1 FROM tipos_reuniao WHERE sigla = $1", payload.sigla
    ):
        raise HTTPException(
            409, f"Já existe um tipo com a sigla '{payload.sigla}'."
        )

    row = await conn.fetchrow(
        """
        INSERT INTO tipos_reuniao (sigla, nome, slug, ordem, criado_por)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, sigla, nome, slug, ordem, ativo
        """,
        payload.sigla, nome, slug, payload.ordem, user["id"],
    )
    return dict(row)


# ── A grade ──────────────────────────────────────────────────────────


@router.get("/semana", response_model=SemanaOut)
async def semana(
    anfitriao_id: UUID | None = None,
    agendado_por: UUID | None = None,
    inicio: date | None = Query(None, description="Qualquer dia da semana desejada."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    A grade de segunda a sexta: os slots de 30 minutos e o que está marcado
    em cada um.

    É a tela e o agregado no mesmo lugar, como manda a diretriz do
    dashboard operacional: os números do topo (marcadas, livres, o que
    ainda não virou convite) saem desta mesma resposta, e não de um
    endpoint separado que poderia discordar da lista logo abaixo.

    `inicio` aceita QUALQUER dia e é normalizado para a segunda daquela
    semana. É o que faz a seta de navegação e um link colado abrirem a
    mesma tela.

    SEM `anfitriao_id`, mostra a semana da equipe inteira — a visão de
    quem coordena, e a que o SDR usa para achar onde cabe a próxima. É a
    MESMA base para todo mundo: nada aqui é filtrado por quem está olhando,
    então um slot marcado aparece ocupado para a equipe inteira no instante
    seguinte. `livres` é a única coisa que só existe com uma agenda
    escolhida: somar os slots vagos de cinco pessoas produziria um número
    que não responde à pergunta de ninguém.

    `agendado_por` recorta por QUEM MARCOU, e combina com `anfitriao_id`:
    "as reuniões que eu marquei para o Bruno" precisa dos dois.

    Este endpoint precisa vir declarado ANTES de qualquer `/{id}`: com o
    wildcard na frente, "semana" seria lido como id e a resposta viraria
    422. Mesma armadilha do /kanban e do /resumo em crm_tarefas.
    """
    referencia = inicio or datetime.now(regras.FUSO_OPERACAO).date()
    dias = regras.dias_da_semana(referencia)
    de, ate = regras.janela_da_semana(referencia)

    where = ["t.prazo >= $1", "t.prazo < $2"]
    params: list = [de, ate]
    if anfitriao_id is not None:
        params.append(anfitriao_id)
        where.append(f"t.responsavel_id = ${len(params)}")
    # Os dois filtros são independentes e combináveis de propósito: "as
    # reuniões que EU marquei para o Bruno" é a pergunta do SDR conferindo
    # o próprio trabalho, e ela precisa dos dois ao mesmo tempo.
    if agendado_por is not None:
        params.append(agendado_por)
        where.append(f"r.agendado_por = ${len(params)}")

    rows = await conn.fetch(
        f"{_SELECT_BASE} WHERE {' AND '.join(where)} ORDER BY t.prazo",
        *params,
    )
    parts = await _participantes(conn, [r["id"] for r in rows])
    agora = _agora()
    itens = [_linha(r, agora, parts) for r in rows]

    feriados = {
        r["data"]: r["motivo"]
        for r in await conn.fetch(
            "SELECT data, motivo FROM dia_nao_util WHERE data >= $1 AND data <= $2",
            dias[0], dias[-1],
        )
    }

    por_dia: dict[date, list[dict]] = {d: [] for d in dias}
    for item in itens:
        dia = regras.no_fuso(item["inicio"]).date()
        # `setdefault` e não indexação direta: uma reunião gravada às 23h
        # de sexta com fuso estranho, ou um dado antigo, cairia fora dos
        # cinco dias e derrubaria a tela inteira com KeyError. Melhor a
        # tela abrir sem ela do que não abrir.
        por_dia.setdefault(dia, []).append(item)

    # Slots ocupados: um slot conta como tomado quando QUALQUER reunião viva
    # o cobre — inclusive uma de 90 minutos, que come três linhas da grade.
    # Contar por reunião diria "17 livres" numa manhã em que não cabe mais
    # nada.
    ocupados: set[tuple[date, time]] = set()
    for item in itens:
        if item["cancelada_em"] is not None:
            continue
        ini = regras.no_fuso(item["inicio"])
        fim = regras.no_fuso(item["fim"])
        for s in regras.SLOTS:
            faixa_ini = datetime.combine(ini.date(), s, tzinfo=regras.FUSO_OPERACAO)
            faixa_fim = regras.fim_de(faixa_ini, regras.PASSO_MIN)
            if regras.conflitam(ini, fim, faixa_ini, faixa_fim):
                ocupados.add((ini.date(), s))

    vivas = [i for i in itens if i["cancelada_em"] is None]
    livres = None
    if anfitriao_id is not None:
        uteis = [d for d in dias if d not in feriados]
        livres = len(uteis) * len(regras.SLOTS) - sum(
            1 for (d, _s) in ocupados if d in uteis
        )

    nome_anfitriao = None
    if anfitriao_id is not None:
        nome_anfitriao = await conn.fetchval(
            "SELECT nome FROM usuarios WHERE id = $1", anfitriao_id
        )

    return {
        "inicio": dias[0],
        "fim": dias[-1],
        "anfitriao_id": anfitriao_id,
        "anfitriao_nome": nome_anfitriao,
        "slots": [_hhmm(s) for s in regras.SLOTS],
        "dias": [
            {
                "data": d,
                "dia_semana": regras.rotulo_dia(d),
                "nao_util": d in feriados,
                "motivo": feriados.get(d),
                "reunioes": por_dia.get(d, []),
            }
            for d in dias
        ],
        "total": len(vivas),
        "concluidas": sum(1 for i in vivas if i["situacao"] == "concluida"),
        "canceladas": sum(1 for i in itens if i["cancelada_em"] is not None),
        "pendentes": sum(1 for i in itens if i["pendente_de_desfecho"]),
        "livres": livres,
        # O que ainda não chegou ao Google. É o número que impede o
        # convite perdido de passar despercebido — e por isso ele fica no
        # topo da tela, não escondido no detalhe de cada cartão.
        "nao_sincronizadas": sum(
            1 for i in vivas if not i["google_event_id"]
        ),
        "google_configurado": google_agenda.configurado(),
    }


@router.get("/produtividade", response_model=ProdutividadeOut)
async def produtividade(
    de: date = Query(..., description="Primeiro dia, no fuso da operação."),
    ate: date = Query(..., description="Último dia, inclusivo."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Agendamentos por dia por SDR, e reuniões por dia por EV com o desfecho.

    OS DOIS EIXOS DE DATA SÃO DIFERENTES, e é isso que os torna
    comparáveis: o SDR é medido pelo dia em que MARCOU (`criado_em`), o EV
    pelo dia em que a reunião ACONTECEU (`prazo`). Ver ProdutividadeOut.

    O RECORTE DE DATA VAI PARA O SQL; a classificação do desfecho fica em
    Python. Não é inconsistência: a janela é determinística (duas datas dão
    sempre os mesmos instantes) e pode ir para o banco sem criar segunda
    fonte de verdade. Já `desfecho_efetivo` depende do relógio e da regra
    das 24h, e repeti-la em SQL criaria a divergência que este módulo
    inteiro evita. É a mesma divisão de `/crm/tarefas/resumo`.

    Volume: reuniões por período é dezenas, não milhares — 18 slots × 5
    dias × o punhado de EVs. Classificar em Python custa menos que manter
    a regra em dois lugares.

    Visível para todo cargo com `crm`, como a produção de tarefas
    (`/crm/tarefas/resumo`) já é. Comparar produção entre pares é o que a
    tela existe para fazer; esconder aqui e mostrar lá seria arbitrário.

    Precisa vir declarado ANTES de `/reunioes/{id}` — mesma armadilha do
    /semana.
    """
    try:
        regras_tarefa.validar_janela(de, ate)
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    fuso = str(regras.FUSO_OPERACAO)
    inicio, fim = regras_tarefa.janela_utc(de, ate)
    dias = [de + timedelta(days=d) for d in range((ate - de).days + 1)]

    # ── SDR: contagem pura, agrupada no banco ──
    # Sem regra nenhuma envolvida — é count(*). Trazer linha a linha para
    # contar em Python seria carregar dado à toa.
    linhas_sdr = await conn.fetch(
        """
        SELECT r.agendado_por AS usuario_id,
               u.nome,
               (r.criado_em AT TIME ZONE $3)::date AS dia,
               count(*) AS agendamentos
          FROM reunioes r
          LEFT JOIN usuarios u ON u.id = r.agendado_por
         WHERE r.criado_em >= $1 AND r.criado_em < $2
         GROUP BY r.agendado_por, u.nome, (r.criado_em AT TIME ZONE $3)::date
        """,
        inicio, fim, fuso,
    )

    # ── EV: linha a linha, porque o desfecho é regra ──
    linhas_ev = await conn.fetch(
        f"""
        SELECT t.responsavel_id AS usuario_id,
               u.nome,
               t.prazo, t.concluida_em, t.cancelada_em,
               r.duracao_min, r.desfecho,
               (t.prazo AT TIME ZONE '{fuso}')::date AS dia
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
          LEFT JOIN usuarios u ON u.id = t.responsavel_id
         WHERE t.prazo >= $1 AND t.prazo < $2
        """,
        inicio, fim,
    )

    agora = _agora()

    def _molde_ev(dia):
        return {"dia": dia, "total": 0, "realizadas": 0,
                "canceladas": 0, "no_show": 0, "pendentes": 0}

    sdr: dict = {}
    for r in linhas_sdr:
        chave = str(r["usuario_id"])
        pessoa = sdr.setdefault(chave, {
            "usuario_id": r["usuario_id"], "nome": r["nome"],
            "total": 0, "por_dia": {d: 0 for d in dias},
        })
        pessoa["total"] += r["agendamentos"]
        # `setdefault` e não indexação: o AT TIME ZONE pode devolver um dia
        # de borda que não está na lista se alguém mexer na janela depois.
        # Melhor a linha aparecer fora da grade do que a tela cair.
        pessoa["por_dia"].setdefault(r["dia"], 0)
        pessoa["por_dia"][r["dia"]] += r["agendamentos"]

    ev: dict = {}
    for r in linhas_ev:
        chave = str(r["usuario_id"])
        pessoa = ev.setdefault(chave, {
            "usuario_id": r["usuario_id"], "nome": r["nome"],
            "total": 0, "realizadas": 0, "canceladas": 0,
            "no_show": 0, "pendentes": 0,
            "por_dia": {d: _molde_ev(d) for d in dias},
        })
        do_dia = pessoa["por_dia"].setdefault(r["dia"], _molde_ev(r["dia"]))

        efetivo = regras.desfecho_efetivo(
            desfecho=r["desfecho"], concluida_em=r["concluida_em"],
            cancelada_em=r["cancelada_em"], inicio=r["prazo"],
        )
        pendente = regras.pendente_de_desfecho(
            desfecho=r["desfecho"], concluida_em=r["concluida_em"],
            cancelada_em=r["cancelada_em"], inicio=r["prazo"],
            duracao_min=r["duracao_min"], agora=agora,
        )
        for alvo in (pessoa, do_dia):
            alvo["total"] += 1
            if efetivo == "realizada":
                alvo["realizadas"] += 1
            elif efetivo == "cancelada":
                alvo["canceladas"] += 1
            elif efetivo == "no_show":
                alvo["no_show"] += 1
            if pendente:
                alvo["pendentes"] += 1

    def _achatar(pessoa, campo_dia):
        pessoa = dict(pessoa)
        pessoa["por_dia"] = [
            ({"dia": d, "agendamentos": v} if campo_dia == "sdr" else v)
            for d, v in sorted(pessoa["por_dia"].items())
        ]
        return pessoa

    realizadas = sum(p["realizadas"] for p in ev.values())
    canceladas = sum(p["canceladas"] for p in ev.values())
    no_show = sum(p["no_show"] for p in ev.values())
    fechadas = realizadas + canceladas + no_show

    return {
        "de": de, "ate": ate, "dias": dias,
        # Ordenado por volume: a tela existe para comparar produção, e a
        # ordem alfabética faria a comparação depender de quem se chama
        # como. Empate desempata pelo nome, para a lista não dançar entre
        # duas cargas iguais.
        "por_sdr": sorted(
            (_achatar(p, "sdr") for p in sdr.values()),
            key=lambda p: (-p["total"], p["nome"] or ""),
        ),
        "por_ev": sorted(
            (_achatar(p, "ev") for p in ev.values()),
            key=lambda p: (-p["total"], p["nome"] or ""),
        ),
        "agendamentos": sum(p["total"] for p in sdr.values()),
        "realizadas": realizadas,
        "canceladas": canceladas,
        "no_show": no_show,
        "pendentes": sum(p["pendentes"] for p in ev.values()),
        "taxa_realizacao": (realizadas / fechadas) if fechadas else None,
        "taxa_no_show": (no_show / fechadas) if fechadas else None,
    }


@router.get("/reunioes/{reuniao_id}", response_model=ReuniaoOut)
async def obter(reuniao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    return await _obter(conn, reuniao_id)


# ── Escrita ──────────────────────────────────────────────────────────


@router.post("/reunioes", response_model=ReuniaoOut, status_code=http.HTTP_201_CREATED)
async def criar(
    payload: ReuniaoCriar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Marca a reunião: cria a TAREFA e a REUNIÃO na mesma transação, e só
    depois manda para o Google.

    A tarefa nasce com tipo `reuniao` sempre — o presencial vira
    `modalidade`, não tipo de tarefa. Se uma visita virasse tipo `visita` e
    uma call virasse `reuniao`, "quantas reuniões em agosto" precisaria
    somar dois tipos, e a primeira pessoa que esquecesse de somar publicaria
    um número errado.

    O Google fica FORA da transação de propósito: uma chamada de rede
    dentro dela seguraria locks pelo tempo inteiro, e uma falha lá
    desfaria o registro do que já foi combinado com o cliente.
    """
    await validar_referencias(
        conn, payload.oportunidade_id, payload.conta_id, payload.anfitriao_id
    )
    await _validar_apoio(
        conn, payload.tipo_id, payload.contato_id, payload.participantes,
        payload.agendado_por,
    )
    await _validar_horario(
        conn, payload.anfitriao_id, payload.inicio, payload.duracao_min
    )

    titulo = (payload.titulo or "").strip() or await _titulo_padrao(conn, payload)

    dados_tarefa = TarefaBase(
        tipo="reuniao",
        titulo=titulo,
        descricao=payload.descricao,
        responsavel_id=payload.anfitriao_id,
        prazo=payload.inicio,
    )

    async with conn.transaction():
        tarefa_id = await _inserir(
            conn, dados_tarefa,
            payload.oportunidade_id, payload.conta_id, user["id"], None,
        )
        reuniao_id = await conn.fetchval(
            """
            INSERT INTO reunioes (
                tarefa_id, duracao_min, tipo_id, modalidade, endereco,
                link_video, contato_id, convidados, observacoes,
                criado_por, agendado_por
            )
            -- O default de `agendado_por` e resolvido em PYTHON, e nao com
            -- COALESCE($11, $10) aqui: reusar o mesmo parametro em duas
            -- colunas faz o Postgres deduzir dois tipos para ele e recusar
            -- a query inteira com AmbiguousParameterError. Custou uma
            -- suite vermelha.
            --
            -- Default de coluna tambem nao serve: o banco nao enxerga o
            -- usuario da sessao, e deixar a coluna nula tiraria a reuniao
            -- do relatorio do SDR em silencio.
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """,
            tarefa_id, payload.duracao_min, payload.tipo_id, payload.modalidade,
            (payload.endereco or "").strip() or None,
            (payload.link_video or "").strip() or None,
            payload.contato_id, payload.convidados,
            (payload.observacoes or "").strip() or None,
            user["id"], payload.agendado_por or user["id"],
        )
        await _gravar_participantes(conn, reuniao_id, payload.participantes)

    return await _sincronizar(conn, reuniao_id)


async def _titulo_padrao(conn, payload: ReuniaoCriar) -> str:
    """
    O título quando quem marcou não digitou nenhum: o próprio rótulo da
    grade.

    Nasce dos dados que a pessoa JÁ escolheu (tipo, empresa, modalidade),
    então diz algo — ao contrário de "Reunião", que é o que se digita
    quinze vezes seguidas quando o campo é obrigatório e não há nada
    específico a dizer.
    """
    alvo_id = payload.oportunidade_id or payload.conta_id
    if payload.oportunidade_id is not None:
        empresa = await conn.fetchval(
            """
            SELECT COALESCE(c.nome_fantasia, c.razao_social)
              FROM oportunidades o JOIN contas c ON c.id = o.conta_id
             WHERE o.id = $1
            """,
            alvo_id,
        )
    else:
        empresa = await conn.fetchval(
            "SELECT COALESCE(nome_fantasia, razao_social) FROM contas WHERE id = $1",
            alvo_id,
        )
    sigla = None
    if payload.tipo_id is not None:
        sigla = await conn.fetchval(
            "SELECT sigla FROM tipos_reuniao WHERE id = $1", payload.tipo_id
        )
    anfitriao = await conn.fetchval(
        "SELECT nome FROM usuarios WHERE id = $1", payload.anfitriao_id
    )
    texto = regras.rotulo(
        sigla_tipo=sigla, empresa=empresa,
        anfitriao=anfitriao, modalidade=payload.modalidade,
    )
    # `or "Reunião"`: rótulo vazio é impossível hoje (a modalidade sempre
    # rende ao menos "ON"), mas o CHECK ck_tarefa_titulo devolveria 500 se
    # um dia rendesse — e 500 por título vazio é o pior jeito de descobrir
    # que alguém mexeu no formato do rótulo.
    return texto or "Reunião"


@router.post(
    "/reunioes/de-tarefa/{tarefa_id}",
    response_model=ReuniaoOut,
    status_code=http.HTTP_201_CREATED,
)
async def criar_de_tarefa(
    tarefa_id: UUID,
    payload: ReuniaoDeTarefa,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Coloca na agenda uma tarefa que já existe — o caminho de quem agendou o
    próximo passo pela oportunidade e só depois viu que aquilo é uma
    reunião com hora marcada.

    REAPROVEITA a tarefa em vez de criar outra. Criar uma segunda diria a
    mesma coisa duas vezes na linha do tempo da negociação e contaria duas
    reuniões na produção do mês.

    O TIPO DA TAREFA NÃO É REESCRITO. Uma `visita` que entra na agenda
    continua sendo uma visita: a modalidade sugerida vira presencial, mas o
    que a pessoa classificou permanece. Reclassificar por baixo mudaria
    números de meses fechados.
    """
    tarefa = await conn.fetchrow(
        """
        SELECT id, tipo, prazo, responsavel_id, concluida_em, cancelada_em,
               oportunidade_id, conta_id
          FROM tarefas WHERE id = $1
        """,
        tarefa_id,
    )
    if tarefa is None:
        raise HTTPException(404, "Tarefa não encontrada.")
    if tarefa["tipo"] not in ("reuniao", "visita"):
        raise HTTPException(
            422,
            "Só tarefa do tipo Reunião ou Visita entra na agenda. "
            "Edite o tipo da tarefa primeiro.",
        )
    try:
        regras_tarefa.validar_edicao(
            EstadoTarefa(
                prazo=tarefa["prazo"],
                concluida_em=tarefa["concluida_em"],
                cancelada_em=tarefa["cancelada_em"],
            )
        )
    except TarefaInvalida:
        # Mensagem própria: a de `validar_edicao` fala em "editar", e quem
        # clicou aqui não estava editando nada — estava tentando agendar.
        raise HTTPException(
            422,
            "Tarefa já fechada não entra na agenda. O histórico é imutável.",
        )
    if await conn.fetchval("SELECT 1 FROM reunioes WHERE tarefa_id = $1", tarefa_id):
        raise HTTPException(409, "Esta tarefa já está na agenda.")

    await _validar_apoio(
        conn, payload.tipo_id, payload.contato_id, payload.participantes,
        payload.agendado_por,
    )
    await _validar_horario(
        conn, tarefa["responsavel_id"], tarefa["prazo"], payload.duracao_min
    )

    async with conn.transaction():
        reuniao_id = await conn.fetchval(
            """
            INSERT INTO reunioes (
                tarefa_id, duracao_min, tipo_id, modalidade, endereco,
                link_video, contato_id, convidados, observacoes,
                criado_por, agendado_por
            )
            -- O default de `agendado_por` e resolvido em PYTHON, e nao com
            -- COALESCE($11, $10) aqui: reusar o mesmo parametro em duas
            -- colunas faz o Postgres deduzir dois tipos para ele e recusar
            -- a query inteira com AmbiguousParameterError. Custou uma
            -- suite vermelha.
            --
            -- Default de coluna tambem nao serve: o banco nao enxerga o
            -- usuario da sessao, e deixar a coluna nula tiraria a reuniao
            -- do relatorio do SDR em silencio.
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """,
            tarefa_id, payload.duracao_min, payload.tipo_id, payload.modalidade,
            (payload.endereco or "").strip() or None,
            (payload.link_video or "").strip() or None,
            payload.contato_id, payload.convidados,
            (payload.observacoes or "").strip() or None,
            user["id"], payload.agendado_por or user["id"],
        )
        await _gravar_participantes(conn, reuniao_id, payload.participantes)

    return await _sincronizar(conn, reuniao_id)


@router.patch("/reunioes/{reuniao_id}", response_model=ReuniaoOut)
async def editar(
    reuniao_id: UUID,
    payload: ReuniaoEditar,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Edita a reunião e, quando for o caso, a tarefa por trás dela.

    `inicio`, `anfitriao_id` e `titulo` NÃO são colunas de `reunioes`: são
    `tarefas.prazo`, `tarefas.responsavel_id` e `tarefas.titulo`. O PATCH
    os encaminha em vez de duplicá-los — é o que garante que reagendar pela
    agenda e reagendar pela aba de tarefas produzam exatamente o mesmo
    efeito.

    REUNIÃO FECHADA NÃO SE EDITA, pela regra de tarefa que já existia:
    reescrever o horário de uma reunião que já aconteceu apagaria o
    histórico que a linha do tempo existe para mostrar.

    Só refaz o convite quando algo que o cliente VÊ mudou. Um ajuste de
    observação interna disparando um "reunião atualizada" no e-mail do
    cliente ensinaria todo mundo a ignorar esses avisos — e aí o
    reagendamento de verdade passaria batido também.
    """
    atual = await _obter_row(conn, reuniao_id)
    try:
        regras_tarefa.validar_edicao(
            EstadoTarefa(
                prazo=atual["inicio"],
                concluida_em=atual["concluida_em"],
                cancelada_em=atual["cancelada_em"],
            )
        )
    except TarefaInvalida as e:
        raise HTTPException(422, str(e))

    campos = payload.model_dump(exclude_unset=True)

    novo_inicio = campos.get("inicio", atual["inicio"])
    novo_anfitriao = campos.get("anfitriao_id", atual["anfitriao_id"])
    nova_duracao = campos.get("duracao_min", atual["duracao_min"])

    if any(k in campos for k in ("inicio", "anfitriao_id", "duracao_min")):
        await _validar_horario(
            conn, novo_anfitriao, novo_inicio, nova_duracao, reuniao_id
        )
    if "anfitriao_id" in campos and not await conn.fetchval(
        "SELECT 1 FROM usuarios WHERE id = $1 AND ativo", novo_anfitriao
    ):
        raise HTTPException(422, "Anfitrião não encontrado ou inativo.")
    await _validar_apoio(
        conn,
        campos.get("tipo_id"),
        campos.get("contato_id"),
        campos.get("participantes"),
        campos.get("agendado_por"),
    )

    da_reuniao = {k: v for k, v in campos.items() if k in CAMPOS_EDITAVEIS}
    for texto in ("endereco", "link_video", "observacoes"):
        if texto in da_reuniao:
            da_reuniao[texto] = (da_reuniao[texto] or "").strip() or None

    async with conn.transaction():
        if da_reuniao:
            sets, params = [], []
            for chave, valor in da_reuniao.items():
                params.append(valor)
                sets.append(f"{chave} = ${len(params)}")
            params.append(reuniao_id)
            await conn.execute(
                f"UPDATE reunioes SET {', '.join(sets)}, atualizado_em = NOW()"
                f" WHERE id = ${len(params)}",
                *params,
            )

        da_tarefa = {}
        if "inicio" in campos:
            da_tarefa["prazo"] = campos["inicio"]
        if "anfitriao_id" in campos:
            da_tarefa["responsavel_id"] = campos["anfitriao_id"]
        if "titulo" in campos:
            da_tarefa["titulo"] = campos["titulo"]
        if da_tarefa:
            sets, params = [], []
            for chave, valor in da_tarefa.items():
                params.append(valor)
                sets.append(f"{chave} = ${len(params)}")
            params.append(atual["tarefa_id"])
            await conn.execute(
                f"UPDATE tarefas SET {', '.join(sets)}, atualizado_em = NOW()"
                f" WHERE id = ${len(params)}",
                *params,
            )

        if "participantes" in campos:
            await _gravar_participantes(
                conn, reuniao_id, campos["participantes"]
            )

    if CAMPOS_QUE_REFAZEM_O_CONVITE & set(campos) or "participantes" in campos:
        return await _sincronizar(conn, reuniao_id)
    return await _obter(conn, reuniao_id)


@router.post("/reunioes/{reuniao_id}/sincronizar", response_model=ReuniaoOut)
async def sincronizar(
    reuniao_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Tenta de novo mandar a reunião para o Google.

    Existe porque a falha é guardada em vez de levantada: sem um botão de
    reenviar, uma queda momentânea do Google deixaria a reunião marcada no
    HIPO e invisível para o cliente para sempre, e a única saída seria
    apagar e refazer.
    """
    await _obter_row(conn, reuniao_id)
    return await _sincronizar(conn, reuniao_id)


@router.post("/reunioes/{reuniao_id}/desfecho", response_model=ReuniaoOut)
async def registrar_desfecho(
    reuniao_id: UUID,
    payload: DesfechoIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Registra o que aconteceu: realizada, cancelada ou no-show.

    É a única porta que fecha uma reunião pela agenda, e ela faz as DUAS
    coisas na mesma transação — grava o desfecho e fecha a tarefa. Separar
    (um botão para o desfecho, outro para concluir) deixaria o par
    divergir na primeira vez que alguém clicasse só um.

      realizada            -> conclui a tarefa. Com a oportunidade viva,
                              EXIGE a próxima: é a regra da Sprint 5, e é
                              ela que faz a reunião empurrar o funil.
      cancelada / no_show  -> cancela a tarefa. Não exige a próxima, mas
                              aceita: remarcar é o desfecho natural de um
                              no-show.

    A DIFERENÇA ENTRE OS DOIS ÚLTIMOS É DO RELÓGIO, e quem escolhe é a
    pessoa. A tela pré-seleciona pela regra das 24h; aqui a antecedência é
    CALCULADA e guardada ao lado da escolha, sem sobrescrevê-la. Quando os
    dois discordam há uma conversa a ter — e ela só existe se o par tiver
    sido guardado.

    Desfecho não se reescreve. Reabrir uma reunião fechada apagaria o
    histórico pelo mesmo motivo que tarefa fechada é imutável — e o número
    do mês passado mudaria depois de fechado.
    """
    atual = await _obter_row(conn, reuniao_id)

    if atual["desfecho"] is not None:
        raise HTTPException(
            422,
            f"Esta reunião já foi registrada como "
            f"{regras.ROTULO_DESFECHO[atual['desfecho']]}.",
        )

    estado = EstadoTarefa(
        prazo=atual["inicio"],
        concluida_em=atual["concluida_em"],
        cancelada_em=atual["cancelada_em"],
    )
    desfecho = payload.desfecho
    encerra = regras.encerra_a_reuniao(desfecho)

    if payload.proxima is not None:
        await validar_referencias(
            conn, atual["oportunidade_id"], atual["alvo_conta_id"],
            payload.proxima.responsavel_id,
        )

    agora = _agora()
    antecedencia = regras.antecedencia_horas(atual["inicio"], agora)
    observacao = (payload.observacao or "").strip() or None

    async with conn.transaction():
        # A validação entra na transação por causa da contagem: a próxima só
        # é exigida de quem fecha a ÚLTIMA tarefa aberta do alvo, e esse
        # número precisa ser lido com o alvo travado. Foi a reunião que
        # tornou isso visível — ela é uma tarefa a mais na oportunidade, e
        # cobrar a próxima ao fechá-la fazia a conta nunca zerar.
        await _travar_alvo(conn, atual["oportunidade_id"], atual["alvo_conta_id"])
        outras = await contar_outras_abertas(
            conn, atual["tarefa_id"],
            atual["oportunidade_id"], atual["alvo_conta_id"],
        )
        try:
            if encerra:
                regras_tarefa.validar_cancelamento(estado)
            else:
                regras_tarefa.validar_conclusao(
                    estado, atual["status_oportunidade"],
                    payload.proxima is not None,
                    outras_abertas=outras,
                )
        except TarefaInvalida as e:
            raise HTTPException(422, str(e))

        if encerra:
            await conn.execute(
                """
                UPDATE tarefas
                   SET cancelada_em = NOW(),
                       motivo_cancelamento = $2,
                       atualizado_em = NOW()
                 WHERE id = $1
                """,
                atual["tarefa_id"],
                # Sem observação, o motivo vira o próprio desfecho: a linha
                # do tempo da oportunidade mostra `motivo_cancelamento`, e
                # "cancelada" sem motivo nenhum ali parece registro pela
                # metade para quem lê seis meses depois.
                observacao or regras.ROTULO_DESFECHO[desfecho],
            )
        else:
            await conn.execute(
                """
                UPDATE tarefas
                   SET concluida_em = NOW(),
                       resultado = $2,
                       atualizado_em = NOW()
                 WHERE id = $1
                """,
                atual["tarefa_id"], observacao,
            )
        if payload.proxima is not None:
            await _inserir(
                conn, payload.proxima,
                atual["oportunidade_id"], atual["alvo_conta_id"],
                user["id"], atual["tarefa_id"],
            )
        await conn.execute(
            """
            UPDATE reunioes
               SET desfecho = $2,
                   desfecho_em = NOW(),
                   desfecho_por = $3,
                   desfecho_observacao = $4,
                   desfecho_antecedencia_horas = $5,
                   atualizado_em = NOW()
             WHERE id = $1
            """,
            reuniao_id, desfecho, user["id"], observacao, antecedencia,
        )

    # O evento sai da agenda de todo mundo só quando a reunião NÃO
    # aconteceu. Apagar o de uma reunião realizada limparia o histórico do
    # calendário do vendedor — que é onde ele reconstrói a semana.
    if encerra:
        await remover_evento_da_tarefa(conn, atual["tarefa_id"])
    return await _obter(conn, reuniao_id)


@router.post("/reunioes/{reuniao_id}/cancelar", response_model=ReuniaoOut)
async def cancelar(
    reuniao_id: UUID,
    payload: Cancelamento,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cancela a reunião: fecha a tarefa e desmarca o evento na agenda de
    todo mundo.

    Cancelar não exige agendar a próxima — cancelar é dizer que aquilo não
    deveria ter sido marcado, não que o negócio andou. Mesma regra do
    cancelamento de tarefa, e o slot volta a ficar livre.

    O evento é removido DEPOIS do commit, e sua falha não desfaz o
    cancelamento: melhor um evento fantasma no Google (com o erro visível
    na tela e um botão para tentar de novo) do que uma reunião que o HIPO
    diz que continua de pé enquanto ninguém vai aparecer.
    """
    atual = await _obter_row(conn, reuniao_id)
    try:
        regras_tarefa.validar_cancelamento(
            EstadoTarefa(
                prazo=atual["inicio"],
                concluida_em=atual["concluida_em"],
                cancelada_em=atual["cancelada_em"],
            )
        )
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
        atual["tarefa_id"], (payload.motivo or "").strip() or None,
    )
    await remover_evento_da_tarefa(conn, atual["tarefa_id"])
    return await _obter(conn, reuniao_id)
