"""
HIPO — Confirmação da véspera (entrega 048, migration 029).

Regras puras da tarefa que a agenda abre sozinha para quem agendou
confirmar a reunião por WhatsApp no dia útil anterior. O banco fica no
router (routers/crm_agenda._sincronizar_confirmacao).

Módulo próprio, e não mais um bloco em services/agenda.py: a agenda é
editada por outras entregas em paralelo, e duas entregas no mesmo arquivo
a partir da mesma base travam o pré-voo de quem for a segunda.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from services.agenda import no_fuso as _local, primeiro_nome
from services.tarefa import FUSO_OPERACAO

__all__ = [
    "TIPO_TAREFA_CONFIRMACAO", "HORA_CONFIRMACAO", "dia_util_anterior",
    "prazo_da_confirmacao", "dia_por_extenso", "titulo_confirmacao",
    "mensagem_confirmacao", "descricao_confirmacao",
]

# ── A confirmação da véspera ─────────────────────────────────────────
#
# O roteiro de vendas manda o SDR confirmar a reunião por WhatsApp no dia
# útil anterior: reunião confirmada acontece, reunião esquecida vira
# no-show. A agenda abre essa tarefa sozinha quando a reunião é marcada
# numa oportunidade com folga para isso.
#
# A REGRA É A VÉSPERA ÚTIL TER QUE SER DEPOIS DE HOJE. "Marcada com pelo
# menos dois dias úteis de antecedência" dito do jeito que dá para testar:
# reunião de quinta marcada na terça tem a quarta para confirmar; marcada
# na quarta, a véspera é hoje — quem acabou de combinar não precisa
# confirmar o que combinou agora há pouco, e uma tarefa nascendo "para
# hoje" só sujaria a coluna do dia.

# WhatsApp e não "outro": é o canal que o roteiro manda usar, e é o tipo
# que conta como contato na produção do SDR.
TIPO_TAREFA_CONFIRMACAO = "whatsapp"

# Começo do expediente. Prazo no meio da tarde deixaria a confirmação
# para a última hora — e o cliente que pede para remarcar precisa de
# tempo para o EV achar outro horário no mesmo dia.
HORA_CONFIRMACAO = time(9, 0)

_DIA_DA_SEMANA = {
    0: "segunda", 1: "terça", 2: "quarta", 3: "quinta",
    4: "sexta", 5: "sábado", 6: "domingo",
}


def dia_util_anterior(dia: date, nao_uteis: Iterable[date] = ()) -> date:
    """
    O dia útil imediatamente antes de `dia`: pula fim de semana e os dias
    sem expediente cadastrados pela gestão (`dia_nao_util`).

    Reunião de segunda confirma na sexta; de quinta depois do feriado de
    quarta, na terça.
    """
    pular = set(nao_uteis)
    d = dia - timedelta(days=1)
    while d.weekday() >= 5 or d in pular:
        d -= timedelta(days=1)
    return d


def prazo_da_confirmacao(
    inicio: datetime,
    agora: datetime,
    nao_uteis: Iterable[date] = (),
    fuso: ZoneInfo = FUSO_OPERACAO,
) -> datetime | None:
    """
    Quando a confirmação deve ser feita — ou None se não cabe uma.

    None quando a véspera útil da reunião é hoje ou já passou: a reunião
    foi marcada sem os dois dias úteis de folga.
    """
    vespera = dia_util_anterior(_local(inicio, fuso).date(), nao_uteis)
    if vespera <= _local(agora, fuso).date():
        return None
    return datetime.combine(vespera, HORA_CONFIRMACAO, tzinfo=fuso)


def dia_por_extenso(
    inicio: datetime, vespera: date, fuso: ZoneInfo = FUSO_OPERACAO
) -> str:
    """
    "amanhã" quando a reunião é no dia seguinte ao da confirmação; senão o
    dia da semana ("segunda"). O roteiro é explícito: na sexta, "amanhã"
    para uma reunião de segunda faz o cliente achar que é sábado.
    """
    dia = _local(inicio, fuso).date()
    if dia == vespera + timedelta(days=1):
        return "amanhã"
    return _DIA_DA_SEMANA[dia.weekday()]


def titulo_confirmacao(
    *, empresa: str | None, inicio: datetime, fuso: ZoneInfo = FUSO_OPERACAO,
) -> str:
    """'Confirmar reunião 12/10 09:30 - XPTO'. Cabe nos 200 da coluna."""
    quando = _local(inicio, fuso)
    texto = f"Confirmar reunião {quando.strftime('%d/%m %H:%M')}"
    empresa = (empresa or "").strip()
    if empresa:
        texto = f"{texto} - {empresa}"
    return texto[:200]


def mensagem_confirmacao(
    *,
    contato_nome: str | None,
    inicio: datetime,
    vespera: date,
    anfitriao_nome: str | None,
    modalidade: str,
    fuso: ZoneInfo = FUSO_OPERACAO,
) -> str:
    """
    A mensagem do roteiro, já preenchida:

        "Nivaldo, tudo certo para amanhã às 09:30 com Jakeline? O link está
        no convite. Qualquer coisa, me avisa por aqui."

    Primeiro nome dos dois lados — é WhatsApp, não ofício. Presencial fala
    do endereço em vez do link. Parte que falta some sem deixar buraco.
    """
    quando = _local(inicio, fuso)
    dia = dia_por_extenso(inicio, vespera, fuso)
    abertura = primeiro_nome(contato_nome)
    pergunta = f"tudo certo para {dia} às {quando.strftime('%H:%M')}"
    ev = primeiro_nome(anfitriao_nome)
    if ev:
        pergunta = f"{pergunta} com {ev}"
    pergunta += "?"
    if abertura:
        pergunta = f"{abertura}, {pergunta}"
    else:
        pergunta = pergunta[0].upper() + pergunta[1:]
    onde = (
        "O endereço está no convite." if modalidade == "presencial"
        else "O link está no convite."
    )
    return f"{pergunta} {onde} Qualquer coisa, me avisa por aqui."


def descricao_confirmacao(mensagem: str) -> str:
    """O corpo da tarefa: a mensagem pronta e o que fazer com a resposta."""
    return (
        "Confirmação da véspera. Mande pelo WhatsApp:\n"
        "\n"
        f"\"{mensagem}\"\n"
        "\n"
        "Confirmou: conclua esta tarefa.\n"
        "Pediu para mudar: edite a reunião ainda na conversa, com o horário "
        "novo já na agenda do EV. Esta tarefa acompanha o novo horário."
    )
