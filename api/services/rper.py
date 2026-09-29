"""
HIPO — RPeR: Reunião de Planejamento e Resultados.

Todo primeiro dia útil do mês o time comercial se reúne em cima de um
PowerPoint: o que cada squad (EC, SDR, EV) entregou no mês que fechou e o
que se espera do mês que começa. Até setembro/2026 esse PPT era montado à
mão, a partir de export. Este módulo é a REGRA que faz o HIPO montá-lo.

Funções puras, sem banco e sem rede: rodam no pytest local do Windows. A
coleta (SQL) mora em services/rper_dados.py, o texto da IA em
services/rper_ia.py e o desenho do .pptx em services/rper_render.py.

── O MÊS FECHADO E O MÊS NOVO ───────────────────────────────────────

O RPeR sempre fala de DOIS meses: resultados do mês fechado e
planejamento do seguinte. O parâmetro é o mês FECHADO — é dele que saem
os números, e é por ele que se confere depois ("o RPeR de agosto").

── ITENS, NÃO CONTAGENS ─────────────────────────────────────────────

A coleta devolve LINHAS (cada reunião, cada tarefa, cada venda, com quem
fez), e as contas saem daqui. Por um motivo que não é estético: a meta do
squad não é a soma das metas das pessoas, e o REALIZADO do squad também
não é a soma do realizado das pessoas. Uma venda com dois EVs envolvidos
conta uma vez para cada um e UMA vez para o squad. Só dá para responder
isso certo olhando a linha, deduplicando pelo id — soma de contagens
contaria a venda duas vezes no total do slide.

── POSIÇÃO x FLUXO ──────────────────────────────────────────────────

A maior parte dos indicadores é FLUXO do mês (reunião realizada em
agosto, venda registrada em agosto) e sai igual não importa o dia em que
o RPeR é gerado. Três são POSIÇÃO: contas sob gestão, em negociação e
pipeline. O HIPO não guarda a fase nem o valor de cada oportunidade dia a
dia, então posição é a do momento da geração — e o slide diz isso. Gerado
no 1º dia útil, como o RPeR é, a diferença para "fim do mês" é um dia.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from services import monitor as regras_monitor

__all__ = [
    "SQUADS", "INDICADORES", "POR_SQUAD", "RperInvalido",
    "mes_seguinte", "mes_anterior", "rotulo_mes", "janela_do_mes",
    "validar_squad", "validar_indicador",
    "formatar", "formatar_atingimento", "atingimento",
    "indicadores_sdr", "indicadores_ev", "indicadores_ec", "calcular_squad",
    "primeiro_nome",
]


class RperInvalido(Exception):
    """Entrada inválida (squad ou indicador desconhecido, mês fora da faixa)."""


SQUADS = ("EC", "SDR", "EV")

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

# Naturezas reaproveitadas do Monitor: é a mesma régua de atingimento.
ACUMULATIVO = regras_monitor.ACUMULATIVO
TAXA = regras_monitor.TAXA
TAXA_INVERSA = regras_monitor.TAXA_INVERSA


@dataclass(frozen=True)
class Indicador:
    chave: str
    # Como sai na tabela do slide: caixa alta, curto.
    rotulo: str
    # 'inteiro' | 'moeda' | 'percentual'
    formato: str
    natureza: str
    # Uma linha: de onde o número vem. Vai para a tela de metas e para a
    # nota de rodapé do slide. Número sem procedência vira discussão.
    fonte: str
    # Posição na geração, e não fluxo do mês. Ver o cabeçalho.
    posicao: bool = False
    # Sai na tabela de metas POR PESSOA do planejamento. Duas por squad,
    # como no PPT que a operação já usava — mais que isso não cabe na
    # coluna e ninguém lê.
    principal: bool = False


INDICADORES: dict[str, tuple[Indicador, ...]] = {
    "SDR": (
        Indicador("agendamentos", "AGENDAMENTOS", "inteiro", ACUMULATIVO,
                  "Reuniões de cliente marcadas no mês, pela data em que foram "
                  "marcadas, creditadas a quem agendou.", principal=True),
        Indicador("reunioes_realizadas", "REUNIÕES REALIZADAS", "inteiro", ACUMULATIVO,
                  "Reuniões de cliente do mês (pela data da reunião) que o SDR "
                  "agendou e que foram realizadas.", principal=True),
        Indicador("noshow", "NO-SHOW (%)", "percentual", TAXA_INVERSA,
                  "No-shows sobre as reuniões fechadas que o SDR agendou. "
                  "Quanto menor, melhor."),
        Indicador("leads", "LEADS GERADOS", "inteiro", ACUMULATIVO,
                  "Oportunidades que o SDR passou de Suspect para Lead no mês."),
        Indicador("tarefas", "TAREFAS DE PROSPECÇÃO", "inteiro", ACUMULATIVO,
                  "Tarefas de oportunidade do SDR com prazo no mês, sem as "
                  "canceladas."),
        Indicador("contas", "CONTAS PROSPECTADAS", "inteiro", ACUMULATIVO,
                  "Empresas distintas tocadas por uma tarefa concluída do SDR."),
        Indicador("taxa_execucao", "TAXA DE EXECUÇÃO", "percentual", TAXA,
                  "Tarefas concluídas sobre as tarefas do mês."),
        Indicador("pipeline_gerado", "TICKET GERADO", "moeda", ACUMULATIVO,
                  "Mensalidade das oportunidades que receberam agendamento do "
                  "SDR no mês."),
        Indicador("nmrr", "NMRR GERADO", "moeda", ACUMULATIVO,
                  "Mensalidade das vendas do mês em que o SDR está envolvido."),
    ),
    "EV": (
        Indicador("followups", "FOLLOW-UPS REALIZADOS", "inteiro", ACUMULATIVO,
                  "Tarefas de oportunidade do EV com prazo no mês e concluídas."),
        Indicador("taxa_execucao", "TAXA DE EXECUÇÃO", "percentual", TAXA,
                  "Follow-ups concluídos sobre os follow-ups do mês (sem os "
                  "cancelados)."),
        Indicador("oportunidades", "OPORTUNIDADES TRABALHADAS", "inteiro", ACUMULATIVO,
                  "Oportunidades distintas com follow-up do EV no mês."),
        Indicador("propostas", "PROPOSTAS ENVIADAS", "inteiro", ACUMULATIVO,
                  "Oportunidades que receberam proposta gerada no HIPO no mês, "
                  "pelo executivo da proposta."),
        Indicador("reunioes_realizadas", "REUNIÕES REALIZADAS", "inteiro", ACUMULATIVO,
                  "Reuniões de cliente do mês em que o EV foi o anfitrião e "
                  "que foram realizadas."),
        Indicador("vendas", "VENDAS FECHADAS", "inteiro", ACUMULATIVO,
                  "Oportunidades conquistadas no mês em que o EV está envolvido.",
                  principal=False),
        Indicador("taxa_conversao", "TAXA DE CONVERSÃO", "percentual", TAXA,
                  "Vendas fechadas sobre reuniões realizadas."),
        Indicador("nmrr", "NMRR", "moeda", ACUMULATIVO,
                  "Soma da mensalidade das vendas do mês.", principal=True),
        Indicador("ticket_medio", "TICKET MÉDIO", "moeda", TAXA,
                  "NMRR dividido pelas vendas do mês."),
        Indicador("em_negociacao", "EM NEGOCIAÇÃO", "inteiro", ACUMULATIVO,
                  "Oportunidades ativas na fase Negociação, na posição da "
                  "geração.", posicao=True),
        Indicador("pipeline", "PIPELINE (TICKET MENSAL)", "moeda", ACUMULATIVO,
                  "Mensalidade das oportunidades ativas em Apresentação e "
                  "Negociação, na posição da geração.", posicao=True, principal=True),
    ),
    "EC": (
        Indicador("contas_gestao", "CONTAS SOB GESTÃO", "inteiro", ACUMULATIVO,
                  "Parceiros na carteira do EC, na posição da geração.",
                  posicao=True),
        Indicador("reunioes_carteira", "REUNIÕES DE CARTEIRA", "inteiro", ACUMULATIVO,
                  "Reuniões com parceiro do mês em que o EC foi o anfitrião e "
                  "que foram realizadas.", principal=True),
        Indicador("parcerias", "PARCERIAS NOVAS", "inteiro", ACUMULATIVO,
                  "Parceiros que entraram na carteira do EC no mês."),
        Indicador("leads", "LEADS INDICADOS", "inteiro", ACUMULATIVO,
                  "Oportunidades criadas no mês indicadas por parceiro da "
                  "carteira do EC."),
        Indicador("tarefas", "TAREFAS", "inteiro", ACUMULATIVO,
                  "Tarefas do EC com prazo no mês, sem as canceladas."),
        Indicador("taxa_execucao", "TAXA DE EXECUÇÃO", "percentual", TAXA,
                  "Tarefas concluídas sobre as tarefas do mês."),
        Indicador("vendas", "VENDAS COM EC", "inteiro", ACUMULATIVO,
                  "Oportunidades conquistadas no mês em que o EC está envolvido."),
        Indicador("mrr", "MRR FECHADO", "moeda", ACUMULATIVO,
                  "Soma da mensalidade das vendas do mês em que o EC está "
                  "envolvido.", principal=True),
    ),
}

POR_SQUAD: dict[str, dict[str, Indicador]] = {
    s: {i.chave: i for i in lista} for s, lista in INDICADORES.items()
}

NOME_SQUAD = {
    "EC": "EC — EXECUTIVO DE CONTAS",
    "SDR": "SDR — PROSPECÇÃO",
    "EV": "EV — EXECUTIVOS DE VENDAS",
}


def validar_squad(squad: str) -> str:
    if squad not in SQUADS:
        raise RperInvalido(f"Squad inválido: '{squad}'. Use: {', '.join(SQUADS)}.")
    return squad


def validar_indicador(squad: str, chave: str) -> Indicador:
    validar_squad(squad)
    ind = POR_SQUAD[squad].get(chave)
    if ind is None:
        raise RperInvalido(
            f"Indicador '{chave}' não existe no squad {squad}. Use: "
            f"{', '.join(POR_SQUAD[squad])}."
        )
    return ind


# ── Meses ────────────────────────────────────────────────────────────


def mes_seguinte(ano: int, mes: int) -> tuple[int, int]:
    """
    >>> mes_seguinte(2026, 12)
    (2027, 1)
    >>> mes_seguinte(2026, 8)
    (2026, 9)
    """
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    """
    >>> mes_anterior(2026, 1)
    (2025, 12)
    """
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def rotulo_mes(ano: int, mes: int, *, com_ano: bool = True) -> str:
    """
    >>> rotulo_mes(2026, 8)
    'agosto/2026'
    >>> rotulo_mes(2026, 3, com_ano=False)
    'março'
    """
    nome = MESES[mes - 1]
    return f"{nome}/{ano}" if com_ano else nome


def janela_do_mes(ano: int, mes: int) -> tuple[date, date]:
    """Primeiro e último dia do mês (inclusivos), no calendário."""
    if not 1 <= mes <= 12:
        raise RperInvalido("Mês deve estar entre 1 e 12.")
    return date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])


def primeiro_nome(nome: str | None) -> str:
    """
    O nome que sai no cabeçalho da coluna. Caixa alta, como no PPT.

    >>> primeiro_nome('Jakeline Santana')
    'JAKELINE'
    >>> primeiro_nome(None)
    '—'
    """
    if not nome or not nome.strip():
        return "—"
    return nome.strip().split()[0].upper()


# ── Formatação ───────────────────────────────────────────────────────


def _milhar(inteiro: int) -> str:
    return f"{inteiro:,}".replace(",", ".")


def formatar(valor: float | int | Decimal | None, formato: str) -> str:
    """
    O número como ele aparece no slide.

    Ausência de dado é travessão, não zero: "R$ 0" de ticket médio num mês
    sem venda seria uma afirmação sobre o mês. Mesmo raciocínio do Monitor.

    >>> formatar(18908, 'moeda')
    'R$ 18.908'
    >>> formatar(226.5, 'moeda')
    'R$ 226,50'
    >>> formatar(93.75, 'percentual')
    '94%'
    >>> formatar(33.333, 'percentual')
    '33,3%'
    >>> formatar(10, 'percentual')
    '10%'
    >>> formatar(1234, 'inteiro')
    '1.234'
    >>> formatar(None, 'moeda')
    '—'
    """
    if valor is None:
        return "—"
    v = float(valor)
    if formato == "moeda":
        if abs(v - round(v)) < 0.005:
            return f"R$ {_milhar(int(round(v)))}"
        inteiro, dec = f"{v:.2f}".split(".")
        return f"R$ {_milhar(int(inteiro))},{dec}"
    if formato == "percentual":
        # Uma casa só abaixo de 10% ou quando a casa muda a leitura
        # (33,3% x 33%); acima disso o inteiro basta e cabe na célula.
        if abs(v - round(v)) < 0.05 or v >= 50:
            return f"{int(round(v))}%"
        return f"{v:.1f}".replace(".", ",") + "%"
    return _milhar(int(round(v)))


def atingimento(realizado: float | None, meta: float | None, natureza: str) -> float | None:
    """A mesma régua do Monitor, contra a meta do MÊS INTEIRO (o mês fechou)."""
    return regras_monitor.atingimento(realizado, meta, natureza)


def formatar_atingimento(fracao: float | None) -> str:
    """
    >>> formatar_atingimento(0.935)
    '94%'
    >>> formatar_atingimento(None)
    '—'
    """
    if fracao is None:
        return "—"
    return f"{int(round(fracao * 100))}%"


# ── Contas sobre as linhas ───────────────────────────────────────────


def _pct(parte: int, total: int) -> float | None:
    return regras_monitor.taxa_percentual(parte, total)


def _unicos(linhas: Iterable[dict], chave: str = "id") -> list[dict]:
    """Deduplica pelo id, mantendo a primeira ocorrência (ordem estável)."""
    vistos: set = set()
    saida = []
    for l in linhas:
        k = l[chave]
        if k in vistos:
            continue
        vistos.add(k)
        saida.append(l)
    return saida


def _soma_valor(linhas: Iterable[dict], campo: str = "valor") -> float:
    return float(sum(float(l[campo] or 0) for l in linhas))


def _de(linhas: Iterable[dict], campo: str, pessoas: set) -> list[dict]:
    """Linhas cujo `campo` é uma das pessoas."""
    return [l for l in linhas if l.get(campo) in pessoas]


def _envolvendo(linhas: Iterable[dict], pessoas: set) -> list[dict]:
    """Linhas cujo conjunto `envolvidos` toca alguma das pessoas."""
    return [l for l in linhas if pessoas & set(l.get("envolvidos") or ())]


def _tarefas(linhas: list[dict], pessoas: set, *, so_oportunidade: bool) -> dict:
    minhas = _de(linhas, "responsavel_id", pessoas)
    if so_oportunidade:
        minhas = [t for t in minhas if t.get("oportunidade_id") is not None]
    minhas = _unicos(minhas)
    feitas = [t for t in minhas if t.get("concluida")]
    return {"todas": minhas, "feitas": feitas}


def indicadores_sdr(dados: dict, pessoas: Iterable) -> dict[str, float | None]:
    p = set(pessoas)
    agend = _unicos(_de(dados["agendamentos"], "agendado_por", p))
    reunioes = _unicos([
        r for r in _de(dados["reunioes"], "agendado_por", p)
        if r.get("parceiro_id") is None
    ])
    realizadas = [r for r in reunioes if r["efetivo"] == "realizada"]
    fechadas = [r for r in reunioes if r["efetivo"] in ("realizada", "cancelada", "no_show")]
    no_show = sum(1 for r in fechadas if r["efetivo"] == "no_show")
    tarefas = _tarefas(dados["tarefas"], p, so_oportunidade=True)
    contas = {t["conta_id"] for t in tarefas["feitas"] if t.get("conta_id")}
    opps_agendadas = _unicos(
        [{"id": a["oportunidade_id"], "valor": a.get("valor")}
         for a in agend if a.get("oportunidade_id")]
    )
    vendas = _unicos(_envolvendo(dados["vendas"], p))
    return {
        "agendamentos": len(agend),
        "reunioes_realizadas": len(realizadas),
        "noshow": _pct(no_show, len(fechadas)),
        "leads": len(_unicos(_de(dados["leads"], "usuario_id", p))),
        "tarefas": len(tarefas["todas"]),
        "contas": len(contas),
        "taxa_execucao": _pct(len(tarefas["feitas"]), len(tarefas["todas"])),
        "pipeline_gerado": _soma_valor(opps_agendadas),
        "nmrr": _soma_valor(vendas),
    }


FASES_PIPELINE = ("apresentacao", "negociacao")


def indicadores_ev(dados: dict, pessoas: Iterable) -> dict[str, float | None]:
    p = set(pessoas)
    tarefas = _tarefas(dados["tarefas"], p, so_oportunidade=True)
    opps = {t["oportunidade_id"] for t in tarefas["todas"]}
    propostas = {
        x["oportunidade_id"] for x in _de(dados["propostas"], "executivo_id", p)
    }
    reunioes = _unicos([
        r for r in _de(dados["reunioes"], "anfitriao_id", p)
        if r.get("parceiro_id") is None
    ])
    realizadas = [r for r in reunioes if r["efetivo"] == "realizada"]
    vendas = _unicos(_envolvendo(dados["vendas"], p))
    nmrr = _soma_valor(vendas)
    ativas = _unicos(_envolvendo(dados["ativas"], p))
    negociacao = [o for o in ativas if o["fase"] == "negociacao"]
    pipeline = [o for o in ativas if o["fase"] in FASES_PIPELINE]
    return {
        "followups": len(tarefas["feitas"]),
        "followups_registrados": len(tarefas["todas"]),
        "taxa_execucao": _pct(len(tarefas["feitas"]), len(tarefas["todas"])),
        "oportunidades": len(opps),
        "propostas": len(propostas),
        "reunioes_realizadas": len(realizadas),
        "vendas": len(vendas),
        "taxa_conversao": _pct(len(vendas), len(realizadas)),
        "nmrr": nmrr,
        "ticket_medio": regras_monitor.media(nmrr, len(vendas)),
        "em_negociacao": len(negociacao),
        "pipeline": _soma_valor(pipeline),
        # Apoio ao texto e aos gráficos — não são linhas da tabela.
        "outras_fases": len(ativas) - len(negociacao),
        "pipeline_sem_valor": sum(1 for o in pipeline if not o.get("valor")),
        "pipeline_com_valor": sum(1 for o in pipeline if o.get("valor")),
        "maior_oportunidade": max((float(o["valor"] or 0) for o in pipeline), default=0.0),
    }


def indicadores_ec(dados: dict, pessoas: Iterable) -> dict[str, float | None]:
    p = set(pessoas)
    carteira = _unicos(_de(dados["parceiros"], "ec_id", p))
    reunioes = _unicos([
        r for r in _de(dados["reunioes"], "anfitriao_id", p)
        if r.get("parceiro_id") is not None
    ])
    realizadas = [r for r in reunioes if r["efetivo"] == "realizada"]
    novas = {e["conta_id"] for e in _de(dados["parcerias"], "para_usuario_id", p)}
    indicacoes = _unicos(_de(dados["indicacoes"], "ec_id", p))
    tarefas = _tarefas(dados["tarefas"], p, so_oportunidade=False)
    vendas = _unicos(_envolvendo(dados["vendas"], p))
    return {
        "contas_gestao": len(carteira),
        "reunioes_carteira": len(realizadas),
        "parcerias": len(novas),
        "leads": len(indicacoes),
        "tarefas": len(tarefas["todas"]),
        "taxa_execucao": _pct(len(tarefas["feitas"]), len(tarefas["todas"])),
        "vendas": len(vendas),
        "mrr": _soma_valor(vendas),
    }


CALCULO = {"SDR": indicadores_sdr, "EV": indicadores_ev, "EC": indicadores_ec}


def _linha(ind: Indicador, realizado, meta) -> dict:
    ating = atingimento(realizado, meta, ind.natureza)
    return {
        "chave": ind.chave,
        "rotulo": ind.rotulo,
        "formato": ind.formato,
        "natureza": ind.natureza,
        "posicao": ind.posicao,
        "principal": ind.principal,
        "realizado": realizado,
        "meta": meta,
        "atingimento": ating,
        "realizado_txt": formatar(realizado, ind.formato),
        "meta_txt": formatar(meta, ind.formato) if meta is not None else "",
        "atingimento_txt": formatar_atingimento(ating) if meta is not None else "",
        "carinha": regras_monitor.carinha(ating),
    }


def calcular_squad(
    squad: str,
    dados: dict,
    pessoas: list[dict],
    metas_squad: dict[str, float],
    metas_pessoa: dict[tuple[str, str], float],
) -> dict:
    """
    O squad inteiro do mês fechado: o total (sobre as linhas do squad,
    deduplicadas) e cada pessoa.

    `pessoas` é [{id, nome}] na ordem em que as colunas saem.
    `metas_pessoa` é {(usuario_id, indicador): valor}.
    """
    validar_squad(squad)
    calc = CALCULO[squad]
    ids = [x["id"] for x in pessoas]
    total_bruto = calc(dados, ids)
    total = [
        _linha(i, total_bruto.get(i.chave), metas_squad.get(i.chave))
        for i in INDICADORES[squad]
    ]
    por_pessoa = []
    for pessoa in pessoas:
        bruto = calc(dados, [pessoa["id"]])
        por_pessoa.append({
            "id": pessoa["id"],
            "nome": pessoa["nome"],
            "rotulo": primeiro_nome(pessoa["nome"]),
            "bruto": bruto,
            "indicadores": [
                _linha(i, bruto.get(i.chave),
                       metas_pessoa.get((str(pessoa["id"]), i.chave)))
                for i in INDICADORES[squad]
            ],
        })
    return {
        "squad": squad,
        "nome": NOME_SQUAD[squad],
        "total": total,
        "bruto": total_bruto,
        "pessoas": por_pessoa,
    }


def valor(linhas: list[dict], chave: str) -> Any:
    """O realizado de um indicador numa lista de linhas calculadas."""
    for l in linhas:
        if l["chave"] == chave:
            return l["realizado"]
    return None


def texto(linhas: list[dict], chave: str) -> str:
    for l in linhas:
        if l["chave"] == chave:
            return l["realizado_txt"]
    return "—"


def data_curta(dt: datetime | date | None, fuso=None) -> str:
    """
    dd/mm, para a coluna 'ÚLT. FUP'. Instante com fuso é convertido para o
    fuso da operação antes: 23h de 31/08 em Brasília é 02h de 01/09 em UTC.

    >>> data_curta(date(2026, 8, 31))
    '31/08'
    >>> data_curta(None)
    '—'
    """
    if dt is None:
        return "—"
    if isinstance(dt, datetime) and fuso is not None and dt.tzinfo is not None:
        dt = dt.astimezone(fuso)
    return dt.strftime("%d/%m")


# ── A montagem do RPeR inteiro ───────────────────────────────────────

# Quantas linhas cabem na tabela das maiores negociações. É o "TOP 10" do
# PPT que a operação já usava.
TOP_NEGOCIACOES = 10


def _planejamento(squad: str, pessoas: list[dict], metas_squad: dict,
                  metas_pessoa: dict) -> dict:
    """
    As metas do MÊS NOVO. Linha sem meta sai com a célula vazia, e não
    some: a reunião de planejamento é justamente onde ela é definida, e o
    PPT impresso precisa do espaço para escrever.
    """
    principais = [i for i in INDICADORES[squad] if i.principal]
    if len(principais) < 2:
        # Squad com um só principal completa com o primeiro fluxo que não
        # é principal, para a tabela por pessoa ter sempre duas colunas.
        extra = next(i for i in INDICADORES[squad] if not i.principal and not i.posicao)
        principais = principais + [extra]
    time = [
        {
            "rotulo": i.rotulo,
            "meta_txt": formatar(metas_squad.get(i.chave), i.formato)
            if i.chave in metas_squad else "",
        }
        for i in INDICADORES[squad]
        if not i.posicao or i.chave in metas_squad
    ]
    por_pessoa = [
        {
            "rotulo": primeiro_nome(p["nome"]),
            "metas": [
                formatar(metas_pessoa.get((str(p["id"]), i.chave)), i.formato)
                if (str(p["id"]), i.chave) in metas_pessoa else ""
                for i in principais[:2]
            ],
        }
        for p in pessoas
    ]
    return {
        "time": time,
        "colunas": [i.rotulo.split(" (")[0] for i in principais[:2]],
        "pessoas": por_pessoa,
        "tem_meta": bool(metas_squad) or bool(metas_pessoa),
    }


def _top_negociacoes(dados: dict, evs: list[dict]) -> list[dict]:
    nomes = {p["id"]: primeiro_nome(p["nome"]).capitalize() for p in evs}
    ids = set(nomes)
    abertas = [
        o for o in _unicos(_envolvendo(dados["ativas"], ids))
        if o["fase"] == "negociacao"
    ]
    abertas.sort(key=lambda o: (-(float(o["valor"] or 0)), o["empresa"] or ""))
    saida = []
    for o in abertas[:TOP_NEGOCIACOES]:
        execs = [nomes[u] for u in (o.get("envolvidos") or ()) if u in nomes]
        saida.append({
            "id": o["id"],
            "numero": o["numero"],
            "empresa": o["empresa"],
            "executivo": " / ".join(sorted(execs)) or "—",
            "ultimo_fup": o.get("ultimo_fup"),
            "valor": float(o["valor"]) if o["valor"] is not None else None,
        })
    return saida


def _pendencias(dados: dict, pessoas: list[dict], agora: datetime) -> dict:
    """
    O que está em aberto AGORA, por pessoa: tarefas atrasadas e reuniões
    do mês que terminaram sem desfecho. É o material do "Ações do mês" —
    ação concreta sobre item concreto, não meta inventada.
    """
    saida = {}
    for p in pessoas:
        sem_desfecho = sum(
            1 for r in dados["reunioes"]
            if r["anfitriao_id"] == p["id"] and r["efetivo"] is None
            and r["inicio"] < agora
        )
        saida[str(p["id"])] = {
            "nome": p["nome"],
            "tarefas_atrasadas": int(dados["atrasadas"].get(p["id"], 0)),
            "reunioes_sem_desfecho": sem_desfecho,
        }
    return saida


def montar(
    *,
    ano: int,
    mes: int,
    dados: dict,
    pessoas: dict[str, list[dict]],
    metas_fechado: dict,
    metas_novo: dict,
    agora: datetime,
) -> dict:
    """
    O RPeR inteiro, pronto para o texto e para o desenho.

    `metas_*` são o formato de rper_dados.metas; o recorte por squad é
    feito aqui para esta função continuar pura.
    """
    ano_novo, mes_novo = mes_seguinte(ano, mes)
    squads = {}
    for s in SQUADS:
        ms = {ind: v for (sq, ind), v in metas_fechado["squad"].items() if sq == s}
        mp = {(u, ind): v for (sq, u, ind), v in metas_fechado["pessoa"].items() if sq == s}
        ns = {ind: v for (sq, ind), v in metas_novo["squad"].items() if sq == s}
        np_ = {(u, ind): v for (sq, u, ind), v in metas_novo["pessoa"].items() if sq == s}
        resultado = calcular_squad(s, dados, pessoas[s], ms, mp)
        resultado["planejamento"] = _planejamento(s, pessoas[s], ns, np_)
        resultado["pendencias"] = _pendencias(dados, pessoas[s], agora)
        squads[s] = resultado

    top = _top_negociacoes(dados, pessoas["EV"])
    ev = squads["EV"]
    pipeline_total = float(ev["bruto"]["pipeline"] or 0)
    soma_top = float(sum(o["valor"] or 0 for o in top))
    dois = top[:2]
    soma_dois = float(sum(o["valor"] or 0 for o in dois))
    ev["negociacoes"] = {
        "top": top,
        "soma_top": soma_top,
        "abertas": ev["bruto"]["em_negociacao"],
        # Quanto do pipeline as duas maiores negociações representam. Conta
        # feita AQUI, e não pela IA: percentual é exatamente o que a guarda
        # numérica proíbe o modelo de calcular.
        "dois_maiores": [o["empresa"] for o in dois],
        "dois_maiores_pct": (round(soma_dois * 100 / pipeline_total)
                             if pipeline_total > 0 and dois else None),
    }
    ev["graficos"] = {
        "nomes": [p["rotulo"] for p in ev["pessoas"]],
        "em_negociacao": [p["bruto"]["em_negociacao"] for p in ev["pessoas"]],
        "concluidas": [p["bruto"]["vendas"] for p in ev["pessoas"]],
        "outras_fases": [p["bruto"]["outras_fases"] for p in ev["pessoas"]],
        "pipeline": [float(p["bruto"]["pipeline"] or 0) for p in ev["pessoas"]],
    }
    for p in ev["pessoas"]:
        pip = float(p["bruto"]["pipeline"] or 0)
        maior = float(p["bruto"]["maior_oportunidade"] or 0)
        p["concentracao_pct"] = round(maior * 100 / pip) if pip > 0 else None

    return {
        "ano": ano,
        "mes": mes,
        "ano_novo": ano_novo,
        "mes_novo": mes_novo,
        "rotulo_fechado": rotulo_mes(ano, mes),
        "rotulo_novo": rotulo_mes(ano_novo, mes_novo),
        "gerado_em": agora,
        "squads": squads,
    }


# ── Texto padrão (sem IA) ────────────────────────────────────────────
#
# É o que sai quando a IA não está configurada, falha, ou escreve um número
# que não existe nos dados. Frases curtas e só com números que já estão nos
# slides: o texto padrão não pode ser pior do que nenhum texto.


def _fatos_pessoa(squad: str, p: dict) -> str:
    b = p["bruto"]
    if squad == "SDR":
        return (
            f"{formatar(b['agendamentos'], 'inteiro')} agendamentos, "
            f"{formatar(b['reunioes_realizadas'], 'inteiro')} reuniões realizadas e "
            f"{formatar(b['tarefas'], 'inteiro')} tarefas de prospecção "
            f"(execução {formatar(b['taxa_execucao'], 'percentual')})."
        )
    if squad == "EV":
        frase = (
            f"{formatar(b['followups'], 'inteiro')} follow-ups realizados "
            f"(execução {formatar(b['taxa_execucao'], 'percentual')}), "
            f"{formatar(b['vendas'], 'inteiro')} vendas e pipeline de "
            f"{formatar(b['pipeline'], 'moeda')}."
        )
        if p.get("concentracao_pct") and p["concentracao_pct"] >= 50:
            frase += (
                f" A maior oportunidade responde por {p['concentracao_pct']}% "
                "do pipeline."
            )
        return frase
    return (
        f"{formatar(b['contas_gestao'], 'inteiro')} parceiros na carteira, "
        f"{formatar(b['reunioes_carteira'], 'inteiro')} reuniões de carteira e "
        f"{formatar(b['mrr'], 'moeda')} em vendas com EC."
    )


def _acoes_padrao(squad: str, s: dict) -> list[str]:
    acoes = []
    atrasadas = sum(x["tarefas_atrasadas"] for x in s["pendencias"].values())
    sem = sum(x["reunioes_sem_desfecho"] for x in s["pendencias"].values())
    if atrasadas:
        acoes.append(f"Zerar as {formatar(atrasadas, 'inteiro')} tarefas atrasadas em aberto")
    if sem:
        acoes.append(f"Registrar o desfecho das {formatar(sem, 'inteiro')} reuniões pendentes")
    if squad == "EV":
        neg = s["negociacoes"]
        if neg["dois_maiores"]:
            acoes.append("Priorizar " + " e ".join(neg["dois_maiores"]))
        sem_valor = s["bruto"]["pipeline_sem_valor"]
        if sem_valor:
            acoes.append(
                f"Preencher a mensalidade das {formatar(sem_valor, 'inteiro')} "
                "oportunidades sem valor"
            )
    if not acoes:
        acoes.append("Manter a cadência de follow-up do mês")
    return acoes[:5]


def textos_padrao(rper: dict) -> dict:
    """Os textos de todos os slides, por regra. Mesmo formato da IA."""
    saida = {}
    for squad, s in rper["squads"].items():
        t = s["total"]
        if squad == "SDR":
            leitura = (
                f"O squad fez {texto(t, 'agendamentos')} agendamentos e "
                f"{texto(t, 'reunioes_realizadas')} reuniões realizadas, com "
                f"no-show de {texto(t, 'noshow')}. Foram "
                f"{texto(t, 'tarefas')} tarefas de prospecção em "
                f"{texto(t, 'contas')} contas."
            )
        elif squad == "EV":
            leitura = (
                f"{texto(t, 'vendas')} vendas somando {texto(t, 'nmrr')} de NMRR, "
                f"{texto(t, 'propostas')} propostas enviadas e "
                f"{texto(t, 'em_negociacao')} negociações abertas, com "
                f"{texto(t, 'pipeline')} de pipeline."
            )
        else:
            leitura = (
                f"{texto(t, 'contas_gestao')} parceiros sob gestão, "
                f"{texto(t, 'reunioes_carteira')} reuniões de carteira e "
                f"{texto(t, 'leads')} leads indicados. Vendas com EC somaram "
                f"{texto(t, 'mrr')}."
            )
        item = {
            "leitura": leitura,
            "pessoas": {str(p["id"]): _fatos_pessoa(squad, p) for p in s["pessoas"]},
            "acoes": _acoes_padrao(squad, s),
        }
        if squad == "EV":
            neg = s["negociacoes"]
            if neg["dois_maiores"] and neg["dois_maiores_pct"] is not None:
                item["foco"] = (
                    f"Fechar {' e '.join(neg['dois_maiores'])} vale "
                    f"{neg['dois_maiores_pct']}% do pipeline dos EVs."
                )
            else:
                item["foco"] = "Sem negociações abertas com valor."
            nomes = s["graficos"]["nomes"]
            valores = s["graficos"]["pipeline"]
            item["pipeline"] = "  ·  ".join(
                f"{n}: {formatar(v, 'moeda')}" for n, v in zip(nomes, valores)
            ) or "Sem executivos de vendas ativos."
        saida[squad] = item
    return saida


def base_de_partida(squad: str, s: dict) -> str:
    """A linha 'BASE DE PARTIDA' do planejamento: os números do mês fechado."""
    t = s["total"]
    if squad == "SDR":
        return (
            f"{texto(t, 'tarefas')} tarefas de prospecção  ·  {texto(t, 'contas')} contas"
            f"  ·  {texto(t, 'agendamentos')} agendamentos  ·  "
            f"{texto(t, 'reunioes_realizadas')} reuniões realizadas"
        )
    if squad == "EV":
        return (
            f"{texto(t, 'propostas')} propostas  ·  {texto(t, 'em_negociacao')} negociações"
            f"  ·  {texto(t, 'pipeline')} de pipeline  ·  {texto(t, 'nmrr')} de NMRR"
        )
    return (
        f"{texto(t, 'contas_gestao')} parceiros  ·  {texto(t, 'reunioes_carteira')} "
        f"reuniões de carteira  ·  {texto(t, 'mrr')} em vendas com EC"
    )
