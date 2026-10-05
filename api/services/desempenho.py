"""
HIPO — Carreira · Desempenho: as regras puras.

A aba Desempenho mostra a cada pessoa o próprio mês: os indicadores do
squad dela (os MESMOS da RPeR, services/rper.py), contra as metas
individuais que a gestão grava em "Metas por squad e pessoa" (tabela
metas_comerciais), mais o funil com as taxas de conversão e o histórico.

Nada de indicador novo aqui. O número de cada pessoa sai de
`rper.CALCULO[squad](dados, [usuario_id])`, a mesma conta do slide da
RPeR: o colaborador vê exatamente o que a gestão vai ver na reunião.

Mês corrente x mês fechado
  * Mês corrente: janela do dia 1º até hoje, e a meta de comparação é a
    META DE HOJE (proporcional aos dias úteis corridos, como no Monitor).
  * Mês fechado: o mês inteiro, contra a meta do mês.
  * Indicador de posição (pipeline, em negociação, contas sob gestão) é
    foto de agora: no mês corrente compara com a meta cheia; no
    histórico não aparece (a foto de hoje não é a do mês passado).

Funções puras, sem banco: o router monta os dados e chama daqui.
"""
from __future__ import annotations

from dataclasses import dataclass

from services import monitor as regras_monitor
from services import rper

# Cargo -> squad da RPeR. Só quem tem squad tem metas e indicadores.
SQUAD_DO_CARGO = {"SDR": "SDR", "EV": "EV", "EC": "EC"}

MESES_HISTORICO = 6


def squad_do_cargo(cargo: str | None) -> str | None:
    return SQUAD_DO_CARGO.get(cargo or "")


# ── Indicadores contra a meta ────────────────────────────────────────

def linhas(
    squad: str,
    bruto: dict,
    metas: dict[str, float],
    *,
    aberto: bool,
    dia_util: int,
    dias_uteis: int,
) -> list[dict]:
    """
    Uma linha por indicador do squad, na ordem da RPeR.

    `metas` é {indicador: valor do mês}. No mês aberto, a comparação é com
    a meta de hoje; `falta_mes` diz quanto falta para a meta cheia (só para
    acumulativo: taxa não "falta").
    """
    saida = []
    for ind in rper.INDICADORES[squad]:
        realizado = bruto.get(ind.chave)
        meta_mes = metas.get(ind.chave)
        if aberto and not ind.posicao:
            meta_ref = regras_monitor.meta_mtd(meta_mes, dia_util, dias_uteis, ind.natureza)
        else:
            meta_ref = float(meta_mes) if meta_mes is not None else None
        ating = regras_monitor.atingimento(realizado, meta_ref, ind.natureza)
        falta = None
        if (meta_mes is not None and ind.natureza == rper.ACUMULATIVO
                and realizado is not None):
            falta = max(0.0, float(meta_mes) - float(realizado))
        saida.append({
            "chave": ind.chave,
            "rotulo": ind.rotulo,
            "formato": ind.formato,
            "natureza": ind.natureza,
            "fonte": ind.fonte,
            "principal": ind.principal,
            "posicao": ind.posicao,
            "realizado": realizado,
            "meta_mes": float(meta_mes) if meta_mes is not None else None,
            "meta_hoje": meta_ref if aberto else None,
            "atingimento": ating,
            "carinha": regras_monitor.carinha(ating),
            "falta_mes": falta,
            "realizado_txt": rper.formatar(realizado, ind.formato),
            "meta_mes_txt": rper.formatar(meta_mes, ind.formato) if meta_mes is not None else "",
            "meta_hoje_txt": (rper.formatar(meta_ref, ind.formato)
                              if aberto and meta_ref is not None else ""),
            "falta_mes_txt": rper.formatar(falta, ind.formato) if falta else "",
        })
    return saida


def ponto_de_atencao(linhas_do_mes: list[dict]) -> dict | None:
    """
    O indicador que mais pede ação agora: o de menor atingimento entre os
    que têm meta, com os principais na frente em caso de empate. É a
    "próxima ação" da tela: em vez de uma tabela para interpretar, uma
    frase sobre onde agir.
    """
    candidatos = [l for l in linhas_do_mes if l["atingimento"] is not None]
    if not candidatos:
        return None
    pior = min(candidatos, key=lambda l: (l["atingimento"], not l["principal"]))
    if pior["atingimento"] >= 1.0:
        return None
    return pior


