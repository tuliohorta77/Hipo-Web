"""
HIPO — Regras do funil de oportunidades.

Funções puras: sem banco, sem I/O. É aqui que vive o invariante fase×status
que o CHECK do banco também garante — a diferença é que aqui dá para explicar
o erro em português para o usuário, em vez de devolver uma violação de
constraint.

O invariante:

    ativa | suspensa                     -> fase != 'finalizado'
    perdido | cancelado | conquistado    -> fase == 'finalizado'

Consequência prática: não existe "mudar só o status" nem "mudar só a fase"
quando o desfecho está envolvido. Definir um status de desfecho move a
oportunidade para Finalizado na mesma operação, e reabrir exige dizer para
qual fase ela volta.
"""
from __future__ import annotations

from dataclasses import dataclass

# Ordem importa: é ela que define "avançar" e "retroceder" no funil, e a
# sequência das colunas do kanban.
FASES = ("lead", "qualificacao", "apresentacao", "negociacao", "finalizado")

FASES_ABERTAS = tuple(f for f in FASES if f != "finalizado")

STATUS_ABERTOS = ("ativa", "suspensa")
STATUS_DESFECHO = ("perdido", "cancelado", "conquistado")
STATUS = STATUS_ABERTOS + STATUS_DESFECHO

# Desfechos que exigem motivo. 'conquistado' não exige: ganhar não precisa de
# justificativa, e obrigar o vendedor a preencher algo no melhor momento do
# funil só gera lixo de dado.
STATUS_COM_MOTIVO = ("perdido", "cancelado")

# 'perdido' entra na taxa de conversão; 'cancelado' fica fora de todo
# denominador — é erro nosso de CRM (lead errado do finder, duplicata,
# empresa inexistente), não recusa do cliente.
STATUS_CONTA_CONVERSAO = ("perdido", "conquistado")

TEMPERATURAS = tuple(range(0, 100, 10))   # 0, 10, ..., 90

ROTULOS_FASE = {
    "lead": "Lead",
    "qualificacao": "Qualificação",
    "apresentacao": "Apresentação",
    "negociacao": "Negociação",
    "finalizado": "Finalizado",
}


class TransicaoInvalida(ValueError):
    """Transição recusada pelas regras do funil."""


@dataclass(frozen=True)
class Estado:
    fase: str
    status: str
    fase_desfecho: str | None = None
    motivo_desfecho_id: int | None = None
    temperatura: int | None = None


def eh_desfecho(status: str) -> bool:
    return status in STATUS_DESFECHO


def eh_aberta(status: str) -> bool:
    return status in STATUS_ABERTOS


def validar_estado(estado: Estado) -> None:
    """
    Valida um estado completo. Levanta TransicaoInvalida com mensagem que o
    usuário entende — o CHECK do banco é a última linha de defesa, não a
    primeira.
    """
    if estado.fase not in FASES:
        raise TransicaoInvalida(f"Fase desconhecida: '{estado.fase}'.")
    if estado.status not in STATUS:
        raise TransicaoInvalida(f"Status desconhecido: '{estado.status}'.")

    if eh_aberta(estado.status) and estado.fase == "finalizado":
        raise TransicaoInvalida(
            "Uma oportunidade em aberto não pode estar na fase Finalizado. "
            "Escolha um desfecho: conquistado, perdido ou cancelado."
        )
    if eh_desfecho(estado.status) and estado.fase != "finalizado":
        raise TransicaoInvalida(
            f"O status '{estado.status}' só existe na fase Finalizado."
        )

    if estado.fase == "finalizado":
        if estado.fase_desfecho not in FASES_ABERTAS:
            raise TransicaoInvalida(
                "Finalizar exige registrar de qual fase a oportunidade saiu."
            )
    elif estado.fase_desfecho is not None:
        raise TransicaoInvalida(
            "Só oportunidade finalizada tem fase de desfecho."
        )

    if estado.status in STATUS_COM_MOTIVO and estado.motivo_desfecho_id is None:
        raise TransicaoInvalida(
            f"O status '{estado.status}' exige informar o motivo."
        )

    if estado.status == "ativa" and estado.temperatura is None:
        raise TransicaoInvalida(
            "Oportunidade ativa precisa de temperatura (0 a 90)."
        )
    if estado.temperatura is not None and estado.temperatura not in TEMPERATURAS:
        raise TransicaoInvalida(
            "Temperatura deve ser um múltiplo de 10 entre 0 e 90."
        )


