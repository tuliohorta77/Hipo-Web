"""
HIPO — Regras da transcrição de reunião.

Funções puras: sem banco, sem rede e sem relógio escondido (`agora` entra
sempre por parâmetro). Mesmo padrão de services/agenda.py e tarefa.py — é o
que deixa testar "o Google ainda está gerando o arquivo" sem esperar o
Google gerar arquivo nenhum.

O I/O com o Meet mora em services/google_meet.py; a orquestração (banco +
Google + IA) em services/coleta_transcricao.py.

═══ A PERGUNTA QUE ESTE MÓDULO RESPONDE ═══════════════════════════════

Dado o que o Google devolveu sobre a sala desta reunião, o que fazer
AGORA: esperar mais, coletar o texto, ou desistir dizendo por quê.

As três saídas importam. "Esperar" para sempre deixaria a tela mostrando
"aguardando" numa reunião em que ninguém entrou. "Desistir" cedo demais
declararia indisponível uma transcrição que o Google entrega 20 minutos
depois — ele de fato demora. As janelas abaixo são o meio-termo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from services.agenda import FUSO_OPERACAO

# ── Janelas ──────────────────────────────────────────────────────────

# Ninguém entrou na sala até N horas depois do horário previsto de término:
# a reunião não aconteceu por ali (remarcaram por telefone, foi presencial
# no fim, o cliente faltou). Vinte e quatro horas cobrem o atraso de
# qualquer reunião real e o "fizemos no dia seguinte, no mesmo link".
ESPERA_SEM_CONFERENCIA = timedelta(hours=24)

# A conferência acabou e o Google não criou recurso de transcrição nenhum.
# O recurso aparece junto com o início da transcrição, então meia hora de
# folga depois do fim é só margem para a consistência eventual da API.
ESPERA_SEM_TRANSCRICAO = timedelta(minutes=30)

# A transcrição existe mas o arquivo ainda não foi gerado (estado STARTED
# ou ENDED). Na prática o Google leva de minutos a uma hora. Passadas seis
# horas, coleta-se o que houver: as falas já estão na API mesmo antes do
# Doc ficar pronto, e esperar para sempre por um arquivo que travou
# esconderia um texto que existe.
ESPERA_ARQUIVO = timedelta(hours=6)

# A Meet API apaga as falas 30 dias depois da conferência. O coletor
# automático só olha a janela curta; a coleta manual (botão na tela) aceita
# até aqui — depois disso, não há o que buscar.
LIMITE_API = timedelta(days=29)

# O timer olha reuniões que terminaram há no máximo isto. Reunião que
# ficou "aguardando" por mais tempo que isso ou já desistiu pelas janelas
# acima, ou esbarrou em erro de configuração que o botão resolve.
JANELA_TIMER = timedelta(days=3)

# Não adianta procurar antes de a reunião terminar: margem de cinco
# minutos sobre o fim previsto.
MARGEM_POS_FIM = timedelta(minutes=5)

# Conferências fora desta janela em volta do horário marcado NÃO são desta
# reunião. O link de um evento do Calendar é reutilizável, e o vendedor que
# usa a sala de segunda para uma call rápida na quinta com outro cliente
# colaria a conversa errada na tarefa errada — com dado de cliente dentro.
TOLERANCIA_ANTES = timedelta(hours=1)
TOLERANCIA_DEPOIS = timedelta(hours=24)

# O que vai para a IA. Uma reunião de uma hora dá ~60 mil caracteres; o
# teto cobre duas horas e meia com folga e mantém o custo previsível. Acima
# disso, fica o começo e o fim — onde mora o "o que ficou combinado".
MAX_CARACTERES_IA = 150_000

STATUS = ("aguardando", "pronta", "indisponivel")

ROTULO_STATUS = {
    "aguardando": "Aguardando transcrição",
    "pronta": "Transcrição pronta",
    "indisponivel": "Sem transcrição",
}

_CODIGO_MEET = re.compile(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})\b", re.I)


# ── Estruturas ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Transcricao:
    """Um recurso `conferenceRecords/*/transcripts/*`, reduzido ao que importa."""
    nome: str
    estado: str                       # STARTED | ENDED | FILE_GENERATED
    documento_url: str | None = None


@dataclass(frozen=True)
class Conferencia:
    """Uma vez em que alguém abriu a sala. `fim` None = ainda em andamento."""
    nome: str
    inicio: datetime
    fim: datetime | None
    transcricoes: tuple[Transcricao, ...] = ()


@dataclass(frozen=True)
class Decisao:
    """
    O que fazer agora. `acao` é uma de:

      aguardar  -- tentar de novo na próxima passada
      coletar   -- baixar as falas das `transcricoes`
      desistir  -- gravar `indisponivel` com `motivo`
    """
    acao: str
    motivo: str | None = None
    conferencias: tuple[Conferencia, ...] = field(default_factory=tuple)

    @property
    def transcricoes(self) -> list[Transcricao]:
        return [t for c in self.conferencias for t in c.transcricoes]


@dataclass(frozen=True)
class Fala:
    """Uma entrada do transcript, com o participante já resolvido para nome."""
    inicio: datetime
    fim: datetime | None
    participante: str
    texto: str


# ── Link → código ────────────────────────────────────────────────────


def codigo_meet(*links: str | None) -> str | None:
    """
    O código da sala (abc-defg-hij) do primeiro link que for do Meet.

    Recebe vários porque a reunião tem dois lugares onde o link pode estar:
    o gerado pelo Google (`google_link`) e o colado à mão (`link_video`).
    Um link do Meet colado à mão também serve — se a sala for de alguém do
    domínio, a API enxerga.

    >>> codigo_meet("https://meet.google.com/abc-defg-hij")
    'abc-defg-hij'
    >>> codigo_meet(None, "https://meet.google.com/ABC-DEFG-HIJ?authuser=0")
    'abc-defg-hij'
    >>> codigo_meet("https://zoom.us/j/123") is None
    True
    """
    for link in links:
        if not link:
            continue
        achado = _CODIGO_MEET.search(link)
        if achado:
            return achado.group(1).lower()
    return None


# ── Quando procurar ──────────────────────────────────────────────────


def pode_procurar(fim_previsto: datetime, agora: datetime) -> bool:
    """A reunião já deveria ter acabado?"""
    return _utc(agora) >= _utc(fim_previsto) + MARGEM_POS_FIM


def dentro_do_limite_da_api(fim_previsto: datetime, agora: datetime) -> bool:
    """As falas ainda existem no Google? (A API apaga depois de 30 dias.)"""
    return _utc(agora) - _utc(fim_previsto) <= LIMITE_API


def conferencias_da_reuniao(
    conferencias: list[Conferencia] | tuple[Conferencia, ...],
    inicio: datetime,
    fim_previsto: datetime,
) -> tuple[Conferencia, ...]:
    """
    Só as conferências que começaram perto do horário marcado, em ordem.

    Ver TOLERANCIA_ANTES/DEPOIS: o link é reutilizável, e a conversa de
    outro cliente na mesma sala não pode entrar nesta tarefa.
    """
    de = _utc(inicio) - TOLERANCIA_ANTES
    ate = _utc(fim_previsto) + TOLERANCIA_DEPOIS
    dentro = [c for c in conferencias if de <= _utc(c.inicio) <= ate]
    return tuple(sorted(dentro, key=lambda c: _utc(c.inicio)))


# ── A decisão ────────────────────────────────────────────────────────


def decidir(
    conferencias: list[Conferencia] | tuple[Conferencia, ...],
    inicio: datetime,
    fim_previsto: datetime,
    agora: datetime,
) -> Decisao:
    """
    Esperar, coletar ou desistir.

    A ordem das perguntas é a ordem em que as coisas acontecem numa
    reunião: alguém entrou? já saíram todos? a transcrição foi ligada? o
    arquivo ficou pronto?
    """
    agora = _utc(agora)
    fim_previsto = _utc(fim_previsto)
    confs = conferencias_da_reuniao(conferencias, inicio, fim_previsto)

    if not confs:
        if agora < fim_previsto + ESPERA_SEM_CONFERENCIA:
            return Decisao("aguardar", "Ninguém entrou na sala do Meet ainda.")
        return Decisao(
            "desistir",
            "Ninguém entrou na sala do Meet desta reunião.",
        )

    if any(c.fim is None for c in confs):
        return Decisao("aguardar", "A reunião ainda está em andamento.", confs)

    ultimo_fim = max(_utc(c.fim) for c in confs)  # type: ignore[arg-type]
    transcricoes = [t for c in confs for t in c.transcricoes]

    if not transcricoes:
        if agora < ultimo_fim + ESPERA_SEM_TRANSCRICAO:
            return Decisao(
                "aguardar", "A reunião acabou há pouco; conferindo a transcrição.",
                confs,
            )
        return Decisao(
            "desistir",
            "A reunião aconteceu, mas a transcrição não foi ligada na sala.",
            confs,
        )

    prontas = all(t.estado == "FILE_GENERATED" for t in transcricoes)
    if prontas or agora >= ultimo_fim + ESPERA_ARQUIVO:
        return Decisao("coletar", None, confs)
    return Decisao("aguardar", "O Google ainda está gerando a transcrição.", confs)


# ── O texto ──────────────────────────────────────────────────────────


def juntar_falas(falas: list[Fala]) -> list[Fala]:
    """
    Ordena por horário e junta falas seguidas da mesma pessoa.

    O Meet quebra um mesmo raciocínio em várias entradas de poucos
    segundos. Lido assim, o texto vira uma lista de frases soltas com o
    mesmo nome repetido em cada linha — e ninguém lê.
    """
    saida: list[Fala] = []
    for f in sorted(falas, key=lambda x: _utc(x.inicio)):
        texto = " ".join((f.texto or "").split())
        if not texto:
            continue
        if saida and saida[-1].participante == f.participante:
            anterior = saida[-1]
            saida[-1] = Fala(
                inicio=anterior.inicio,
                fim=f.fim or anterior.fim,
                participante=anterior.participante,
                texto=f"{anterior.texto} {texto}",
            )
        else:
            saida.append(Fala(f.inicio, f.fim, f.participante, texto))
    return saida


def texto_corrido(falas: list[Fala]) -> str:
    """
    "[09:03] Nome: fala", uma por linha, no horário de Brasília.

    O horário é o da OPERAÇÃO, e não o do servidor: a EC2 roda em UTC, e
    "[12:03]" numa reunião que começou às 9h faria o texto mentir sobre si
    mesmo — a mesma armadilha do fuso que a grade da agenda já pegou.
    """
    linhas = []
    for f in juntar_falas(falas):
        hora = _utc(f.inicio).astimezone(FUSO_OPERACAO).strftime("%H:%M")
        linhas.append(f"[{hora}] {f.participante}: {f.texto}")
    return "\n".join(linhas)


def entradas_json(falas: list[Fala]) -> list[dict]:
    """O que vai para a coluna JSONB `entradas`."""
    return [
        {
            "inicio": _utc(f.inicio).isoformat(),
            "fim": _utc(f.fim).isoformat() if f.fim else None,
            "participante": f.participante,
            "texto": f.texto,
        }
        for f in juntar_falas(falas)
    ]


def nome_do_participante(participante: dict | None) -> str:
    """
    O nome legível de um recurso `participants/*` do Meet.

    Três formas possíveis, uma por tipo de gente: logado numa conta Google,
    anônimo (entrou pelo link sem conta) e por telefone. O cliente costuma
    ser o segundo.
    """
    p = participante or {}
    for chave in ("signedinUser", "anonymousUser", "phoneUser"):
        nome = ((p.get(chave) or {}).get("displayName") or "").strip()
        if nome:
            return nome
    return "Participante"


def recorte_para_ia(texto: str, limite: int = MAX_CARACTERES_IA) -> str:
    """
    O texto inteiro, ou o começo e o fim se passar do limite.

    >>> recorte_para_ia("abc", limite=10)
    'abc'
    >>> r = recorte_para_ia("a" * 50 + "b" * 50, limite=40)
    >>> r.startswith("a" * 20) and r.endswith("b" * 20) and "[trecho do meio omitido]" in r
    True
    """
    if len(texto) <= limite:
        return texto
    metade = limite // 2
    return (
        texto[:metade]
        + "\n\n[trecho do meio omitido]\n\n"
        + texto[-metade:]
    )


# ── Apoio ────────────────────────────────────────────────────────────


def _utc(d: datetime | None) -> datetime:
    if d is None:  # pragma: no cover - chamadores filtram antes
        raise ValueError("data ausente")
    if d.tzinfo is None:
        # Data sem fuso é tratada como UTC: é como a API do Google e o
        # asyncpg (timestamptz) entregam. Nunca como horário local.
        return d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def data_do_google(valor: str | None) -> datetime | None:
    """
    '2026-09-24T12:03:04.123456Z' -> datetime com fuso.

    O Google manda até nove casas de fração de segundo; o `fromisoformat`
    do 3.11 aceita no máximo seis. Corta o excesso em vez de falhar.

    >>> data_do_google("2026-09-24T12:03:04.123456789Z").isoformat()
    '2026-09-24T12:03:04.123456+00:00'
    >>> data_do_google(None) is None
    True
    """
    if not valor:
        return None
    v = valor.strip().replace("Z", "+00:00")
    m = re.match(r"^(.*T\d\d:\d\d:\d\d)(\.\d+)?([+-]\d\d:\d\d)?$", v)
    if m:
        base, frac, tz = m.group(1), m.group(2) or "", m.group(3) or "+00:00"
        v = base + frac[:7] + tz
    return datetime.fromisoformat(v)