# ── Funil e taxas de conversão ───────────────────────────────────────

@dataclass(frozen=True)
class Etapa:
    chave: str
    rotulo: str
    # Rótulo da taxa que liga esta etapa à anterior.
    taxa_rotulo: str | None = None


FUNIS: dict[str, tuple[Etapa, ...]] = {
    "SDR": (
        Etapa("tarefas", "Tarefas de prospecção"),
        Etapa("contas", "Empresas contatadas", "das tarefas viraram contato com empresa"),
        Etapa("agendamentos", "Reuniões agendadas", "agendamentos por empresa contatada"),
        Etapa("reunioes_realizadas", "Reuniões realizadas", "das agendadas foram realizadas"),
    ),
    "EV": (
        Etapa("reunioes_realizadas", "Reuniões realizadas"),
        Etapa("propostas", "Propostas", "das reuniões viraram proposta"),
        Etapa("vendas", "Vendas", "das propostas viraram venda"),
    ),
    "EC": (
        Etapa("contas_gestao", "Parceiros na carteira"),
        Etapa("reunioes_carteira", "Reuniões de carteira", "reuniões por parceiro"),
        Etapa("leads", "Indicações recebidas", "indicações por reunião"),
        Etapa("vendas", "Vendas com EC", "das indicações viraram venda"),
    ),
}

# Taxas "por" (podem passar de 100%) saem como razão, não como percentual.
_RAZOES = {"agendamentos", "reunioes_carteira", "leads"}


def funil(squad: str, bruto: dict) -> list[dict]:
    """
    As etapas do funil da função com a taxa de passagem de cada uma.

    É conversão DENTRO do mês: a reunião realizada hoje pode ter sido
    agendada no mês passado. Serve para enxergar onde o funil afina, não
    como coorte exata — a tela diz isso.
    """
    saida = []
    anterior = None
    for etapa in FUNIS[squad]:
        valor = bruto.get(etapa.chave)
        taxa = None
        if anterior is not None and etapa.taxa_rotulo:
            base = anterior or 0
            taxa = (float(valor or 0) / float(base)) if base else None
        if etapa.chave in _RAZOES and taxa is not None:
            taxa_txt = f"{taxa:.1f}".replace(".", ",")
        else:
            taxa_txt = f"{round(taxa * 100)}%" if taxa is not None else "—"
        saida.append({
            "chave": etapa.chave,
            "rotulo": etapa.rotulo,
            "valor": valor,
            "valor_txt": rper.formatar(valor, "inteiro"),
            "taxa": taxa,
            "taxa_txt": taxa_txt if anterior is not None else "",
            "taxa_rotulo": etapa.taxa_rotulo or "",
        })
        anterior = valor
    return saida


# ── Histórico ────────────────────────────────────────────────────────

def ponto_historico(squad: str, ano: int, mes: int, bruto: dict,
                    metas: dict[str, float]) -> dict:
    """Um mês fechado: realizado e atingimento contra a meta do mês."""
    itens = {}
    for ind in rper.INDICADORES[squad]:
        if ind.posicao:
            continue
        realizado = bruto.get(ind.chave)
        meta = metas.get(ind.chave)
        ating = regras_monitor.atingimento(realizado, meta, ind.natureza)
        itens[ind.chave] = {
            "realizado": realizado,
            "realizado_txt": rper.formatar(realizado, ind.formato),
            "meta": meta,
            "atingimento": ating,
            "atingimento_txt": rper.formatar_atingimento(ating) if meta is not None else "",
        }
    return {"ano": ano, "mes": mes, "rotulo": rper.rotulo_mes(ano, mes, com_ano=False),
            "indicadores": itens}


def meses_anteriores(ano: int, mes: int, quantos: int) -> list[tuple[int, int]]:
    """Os `quantos` meses antes de (ano, mes), do mais antigo ao mais novo."""
    saida = []
    a, m = ano, mes
    for _ in range(quantos):
        a, m = rper.mes_anterior(a, m)
        saida.append((a, m))
    return list(reversed(saida))
