"""
HIPO — Temperatura do contato: quente, morno ou frio (entrega 046).

Função pura: sem banco, sem relógio escondido — `agora` entra como
parâmetro, mesmo padrão de services/tarefa.py.

O sinal responde "como está o relacionamento com ESTA PESSOA", a partir
das tarefas feitas com ela (em qualquer oportunidade ou parceria — a
temperatura é da pessoa, não da negociação).

O QUE CONTA
  * Só tarefa CONCLUÍDA. Concluir é dizer que a conversa aconteceu.
  * Tarefa futura ou ainda aberta não conta: é intenção, não contato.
  * Cancelada não conta — inclui reunião com desfecho No-show ou
    Cancelada, que fecham a tarefa como cancelada.
  * O dia que vale é `concluida_em` (quando aconteceu), não o prazo.

COMO PONTUA (quantidade × recência × peso do sucesso)

    recência da conversa      até 14 dias = 3   15–30 = 2   31–60 = 1   >60 = 0
    tipo                      reunião ou visita realizada = 2 × ; demais = 1 ×

    QUENTE  pontos >= 6  E  a última conversa foi há até 14 dias
    MORNO   pontos >= 2
    FRIO    o resto (nunca falou, ou só conversa antiga)

    Exemplos: 2 ligações na semana = 6 → quente; 1 reunião realizada há 10
    dias = 6 → quente; 1 WhatsApp respondido há 5 dias = 3 → morno;
    1 ligação há 40 dias = 1 → frio.

Reunião e visita valem o dobro porque são o sucesso mais forte: a pessoa
reservou tempo para você. "Quente" exige recência além dos pontos — três
reuniões no mês passado e silêncio nas últimas duas semanas é morno.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Faixas de recência: (dias até, peso). Ordenadas.
FAIXAS_RECENCIA = ((14, 3), (30, 2), (60, 1))
JANELA_DIAS = FAIXAS_RECENCIA[-1][0]

TIPOS_PESO_DOBRADO = ("reuniao", "visita")

PONTOS_QUENTE = 6
DIAS_QUENTE = 14
PONTOS_MORNO = 2

ROTULOS = {"quente": "Quente", "morno": "Morno", "frio": "Frio"}


@dataclass(frozen=True)
class Interacao:
    tipo: str
    concluida_em: datetime


@dataclass(frozen=True)
class Temperatura:
    nivel: str                    # 'quente' | 'morno' | 'frio'
    rotulo: str
    pontos: int
    interacoes_janela: int        # concluídas nos últimos 60 dias
    ultima_interacao: datetime | None
    dias_desde_ultima: int | None


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


def peso_recencia(dias: int) -> int:
    for limite, peso in FAIXAS_RECENCIA:
        if dias <= limite:
            return peso
    return 0


def peso_tipo(tipo: str) -> int:
    return 2 if tipo in TIPOS_PESO_DOBRADO else 1


def calcular(
    interacoes: list[Interacao] | tuple,
    agora: datetime,
    ultima_conhecida: datetime | None = None,
) -> Temperatura:
    """
    `interacoes`: as tarefas CONCLUÍDAS com o contato (o chamador já filtra
    concluída; cancelada e aberta nem chegam aqui). Uma concluída com data
    no futuro (relógio torto, carga antiga) conta como hoje.
    """
    agora = _utc(agora)
    pontos = 0
    na_janela = 0
    ultima: datetime | None = None
    for it in interacoes:
        quando = _utc(it.concluida_em)
        if ultima is None or quando > ultima:
            ultima = quando
        dias = max((agora - quando).days, 0)
        p = peso_recencia(dias)
        if p:
            na_janela += 1
            pontos += p * peso_tipo(it.tipo)

    # A busca no banco só traz a janela de 60 dias; a última conversa
    # ANTIGA vem à parte, para a tela poder dizer "há 4 meses".
    if ultima_conhecida is not None:
        uc = _utc(ultima_conhecida)
        if ultima is None or uc > ultima:
            ultima = uc
    dias_ultima = max((agora - ultima).days, 0) if ultima else None
    if pontos >= PONTOS_QUENTE and dias_ultima is not None and dias_ultima <= DIAS_QUENTE:
        nivel = "quente"
    elif pontos >= PONTOS_MORNO:
        nivel = "morno"
    else:
        nivel = "frio"
    return Temperatura(
        nivel=nivel,
        rotulo=ROTULOS[nivel],
        pontos=pontos,
        interacoes_janela=na_janela,
        ultima_interacao=ultima,
        dias_desde_ultima=dias_ultima,
    )


def como_dict(t: Temperatura) -> dict:
    return {
        "temperatura": t.nivel,
        "temperatura_rotulo": t.rotulo,
        "temperatura_pontos": t.pontos,
        "interacoes_60d": t.interacoes_janela,
        "ultima_conversa": t.ultima_interacao,
        "dias_desde_ultima_conversa": t.dias_desde_ultima,
    }