def mover_para_fase(atual: Estado, nova_fase: str) -> Estado:
    """
    Move entre fases abertas. É o que o drag-and-drop do kanban chama.

    Arrastar para Finalizado NÃO passa por aqui: soltar naquela coluna abre o
    modal de desfecho, que chama `finalizar`. Sem isso o kanban criaria
    oportunidade finalizada sem status nem motivo.
    """
    if nova_fase == "finalizado":
        raise TransicaoInvalida(
            "Para finalizar, informe o desfecho (conquistado, perdido ou cancelado)."
        )
    if nova_fase not in FASES_ABERTAS:
        raise TransicaoInvalida(f"Fase desconhecida: '{nova_fase}'.")
    if eh_desfecho(atual.status):
        raise TransicaoInvalida(
            "Oportunidade finalizada não muda de fase. Reabra antes."
        )
    if nova_fase == atual.fase:
        raise TransicaoInvalida(f"A oportunidade já está em {ROTULOS_FASE[nova_fase]}.")

    novo = Estado(
        fase=nova_fase,
        status=atual.status,
        fase_desfecho=None,
        motivo_desfecho_id=None,
        temperatura=atual.temperatura,
    )
    validar_estado(novo)
    return novo


def finalizar(atual: Estado, status: str, motivo_desfecho_id: int | None) -> Estado:
    """
    Fecha a oportunidade. Guarda em `fase_desfecho` a fase de onde ela saiu —
    é isso que permite medir em qual fase se perde e de qual fase vêm os
    ganhos.
    """
    if status not in STATUS_DESFECHO:
        raise TransicaoInvalida(
            f"'{status}' não é um desfecho. Use: {', '.join(STATUS_DESFECHO)}."
        )
    if eh_desfecho(atual.status):
        raise TransicaoInvalida("Esta oportunidade já está finalizada.")
    if status in STATUS_COM_MOTIVO and motivo_desfecho_id is None:
        raise TransicaoInvalida(f"O status '{status}' exige informar o motivo.")

    novo = Estado(
        fase="finalizado",
        status=status,
        fase_desfecho=atual.fase,
        # Conquistado não carrega motivo mesmo que venha um por engano.
        motivo_desfecho_id=motivo_desfecho_id if status in STATUS_COM_MOTIVO else None,
        temperatura=atual.temperatura,
    )
    validar_estado(novo)
    return novo


def reabrir(atual: Estado, fase_destino: str | None, temperatura: int | None) -> Estado:
    """
    Traz de volta para o funil. Sem `fase_destino`, volta para a fase de onde
    saiu — que é quase sempre o que se quer ao desfazer um fechamento errado.

    Exige temperatura porque o estado de destino é 'ativa'.
    """
    if not eh_desfecho(atual.status):
        raise TransicaoInvalida("Só oportunidade finalizada pode ser reaberta.")

    destino = fase_destino or atual.fase_desfecho
    if destino not in FASES_ABERTAS:
        raise TransicaoInvalida(
            f"Fase de retorno inválida: '{destino}'. "
            f"Use uma destas: {', '.join(FASES_ABERTAS)}."
        )

    novo = Estado(
        fase=destino,
        status="ativa",
        fase_desfecho=None,
        motivo_desfecho_id=None,
        temperatura=temperatura if temperatura is not None else atual.temperatura,
    )
    validar_estado(novo)
    return novo


def mudar_status(atual: Estado, novo_status: str, temperatura: int | None = None) -> Estado:
    """
    Alterna entre ativa e suspensa. Desfechos não passam por aqui — use
    `finalizar` ou `reabrir`, que sabem cuidar da fase.
    """
    if novo_status not in STATUS_ABERTOS:
        raise TransicaoInvalida(
            "Para finalizar use o desfecho; para voltar ao funil, a reabertura."
        )
    if eh_desfecho(atual.status):
        raise TransicaoInvalida("Oportunidade finalizada precisa ser reaberta antes.")
    if novo_status == atual.status:
        raise TransicaoInvalida(f"A oportunidade já está '{novo_status}'.")

    temp = temperatura if temperatura is not None else atual.temperatura
    # Suspensa não exige temperatura, mas o valor antigo é preservado para o
    # dia em que voltar a ser ativa.
    novo = Estado(
        fase=atual.fase,
        status=novo_status,
        fase_desfecho=None,
        motivo_desfecho_id=None,
        temperatura=temp,
    )
    validar_estado(novo)
    return novo


def formatar_numero(ano: int, sequencial: int) -> str:
    """
    OPP-2026-00001.

    A sequence do banco é global (não reinicia por ano), então o sufixo é
    único para sempre — o ano é informativo. Reiniciar por ano exigiria
    coordenação entre transições concorrentes na virada, sem ganho real.
    """
    return f"OPP-{ano}-{sequencial:05d}"
