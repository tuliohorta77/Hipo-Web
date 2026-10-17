"""
HIPO -- Contratos: regras do repasse Controller -> Spectre (043).

Funcoes puras, sem banco: rodam no pytest local do Windows.

A conta de cada lancamento (colunas da planilha "SPECTRE MED - CONTROLE
CONTRATOS"):

    K  valor do contrato   = vidas x valor por vida   (cobranca por vida)
                           = valor fixo do mes        (valor de tabela)
    L  repasse             = K x percentual
    N  imposto             = L x aliquota
    O  liquido             = L - N                    <- entra na Spectre

Percentual: 100% no PRIMEIRO mes do contrato (premio de venda) e 30% da
recorrencia depois -- regra do Tulio, 16/10/2026. Os dois ficam no contrato
e podem ser trocados por contrato ou por lancamento.

Valor da nota do mes = soma dos O - descontos combinados com a Controller.

Arredondamento: centavo, meio para cima, em cada etapa -- e o que a nota
fiscal mostra. O e sempre L - N exatos (o banco confere).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MODALIDADES = ("por_vida", "valor_fixo")
STATUS = ("ativo", "encerrado")

PERCENTUAL_REPASSE_PADRAO = Decimal("30")
PERCENTUAL_PRIMEIRO_MES_PADRAO = Decimal("100")
IMPOSTO_PADRAO = Decimal("14.33")

CENTAVO = Decimal("0.01")

MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun",
                "jul", "ago", "set", "out", "nov", "dez"]


class RepasseInvalido(ValueError):
    """Entrada que nao vira lancamento (a API devolve 422)."""


def dinheiro(valor) -> Decimal:
    """Decimal com centavos, meio para cima. None vira zero."""
    if valor is None:
        return Decimal("0.00")
    try:
        return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except InvalidOperation as e:
        raise RepasseInvalido(f"Valor inválido: {valor!r}") from e


def percentual(valor, campo: str = "Percentual") -> Decimal:
    p = dinheiro(valor)
    if p < 0 or p > 100:
        raise RepasseInvalido(f"{campo} precisa ficar entre 0 e 100.")
    return p


# ── Competencia ──────────────────────────────────────────────────────

_RE_COMPETENCIA = re.compile(r"^(\d{4})-(\d{2})$")


def competencia_de_texto(texto: str) -> date:
    """
    'AAAA-MM' -> date do dia 1.

    >>> competencia_de_texto("2026-10")
    datetime.date(2026, 10, 1)
    """
    m = _RE_COMPETENCIA.match((texto or "").strip())
    if not m:
        raise RepasseInvalido("Competência no formato AAAA-MM.")
    ano, mes = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
        raise RepasseInvalido("Competência fora do calendário.")
    return date(ano, mes, 1)


def competencia_de_data(d: date) -> date:
    return date(d.year, d.month, 1)


def competencia_texto(c: date) -> str:
    return f"{c.year:04d}-{c.month:02d}"


def rotulo_competencia(c: date) -> str:
    """
    >>> rotulo_competencia(date(2026, 10, 1))
    'out/2026'
    """
    return f"{MESES_CURTOS[c.month - 1]}/{c.year}"


def somar_meses(c: date, n: int) -> date:
    total = c.year * 12 + (c.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


# ── Percentual do mes ────────────────────────────────────────────────

def eh_primeiro_mes(
    competencia: date,
    primeira_competencia: date | None,
    tem_lancamento_anterior: bool,
) -> bool:
    """
    O mes que leva o premio de venda.

    Contrato que ainda nao teve lancamento (primeira_competencia vazia): o
    primeiro mes e o primeiro lancado -- desde que nao exista lancamento em
    mes anterior. Depois que o primeiro mes foi gravado, so ele.
    """
    if primeira_competencia is not None:
        return competencia == primeira_competencia
    return not tem_lancamento_anterior


def percentual_do_mes(
    primeiro_mes: bool,
    percentual_repasse,
    percentual_primeiro_mes,
) -> Decimal:
    return percentual(percentual_primeiro_mes if primeiro_mes else percentual_repasse)


# ── Calculo ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Calculo:
    valor_contrato: Decimal    # K
    percentual_repasse: Decimal
    valor_repasse: Decimal     # L
    imposto_percentual: Decimal
    valor_imposto: Decimal     # N
    valor_liquido: Decimal     # O

    def como_dict(self) -> dict:
        return {
            "valor_contrato": self.valor_contrato,
            "percentual_repasse": self.percentual_repasse,
            "valor_repasse": self.valor_repasse,
            "imposto_percentual": self.imposto_percentual,
            "valor_imposto": self.valor_imposto,
            "valor_liquido": self.valor_liquido,
        }


def valor_do_contrato(vidas: int, valor_por_vida=None, valor_fixo=None) -> Decimal:
    """
    K. Por vida quando o valor por vida veio; senao o valor fixo.

    >>> valor_do_contrato(181, valor_por_vida="11.50")
    Decimal('2081.50')
    >>> valor_do_contrato(5, valor_fixo=180)
    Decimal('180.00')
    """
    if vidas is None or int(vidas) < 0:
        raise RepasseInvalido("Vidas não pode ser negativo.")
    if valor_por_vida is not None:
        vpv = dinheiro(valor_por_vida)
        if vpv < 0:
            raise RepasseInvalido("Valor por vida não pode ser negativo.")
        return dinheiro(Decimal(int(vidas)) * vpv)
    if valor_fixo is None:
        raise RepasseInvalido("Informe o valor por vida ou o valor fixo do mês.")
    fixo = dinheiro(valor_fixo)
    if fixo < 0:
        raise RepasseInvalido("Valor fixo não pode ser negativo.")
    return fixo


def calcular(valor_contrato, percentual_repasse, imposto_percentual) -> Calculo:
    """
    L, N e O a partir de K.

    Conferido com a planilha (set/2026, SERVCON VIP: 181 vidas a 11,50):
    >>> c = calcular("2081.50", 30, "14.33")
    >>> (c.valor_repasse, c.valor_imposto, c.valor_liquido)
    (Decimal('624.45'), Decimal('89.48'), Decimal('534.97'))
    """
    k = dinheiro(valor_contrato)
    if k < 0:
        raise RepasseInvalido("Valor do contrato não pode ser negativo.")
    pct = percentual(percentual_repasse, "Percentual de repasse")
    imp = percentual(imposto_percentual, "Imposto")
    repasse = dinheiro(k * pct / 100)
    imposto = dinheiro(repasse * imp / 100)
    return Calculo(
        valor_contrato=k,
        percentual_repasse=pct,
        valor_repasse=repasse,
        imposto_percentual=imp,
        valor_imposto=imposto,
        valor_liquido=repasse - imposto,
    )


# ── Fechamento do mes ────────────────────────────────────────────────

def totais(lancamentos: list[dict], descontos: list[dict] | None = None) -> dict:
    """
    Somatorios do mes. valor_nf = soma dos liquidos - descontos.

    >>> t = totais([{"valor_contrato": 100, "valor_repasse": 30,
    ...              "valor_imposto": "4.30", "valor_liquido": "25.70", "pago": True}],
    ...            [{"valor": 5}])
    >>> t["valor_nf"]
    Decimal('20.70')
    """
    soma = {k: Decimal("0.00") for k in
            ("valor_contrato", "valor_repasse", "valor_imposto", "valor_liquido")}
    liquido_pago = Decimal("0.00")
    vidas = 0
    for l in lancamentos:
        for k in soma:
            soma[k] += dinheiro(l.get(k))
        if l.get("pago"):
            liquido_pago += dinheiro(l.get("valor_liquido"))
        vidas += int(l.get("vidas") or 0)
    total_descontos = sum((dinheiro(d.get("valor")) for d in (descontos or [])), Decimal("0.00"))
    return {
        **soma,
        "vidas": vidas,
        "liquido_pago": liquido_pago,
        "descontos": total_descontos,
        "valor_nf": soma["valor_liquido"] - total_descontos,
    }


def contrato_vale_na_competencia(
    competencia: date,
    data_venda: date,
    status: str,
    encerrado_em: date | None,
) -> bool:
    """
    O contrato entra na lista do mes? A partir do mes da venda, ate o mes
    em que foi encerrado (inclusive).
    """
    if competencia < competencia_de_data(data_venda):
        return False
    if status == "encerrado" and encerrado_em is not None:
        return competencia <= competencia_de_data(encerrado_em)
    return True


def proximo_passo(
    competencia: date,
    pendentes: int,
    valor_nf: Decimal,
    nf_numero: str | None,
    recebido_em: date | None,
) -> dict:
    """
    A proxima acao de quem opera a tela (diretriz "proxima tarefa"):
    lancar o que falta, emitir a nota, confirmar o recebimento.
    """
    rotulo = rotulo_competencia(competencia)
    if pendentes:
        s = "" if pendentes == 1 else "s"
        return {
            "acao": "lancar",
            "texto": f"Lançar vidas e valores de {pendentes} contrato{s} de {rotulo}.",
        }
    if not nf_numero:
        valor = f"{dinheiro(valor_nf):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return {
            "acao": "emitir_nf",
            "texto": f"Emitir a nota de R$ {valor} para a Controller ({rotulo}).",
        }
    if recebido_em is None:
        return {
            "acao": "receber",
            "texto": f"Confirmar o recebimento da NF {nf_numero} ({rotulo}).",
        }
    return {"acao": "fechado", "texto": f"{rotulo} fechado: nota emitida e recebida."}


def validar_contrato(
    modalidade: str,
    valor_por_vida,
    valor_fixo,
    percentual_repasse,
    percentual_primeiro_mes,
    imposto_percentual,
) -> None:
    if modalidade not in MODALIDADES:
        raise RepasseInvalido("Modalidade deve ser 'por_vida' ou 'valor_fixo'.")
    if modalidade == "por_vida" and valor_por_vida is None:
        raise RepasseInvalido("Contrato por vida precisa do valor por vida.")
    if modalidade == "valor_fixo" and valor_fixo is None:
        raise RepasseInvalido("Contrato de valor fixo precisa do valor.")
    for v, nome in ((valor_por_vida, "Valor por vida"), (valor_fixo, "Valor fixo")):
        if v is not None and dinheiro(v) < 0:
            raise RepasseInvalido(f"{nome} não pode ser negativo.")
    percentual(percentual_repasse, "Percentual de repasse")
    percentual(percentual_primeiro_mes, "Percentual do primeiro mês")
    percentual(imposto_percentual, "Imposto")
