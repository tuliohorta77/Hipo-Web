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
from services import roteiro_scorecard as sc
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


# ── Scorecard das reuniões (só EV) ───────────────────────────────────
#
# A nota do roteiro de vendas (services/roteiro_scorecard.py, 0 a 20) das
# reuniões que a pessoa CONDUZIU no mês. É a mesma conta do quadro
# SCORECARD do Monitor, recortada pela pessoa:
#   * reunião de cliente (parceiro é ilha, não tem scorecard), desfecho
#     efetivo Realizada, pela data da reunião, com a pessoa de anfitriã
#     (tarefas.responsavel_id) — o mesmo critério do APRE e da RPeR;
#   * só conta avaliação PRONTA da versão CORRENTE do roteiro;
#   * reunião realizada ainda sem nota fica FORA da média (zero seria uma
#     nota que ninguém deu);
#   * meta: a do quadro SCORECARD do Monitor no mês, ou 15 (o padrão do
#     roteiro). Taxa: média 15 no dia 5 vale o mesmo que no dia 25.

SQUADS_COM_SCORECARD = {"EV"}

# Item com média abaixo disto vira o foco de treino do mês.
LIMIAR_ITEM_FRACO = 1.5


def tem_scorecard(squad: str | None) -> bool:
    return squad in SQUADS_COM_SCORECARD


def nota_da_reuniao(r: dict) -> tuple[float | None, str | None]:
    """
    A nota e a situação do scorecard de uma reunião. Mesma regra de
    `routers/monitor._nota`: 'ia' | 'validada' | 'avaliando' | 'erro' | None.
    """
    status = r.get("av_status")
    if status is None:
        return None, None
    if status == "aguardando":
        return None, "avaliando"
    if status == "erro":
        return None, "erro"
    if r.get("av_versao") != sc.VERSAO or r.get("av_nota") is None:
        return None, None
    return float(r["av_nota"]), ("validada" if r.get("av_validada") else "ia")


def _num(valor: float | None, casas: int = 1) -> str:
    if valor is None:
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def media_scorecard(reunioes: list[dict]) -> tuple[float | None, int]:
    """A média (uma casa) das reuniões com nota, e quantas eram."""
    notas = [n for n, _ in (nota_da_reuniao(r) for r in reunioes) if n is not None]
    if not notas:
        return None, 0
    return round(sum(notas) / len(notas), 1), len(notas)


def medias_por_item(itens_por_reuniao: dict, reunioes_com_nota: list) -> list[dict]:
    """
    A média de cada um dos 10 itens (0 a 2) nas reuniões que entram na
    média. Item sem nota numa reunião avaliada conta 0, como na `nota_total`
    (é o descartado por falta de trecho, até a gestão dar a nota).
    """
    saida = []
    n = len(reunioes_com_nota)
    for item in sc.ITENS:
        if n:
            soma = sum(
                float((itens_por_reuniao.get(rid) or {}).get(item.numero) or 0)
                for rid in reunioes_com_nota
            )
            media = round(soma / n, 2)
        else:
            media = None
        saida.append({
            "item": item.numero,
            "nome": item.nome,
            "etapa": item.etapa,
            "media": media,
            "media_txt": _num(media),
            "fracao": (media / sc.NOTA_MAXIMA_ITEM) if media is not None else None,
        })
    return saida


def item_mais_fraco(itens: list[dict]) -> dict | None:
    """O item de menor média, se estiver abaixo do limiar; empate fica o
    primeiro do roteiro (é o que vem antes na reunião)."""
    candidatos = [i for i in itens if i["media"] is not None]
    if not candidatos:
        return None
    pior = min(candidatos, key=lambda i: (i["media"], i["item"]))
    return pior if pior["media"] < LIMIAR_ITEM_FRACO else None


def scorecard(
    reunioes: list[dict],
    itens_por_reuniao: dict,
    meta: float | None,
    *,
    meta_padrao: bool,
) -> dict:
    """
    O bloco Scorecard do Desempenho.

    `reunioes`: as realizadas de cliente da pessoa no mês, já com o
    desfecho efetivo filtrado, mais recente primeiro, com `av_*`,
    `foco_proxima`, `empresa`, `inicio`, `reuniao_id`, `oportunidade_numero`.
    `itens_por_reuniao`: {reuniao_id: {item: nota}} das que têm nota.
    """
    media, avaliadas = media_scorecard(reunioes)
    ating = regras_monitor.atingimento(media, meta, regras_monitor.TAXA)

    lista = []
    com_nota = []
    foco = None
    for r in reunioes:
        nota, status = nota_da_reuniao(r)
        if nota is not None:
            com_nota.append(r["reuniao_id"])
            if foco is None and r.get("foco_proxima"):
                foco = {
                    "texto": r["foco_proxima"],
                    "reuniao_id": str(r["reuniao_id"]),
                    "empresa": r.get("empresa"),
                    "data": r["inicio"].isoformat() if r.get("inicio") else None,
                }
        lista.append({
            "reuniao_id": str(r["reuniao_id"]),
            "data": r["inicio"].isoformat() if r.get("inicio") else None,
            "empresa": r.get("empresa"),
            "oportunidade_numero": r.get("oportunidade_numero"),
            "nota": nota,
            "nota_status": status,
            "faixa": sc.faixa(nota),
        })

    itens = medias_por_item(itens_por_reuniao, com_nota)
    return {
        "media": media,
        "media_txt": _num(media),
        "nota_maxima": sc.NOTA_MAXIMA,
        "avaliadas": avaliadas,
        "realizadas": len(reunioes),
        "sem_nota": len(reunioes) - avaliadas,
        "meta": meta,
        "meta_txt": _num(meta) if meta is not None else "",
        "meta_padrao": meta_padrao,
        "atingimento": ating,
        "carinha": regras_monitor.carinha(ating),
        "faixa": sc.faixa(media),
        "itens": itens,
        "item_fraco": item_mais_fraco(itens),
        "foco": foco,
        "reunioes": lista,
    }


def ponto_scorecard(ano: int, mes: int, reunioes: list[dict]) -> dict:
    """Um mês do histórico do scorecard: só a média e quantas reuniões."""
    media, avaliadas = media_scorecard(reunioes)
    return {
        "ano": ano, "mes": mes,
        "rotulo": rper.rotulo_mes(ano, mes, com_ano=False),
        "media": media, "media_txt": _num(media), "avaliadas": avaliadas,
        "faixa": sc.faixa(media),
    }
