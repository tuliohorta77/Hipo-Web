"""
HIPO — Monitor: o painel de parede da operacao.

Dez indicadores com meta e resultado do MES CORRENTE, cada um com uma
carinha. Fica aberto numa TV o dia inteiro e se atualiza sozinho.

Funcoes puras, sem banco e sem rede: rodam no pytest local do Windows. O
router monta as consultas; as REGRAS (o que e MTD, como se compara com a
meta, qual carinha aparece) moram aqui.

── POR QUE A META E MTD ─────────────────────────────────────────────

A meta do mes inteiro comparada com o resultado de hoje diz que todo dia 2
esta tudo vermelho. O que responde "estamos no ritmo?" e a meta
proporcional aos DIAS UTEIS JA CORRIDOS:

    meta_mtd = meta_mensal * dia_util_atual / dias_uteis_do_mes

Dia util sai de services/dias_uteis.py, que desconta sabado, domingo e a
tabela `dia_nao_util` — e e por isso que o painel tem um campo de feriados:
sem ele, um mes com tres feriados cobraria ritmo de mes cheio.

── ACUMULATIVO, TAXA E TAXA INVERSA ─────────────────────────────────

Nem todo indicador acumula. Leads, reunioes e contratos somam ao longo do
mes, e por isso a meta deles e proporcional ao mes corrido. Ja "% de
no-show" e "ticket medio" sao TAXAS: 11% de no-show no dia 5 e 11% de
no-show no dia 25 valem o mesmo, e proporcionalizar a meta deles produziria
"meta de 3% de no-show" no comeco do mes — um numero sem significado.

No-show ainda e INVERSO: bater a meta e ficar ABAIXO dela. Por isso o
atingimento dele e `meta / resultado`, e nao o contrario.

── A CARINHA ────────────────────────────────────────────────────────

Regua definida pelo Tulio (17/09), sobre o atingimento da meta MTD:

    >= 110%  muito feliz
    >= 100%  feliz
    >=  70%  neutra
    >=  50%  triste
    <   50%  bravo

Indicador sem meta ou sem fonte de dado (o caso do treinamento, que nao
existe neste negocio ainda) nao ganha carinha: carinha sobre denominador
inventado e pior do que celula vazia.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "INDICADORES", "POR_CHAVE", "CHAVES", "ACUMULATIVO", "TAXA", "TAXA_INVERSA",
    "ABERTO", "CARINHAS", "MonitorInvalido",
    "meta_mtd", "atingimento", "carinha", "media",
]


class MonitorInvalido(Exception):
    """Entrada invalida no painel (indicador desconhecido, meta negativa...)."""


# Naturezas. String e nao enum porque atravessa JSON e CHECK de banco.
ACUMULATIVO = "acumulativo"
TAXA = "taxa"
TAXA_INVERSA = "taxa_inversa"
ABERTO = "aberto"

NATUREZAS = (ACUMULATIVO, TAXA, TAXA_INVERSA, ABERTO)


@dataclass(frozen=True)
class Indicador:
    chave: str
    # O que aparece no alto do quadro, em caixa alta e curto: e uma TV vista
    # de longe, e "Reunioes de parceria" nao cabe em 5 colunas.
    sigla: str
    rotulo: str
    natureza: str
    # 'inteiro' | 'moeda' | 'percentual'
    formato: str
    ordem: int
    # Uma linha explicando de onde o numero vem. Vai para o title do quadro:
    # painel de parede sem procedencia vira discussao sobre o numero.
    fonte: str


INDICADORES: tuple[Indicador, ...] = (
    Indicador(
        "lead", "LEAD", "Leads novos", ACUMULATIVO, "inteiro", 10,
        "Oportunidades que passaram de Suspect para Lead no mes.",
    ),
    Indicador(
        "agen", "AGEN", "Reunioes no mes", ACUMULATIVO, "inteiro", 20,
        "Reunioes com cliente marcadas para o mes (pela data da reuniao), "
        "menos as desmarcadas. Parceria nao entra.",
    ),
    Indicador(
        "apre", "APRE", "Reunioes realizadas", ACUMULATIVO, "inteiro", 30,
        "Reunioes com cliente e desfecho Realizada, pela data da reuniao. "
        "Parceria nao entra.",
    ),
    Indicador(
        "nmrr", "NMRR", "Mensalidade nova", ACUMULATIVO, "moeda", 40,
        "Soma da mensalidade das oportunidades conquistadas no mes.",
    ),
    Indicador(
        "ticket_medio", "TICK MED", "Ticket medio", TAXA, "moeda", 50,
        "NMRR dividido pelos contratos do mes.",
    ),
    Indicador(
        "reunioes_parceria", "PARCERIAS", "Reunioes de parceria", ACUMULATIVO,
        "inteiro", 60,
        "Reunioes com parceiro (modulo Parceiros) com desfecho Realizada. "
        "E o unico quadro onde parceria aparece.",
    ),
    Indicador(
        "agendamentos_mes", "AGEND MES", "Agendamentos feitos", ACUMULATIVO,
        "inteiro", 70,
        "Reunioes com cliente AGENDADAS no mes, pela data em que foram "
        "marcadas. Parceria nao entra.",
    ),
    Indicador(
        "noshow", "% NOSHOW", "No-show", TAXA_INVERSA, "percentual", 80,
        "No-shows de cliente sobre as reunioes de cliente ja fechadas no mes. "
        "Parceria fica fora dos dois lados. Quanto menor, melhor.",
    ),
    Indicador(
        "contratos", "CONTRATOS", "Contratos fechados", ACUMULATIVO, "inteiro", 90,
        "Oportunidades conquistadas no mes.",
    ),
    Indicador(
        "treinamento", "TREINAMENTO", "Treinamento", ABERTO, "inteiro", 100,
        "Ainda sem fonte de dado neste negocio — o quadro fica reservado.",
    ),
)

POR_CHAVE = {i.chave: i for i in INDICADORES}
CHAVES = tuple(i.chave for i in INDICADORES)

# As cinco carinhas, da pior para a melhor, com o piso de atingimento de
# cada uma. Lida de baixo para cima em `carinha`.
CARINHAS = (
    ("bravo", 0.0),
    ("triste", 0.50),
    ("neutro", 0.70),
    ("feliz", 1.00),
    ("muito_feliz", 1.10),
)


def validar_indicador(chave: str) -> str:
    if chave not in POR_CHAVE:
        raise MonitorInvalido(
            f"Indicador invalido: '{chave}'. Use: {', '.join(CHAVES)}."
        )
    return chave


def meta_mtd(
    meta: float | None,
    dia_util_atual: int,
    dias_uteis: int,
    natureza: str = ACUMULATIVO,
) -> float | None:
    """
    A meta que valia para HOJE.

    Acumulativo: proporcional aos dias uteis corridos. Taxa: a propria meta
    — 11% de no-show nao "acumula" ao longo do mes.

    >>> meta_mtd(276, 5, 20)
    69.0
    >>> meta_mtd(30, 5, 20, TAXA_INVERSA)
    30.0
    >>> meta_mtd(None, 5, 20) is None
    True
    >>> meta_mtd(276, 0, 0)
    0.0
    """
    if meta is None:
        return None
    if natureza in (TAXA, TAXA_INVERSA):
        return float(meta)
    if dias_uteis <= 0:
        # Mes inteiro sem dia util (so acontece com a tabela de feriados
        # errada): meta de hoje e zero, e nao a do mes cheio — cobrar ritmo
        # de mes cheio num mes que o sistema acha que nao existe seria pior.
        return 0.0
    return float(meta) * max(0, min(dia_util_atual, dias_uteis)) / dias_uteis


def atingimento(
    resultado: float | None,
    meta: float | None,
    natureza: str = ACUMULATIVO,
) -> float | None:
    """
    Quanto da meta foi atingido, como fracao (1.0 = 100%).

    None quando nao da para responder: sem meta, sem resultado, ou
    indicador aberto. `None` e informacao — e o que faz o quadro aparecer
    sem carinha em vez de exibir 0%.

    >>> atingimento(69, 69)
    1.0
    >>> atingimento(11, 30, TAXA_INVERSA) > 2
    True
    >>> atingimento(40, 30, TAXA_INVERSA)
    0.75
    >>> atingimento(5, 0) is None
    True
    """
    if natureza == ABERTO or resultado is None or meta is None:
        return None
    meta = float(meta)
    resultado = float(resultado)
    if natureza == TAXA_INVERSA:
        if meta <= 0:
            return None
        if resultado <= 0:
            # Zero no-show e o melhor resultado possivel. Sem este ramo a
            # divisao estouraria, e o mes perfeito apareceria sem carinha.
            return 2.0
        return meta / resultado
    if meta <= 0:
        return None
    return resultado / meta


def carinha(valor: float | None) -> str | None:
    """
    A carinha do atingimento.

    >>> carinha(1.2)
    'muito_feliz'
    >>> carinha(1.0)
    'feliz'
    >>> carinha(0.75)
    'neutro'
    >>> carinha(0.5)
    'triste'
    >>> carinha(0.2)
    'bravo'
    >>> carinha(None) is None
    True
    """
    if valor is None:
        return None
    escolhida = CARINHAS[0][0]
    for nome, piso in CARINHAS:
        if valor >= piso:
            escolhida = nome
    return escolhida


def media(total: float | None, quantidade: int | None) -> float | None:
    """
    Divisao que devolve None em vez de estourar — ticket medio sem contrato
    nenhum e indefinido, nao zero. "R$ 0" seria uma afirmacao sobre o mes.

    >>> media(4500, 10)
    450.0
    >>> media(4500, 0) is None
    True
    """
    if not quantidade or total is None:
        return None
    return float(total) / quantidade


def taxa_percentual(parte: int, total: int) -> float | None:
    """
    Percentual de `parte` sobre `total`, ou None sem denominador.

    Mes sem reuniao fechada tem no-show INDEFINIDO, nao 0% — e "0%" descreve
    um mes bom de verdade.

    >>> taxa_percentual(3, 27)
    11.1
    >>> taxa_percentual(0, 0) is None
    True
    """
    if total <= 0:
        return None
    return round(parte * 100 / total, 1)
