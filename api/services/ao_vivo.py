"""
HIPO - Transcricao AO VIVO da reuniao (prova de conceito).

Funcoes puras, sem banco e sem relogio escondido: rodam no pytest local do
Windows.

O QUE E

Durante a call, a tela "Reuniao ao vivo" do HIPO capta dois audios no
navegador do vendedor -- o microfone (canal `vendedor`) e o som da aba do
Google Meet (canal `cliente`) -- e transcreve cada um com o reconhecimento
de voz do proprio Chrome (Web Speech API, que desde o Chrome 133 aceita uma
MediaStreamTrack qualquer e nao so o microfone). O texto chega aqui em
lotes e fica preso a reuniao, que e uma tarefa.

POR QUE DOIS CANAIS E NAO UM

O Meet nao devolve para a aba a voz de quem esta falando nela. Entao o
microfone so tem o vendedor, e a aba so tem o cliente: a separacao de quem
falou vem de graca, sem diarizacao. E ela que da a proporcao de fala (nas
reunioes reais medidas em 30/09 o EV falou 65-68% das palavras).

POR QUE E PROVA DE CONCEITO

O reconhecimento do Chrome e gratuito, mas nao tem contrato de qualidade:
para em silencio, nao se sabe se roda dois ao mesmo tempo em toda maquina,
e o pt-BR com audio de chamada nunca foi medido. A transcricao do Meet que
ja chega depois da reuniao (entrega 020) vira o gabarito: `cobertura` diz
quanto das palavras do Meet o ao vivo tambem pegou. Se servir, os cartoes
de roteiro e objecao entram em cima disto; se nao, troca-se so o
transcritor (AssemblyAI no canal do cliente) e o resto fica.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable

CANAIS = ("vendedor", "cliente")

# Janela em que a captura pode ser ABERTA. Uma hora antes cobre o "entrei
# cedo para testar o audio"; tres horas depois do fim cobre a reuniao que
# estourou o horario. Fora disso a sessao gravaria conversa que nao e desta
# reuniao -- o link do Meet e reutilizavel, a mesma armadilha que a coleta
# da entrega 020 trata com a janela de conferencias.
ANTECEDENCIA = timedelta(hours=1)
TOLERANCIA_APOS_FIM = timedelta(hours=3)

# Limites de um lote. O navegador manda a cada ~10 s; 300 falas num lote so
# aconteceria com a rede caida por muito tempo, e ai o cliente reparte.
MAX_FALAS_POR_LOTE = 300
MAX_CARACTERES_FALA = 2000
MAX_ERROS_POR_LOTE = 50
# Erros guardados por sessao. O reconhecimento que cai em loop (sem rede)
# relata a cada tentativa; guardar tudo encheria a linha de ruido igual.
MAX_ERROS_GUARDADOS = 100

_PALAVRA = re.compile(r"\w+", re.UNICODE)


def motivo_para_nao_abrir(
    *,
    inicio: datetime,
    duracao_min: int,
    agora: datetime,
    cancelada: bool,
    modalidade: str | None,
) -> str | None:
    """
    None quando a captura pode comecar; senao, a frase para a tela.

    >>> from datetime import timezone
    >>> t = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
    >>> motivo_para_nao_abrir(inicio=t, duracao_min=30, agora=t,
    ...                       cancelada=False, modalidade="online") is None
    True
    """
    if cancelada:
        return "A reunião foi cancelada."
    if modalidade != "online":
        return ("A transcrição ao vivo precisa do áudio da chamada, "
                "e esta reunião é presencial.")
    if agora < inicio - ANTECEDENCIA:
        return "Ainda é cedo: a captura abre 1 hora antes do início da reunião."
    fim = inicio + timedelta(minutes=duracao_min)
    if agora > fim + TOLERANCIA_APOS_FIM:
        return "A reunião já terminou há mais de 3 horas."
    return None


def pode_capturar(
    *,
    usuario_id,
    eh_gestao: bool,
    anfitriao_id,
    participantes: Iterable,
) -> bool:
    """
    Quem pode LIGAR a captura: o anfitriao, um participante interno ou a
    gestao. O SDR que marcou a reuniao para o EV nao esta na call, e uma
    sessao aberta por ele gravaria o microfone de quem nao conduz.
    """
    if eh_gestao:
        return True
    uid = str(usuario_id)
    if uid == str(anfitriao_id):
        return True
    return uid in {str(p) for p in participantes}


def palavras(texto: str | None) -> list[str]:
    """
    Palavras normalizadas: minusculas e sem acento.

    O Meet escreve "você" e o Chrome as vezes "voce"; comparar com acento
    contaria como erro de transcricao o que e so grafia.
    """
    if not texto:
        return []
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto.lower())
        if not unicodedata.combining(c)
    )
    return _PALAVRA.findall(sem_acento)


def contar_palavras(texto: str | None) -> int:
    return len(palavras(texto))


def metricas(falas: Iterable[dict]) -> dict:
    """
    O que a barra da tela mostra: palavras por canal e a proporcao do
    vendedor. A proporcao e por PALAVRA, nao por tempo -- o reconhecimento
    do navegador nao da o instante de cada palavra, e palavras e a mesma
    regua usada na medicao das reunioes reais.

    Sem palavra nenhuma a proporcao e None, e nao 0: "0% de fala do
    vendedor" numa sessao vazia seria uma afirmacao falsa.
    """
    por_canal = {c: 0 for c in CANAIS}
    quantas = 0
    for f in falas:
        canal = f.get("canal")
        if canal not in por_canal:
            continue
        por_canal[canal] += contar_palavras(f.get("texto"))
        quantas += 1
    total = por_canal["vendedor"] + por_canal["cliente"]
    return {
        "falas": quantas,
        "palavras_vendedor": por_canal["vendedor"],
        "palavras_cliente": por_canal["cliente"],
        "palavras_total": total,
        "proporcao_vendedor_pct": (
            round(100 * por_canal["vendedor"] / total) if total else None
        ),
    }


def cobertura(ao_vivo: Iterable[str], referencia: Iterable[str]) -> dict | None:
    """
    Quanto das palavras da transcricao do Meet o ao vivo tambem pegou.

    Conta por MULTICONJUNTO: "sim sim sim" no Meet e "sim" no ao vivo
    cobre 1 de 3, nao 3 de 3. Ordem nao importa -- as duas fontes quebram
    as falas em lugares diferentes, e alinhar frase a frase seria medir o
    corte, nao o reconhecimento.

    None quando nao ha referencia: sem gabarito, nao ha nota.
    """
    ref = Counter()
    for t in referencia:
        ref.update(palavras(t))
    total_ref = sum(ref.values())
    if total_ref == 0:
        return None
    viv = Counter()
    for t in ao_vivo:
        viv.update(palavras(t))
    comuns = sum((ref & viv).values())
    return {
        "palavras_meet": total_ref,
        "palavras_ao_vivo": sum(viv.values()),
        "cobertura_pct": round(100 * comuns / total_ref),
    }


def limpar_texto(texto: str | None) -> str:
    """Espacos colapsados; o reconhecimento as vezes manda '  ' e quebra."""
    return " ".join((texto or "").split())


def juntar_erros(atuais: list | None, novos: list) -> list:
    """Anexa e guarda so os MAX_ERROS_GUARDADOS mais recentes."""
    return (list(atuais or []) + list(novos))[-MAX_ERROS_GUARDADOS:]
