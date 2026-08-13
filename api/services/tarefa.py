"""
HIPO — Regras das tarefas do funil.

Funções puras: sem banco, sem I/O, sem `datetime.now()` escondido. Todo
cálculo que depende do relógio recebe `agora` como parâmetro — é o que
permite testar "atrasada" e "hoje" sem mockar o tempo, mesmo padrão de
services/dias_uteis.py.

Três regras moram aqui:

  1. SITUAÇÃO DERIVADA. A tarefa não tem coluna de estado. O que ela tem é
     prazo, concluída_em e cancelada_em; o estado sai da combinação desses
     três com o relógio. Guardar 'atrasada' no banco exigiria um job virando
     o estado à meia-noite, e falha de job produz dado mentiroso.

  2. CONCLUIR EXIGE A PRÓXIMA. Enquanto a oportunidade está aberta, fechar
     uma tarefa sem marcar a seguinte deixaria o negócio sem próximo passo —
     que é exatamente o buraco que o CRM existe para tapar. A exceção é a
     oportunidade já finalizada: acabou, não há próxima.

  3. EXATAMENTE UM ALVO. Toda tarefa é de uma oportunidade OU de um parceiro,
     nunca das duas e nunca de nenhum. Ver `validar_alvo`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# O dia de calendário que interessa é o do escritório, não o de Greenwich.
# Sem isto, uma tarefa marcada para 21h de Brasília cai no dia SEGUINTE em
# UTC e aparece como 'futura' em vez de 'hoje' — some da coluna do dia
# justamente no fim da tarde, quando o vendedor mais olha para ela.
FUSO_OPERACAO = ZoneInfo("America/Sao_Paulo")

# Tipos de tarefa. Lista fechada de propósito: diferente de vertical e
# origem, aqui não interessa cada um inventar o seu — a comparação entre
# "quantas ligações até fechar" só funciona com vocabulário estável.
TIPOS = (
    "ligacao", "reuniao", "visita", "proposta", "email", "whatsapp", "outro",
)

ROTULOS_TIPO = {
    "ligacao": "Ligação",
    "reuniao": "Reunião",
    "visita": "Visita",
    "proposta": "Proposta",
    "email": "E-mail",
    "whatsapp": "WhatsApp",
    "outro": "Outro",
}

# Situações derivadas. As três primeiras são tarefa em aberto.
SITUACOES_ABERTAS = ("atrasada", "hoje", "futura")
SITUACOES_FECHADAS = ("concluida", "cancelada")
SITUACOES = SITUACOES_ABERTAS + SITUACOES_FECHADAS

# Ordem de urgência para a tela: atrasada primeiro, concluída por último.
ORDEM_SITUACAO = {s: i for i, s in enumerate(
    ("atrasada", "hoje", "futura", "concluida", "cancelada")
)}


class TarefaInvalida(ValueError):
    """Operação recusada pelas regras de tarefa."""


@dataclass(frozen=True)
class EstadoTarefa:
    prazo: datetime
    concluida_em: datetime | None = None
    cancelada_em: datetime | None = None


def validar_tipo(tipo: str) -> str:
    if tipo not in TIPOS:
        raise TarefaInvalida(
            f"Tipo de tarefa inválido: '{tipo}'. Use: {', '.join(TIPOS)}."
        )
    return tipo


def esta_aberta(estado: EstadoTarefa) -> bool:
    return estado.concluida_em is None and estado.cancelada_em is None


# ── O alvo da tarefa ─────────────────────────────────────────────────
#
# Desde a 006, tarefa tem dois alvos possíveis: a oportunidade (o follow-up
# do negócio) e a conta parceira (o cultivo da relação com quem indica).
#
# EXATAMENTE UM. Zero seria a lista de afazeres pessoal que a Sprint 5
# recusou de propósito — sem vínculo a tarefa para de servir para métrica.
# Dois tornaria ambíguo em qual funil ela conta, e a primeira métrica que
# somasse os dois alvos contaria a mesma tarefa duas vezes.

ALVOS = ("oportunidade", "parceiro")

ROTULOS_ALVO = {"oportunidade": "Oportunidade", "parceiro": "Parceiro"}


def validar_alvo(oportunidade_id, conta_id) -> str:
    """
    Devolve 'oportunidade' ou 'parceiro'. Levanta TarefaInvalida se vierem
    os dois ou nenhum.

    O CHECK do banco (ck_tarefa_alvo) é a última linha de defesa; esta é a
    primeira, e é a que produz mensagem em português em vez de 500.
    """
    tem_opp = oportunidade_id is not None
    tem_conta = conta_id is not None
    if tem_opp and tem_conta:
        raise TarefaInvalida(
            "A tarefa é de uma oportunidade OU de um parceiro, não das duas."
        )
    if not tem_opp and not tem_conta:
        raise TarefaInvalida(
            "Informe a oportunidade ou o parceiro a que esta tarefa pertence."
        )
    return "oportunidade" if tem_opp else "parceiro"


def situacao(
    estado: EstadoTarefa,
    agora: datetime,
    fuso: ZoneInfo = FUSO_OPERACAO,
) -> str:
    """
    Situação derivada da tarefa.

        cancelada_em preenchido        -> 'cancelada'
        concluida_em preenchido        -> 'concluida'
        prazo no mesmo dia que agora   -> 'hoje'
        prazo antes de agora           -> 'atrasada'
        senão                          -> 'futura'

    'hoje' é dia de calendário, não janela de 24h: uma tarefa marcada para as
    09h continua sendo "de hoje" às 18h, mesmo já atrasada em relação à hora.
    Só vira 'atrasada' na virada do dia. Vendedor não trata as duas coisas do
    mesmo jeito — o que passou da hora ainda dá para fazer hoje; o que passou
    do dia é dívida.

    E o dia é o do FUSO DA OPERAÇÃO, não o de UTC. Comparando em UTC, uma
    tarefa das 21h de Brasília já está no dia seguinte e vira 'futura' — ela
    sumia da coluna de hoje exatamente no fim da tarde.
    """
    if estado.cancelada_em is not None:
        return "cancelada"
    if estado.concluida_em is not None:
        return "concluida"

    prazo = _com_fuso(estado.prazo).astimezone(fuso)
    agora = _com_fuso(agora).astimezone(fuso)

    if prazo.date() == agora.date():
        return "hoje"
    if prazo < agora:
        return "atrasada"
    return "futura"


def exige_proxima(status_oportunidade: str | None) -> bool:
    """
    Concluir esta tarefa obriga a criar a próxima?

    Sim enquanto a oportunidade está viva (ativa ou suspensa). Não quando ela
    já foi finalizada — conquistada, perdida ou cancelada não têm próximo
    passo comercial, e exigir um só produziria tarefa de mentira que ninguém
    vai fazer.

    Suspensa continua exigindo de propósito: suspender é pausa, e pausa sem
    data para voltar é como oportunidade morre em silêncio.

    TAREFA DE PARCEIRO EXIGE SEMPRE (`status_oportunidade` chega None).
    Parceria não tem estado final que dispense a próxima — e é exatamente
    por isso que ela exige: sem um próximo contato marcado, a relação some
    da agenda de todo mundo e só reaparece meses depois, como parceiro
    dormente. O farol mostra que parou; a corrente de tarefas é o que
    impede de parar.

    Quem realmente não tem próximo passo com um parceiro não deve concluir a
    tarefa: deve CANCELAR (que é dizer "isso não ia acontecer") ou tirar o
    parceiro da carteira. As duas saídas existem e nenhuma exige próxima.
    """
    if status_oportunidade is None:
        return True
    return status_oportunidade in ("ativa", "suspensa")


# Mensagem por alvo. A da oportunidade manda finalizar; a do parceiro não
# pode mandar isso, porque não existe "finalizar parceria" — mandar o
# usuário fazer uma coisa que a tela não oferece é pior do que não explicar.
_SEM_PROXIMA = {
    "oportunidade": (
        "Concluir exige agendar a próxima tarefa desta oportunidade. "
        "Se não há próximo passo, finalize a oportunidade."
    ),
    "parceiro": (
        "Concluir exige agendar a próxima conversa com este parceiro. "
        "Se não há próximo passo, cancele a tarefa em vez de concluir, ou "
        "tire o parceiro da carteira."
    ),
}


def validar_conclusao(
    estado: EstadoTarefa,
    status_oportunidade: str | None,
    tem_proxima: bool,
) -> None:
    """
    Levanta TarefaInvalida com mensagem em português se a conclusão não pode
    acontecer. O CHECK do banco é a última linha de defesa; esta é a primeira.
    """
    if estado.cancelada_em is not None:
        raise TarefaInvalida("Esta tarefa foi cancelada e não pode ser concluída.")
    if estado.concluida_em is not None:
        raise TarefaInvalida("Esta tarefa já foi concluída.")
    if exige_proxima(status_oportunidade) and not tem_proxima:
        alvo = "parceiro" if status_oportunidade is None else "oportunidade"
        raise TarefaInvalida(_SEM_PROXIMA[alvo])


def validar_cancelamento(estado: EstadoTarefa) -> None:
    if estado.concluida_em is not None:
        raise TarefaInvalida("Tarefa concluída não pode ser cancelada.")
    if estado.cancelada_em is not None:
        raise TarefaInvalida("Esta tarefa já foi cancelada.")


def validar_edicao(estado: EstadoTarefa) -> None:
    """
    Só tarefa em aberto é editável.

    Reescrever prazo ou título de tarefa já fechada apagaria o histórico —
    que é justamente o que a aba existe para mostrar.
    """
    if not esta_aberta(estado):
        raise TarefaInvalida(
            "Tarefa fechada não pode ser editada. O histórico é imutável."
        )


def chave_ordenacao(situacao_atual: str, prazo: datetime) -> tuple[int, datetime]:
    """
    Ordem de exibição: bloco por situação (atrasada → hoje → futura →
    concluída → cancelada) e, dentro do bloco, por prazo crescente.
    """
    return (ORDEM_SITUACAO.get(situacao_atual, 99), _com_fuso(prazo))


def _com_fuso(d: datetime) -> datetime:
    """
    asyncpg devolve TIMESTAMPTZ com fuso, mas teste puro costuma montar
    datetime ingênuo. Comparar os dois levanta TypeError, então normaliza
    para UTC quando vier sem fuso.
    """
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)
