"""
HIPO — Regras da proposta comercial.

Funções puras: sem banco, sem I/O, sem `date.today()` escondido. Toda data
entra como parâmetro — mesmo padrão de services/tarefa.py e services/
dias_uteis.py, e o que permite testar validade e valores sem mockar o
relógio. (A armadilha do fuso está documentada em claude/armadilhas-deploy-
e-fuso.md: teste que pergunta "que dia é hoje" ao relógio da máquina fica
verde 21 horas por dia.)

O que mora aqui:

  * o escopo padrão da Controller MedSeg, que é o que 90% das propostas
    usam sem tocar;
  * a aritmética do investimento, que é simples mas estava sendo feita na
    cabeça do vendedor a cada proposta — e mensalidade errada em proposta
    enviada é desconto que ninguém aprovou;
  * a formatação pt-BR de dinheiro e data, porque o modelo é um .pptx e o
    que entra nele é string, não número.

O preenchimento do arquivo em si está em services/proposta_render.py: aqui
não se abre arquivo nenhum.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

# Os seis itens que o modelo já trazia impressos. Viram sugestão marcada no
# formulário — o vendedor desmarca o que não vendeu e acrescenta o que for
# específico daquele cliente.
ESCOPO_PADRAO = [
    "Programa de Gerenciamento de Riscos: PGR - (NR-01)",
    "Implantação de Fatores de Riscos Psicossociais (NR-01)",
    "PCMSO – Programa de Controle de Medicina e Saúde Ocupacional - (NR-07)",
    "Exames Clinicos (Admissional, Demissional, Periódico, Mudança de Risco e "
    "Retorno ao Trabalho)",
    "Envio de eventos SST 2240 e 2220 para o eSocial",
    "LTCAT (Laudo Técnico das Condições do Ambiente de Trabalho): (NR-15)",
]

# Dez dias corridos entre a data da proposta e o vencimento — é o que o
# modelo trazia (26/08 -> 05/09) e vira o padrão do formulário. O campo é
# editável: prazo de validade é argumento de negociação, não constante.
DIAS_VALIDADE_PADRAO = 10

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# A unidade onde a proposta é assinada. Sai no slide de fechamento, antes da
# data ("Guarulhos, 26 de agosto de 2026").
CIDADE_PADRAO = "Guarulhos"

MAX_ITENS_ESCOPO = 20
MAX_VIDAS = 100_000


class PropostaInvalida(ValueError):
    """Erro de regra, com mensagem pronta para o usuário ler."""


# ── Formatação ───────────────────────────────────────────────────────

def moeda(valor: Decimal | int | float | None) -> str:
    """
    Formata em Real, no padrão brasileiro.

    >>> moeda(Decimal("1000"))
    'R$ 1.000,00'
    >>> moeda(Decimal("20"))
    'R$ 20,00'
    >>> moeda(None)
    'R$ 0,00'

    Feito na mão em vez de `locale`: o locale pt_BR não vem instalado no
    contêiner do CI nem, necessariamente, na EC2 — e `locale.setlocale` é
    estado global de processo, que numa API async vaza entre requests.
    """
    if valor is None:
        valor = Decimal(0)
    v = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, centavos = f"{abs(v):.2f}".split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    sinal = "-" if v < 0 else ""
    return f"{sinal}R$ {'.'.join(grupos)},{centavos}"


def data_extenso(d: date) -> str:
    """
    >>> data_extenso(date(2026, 8, 26))
    '26 de agosto de 2026'
    """
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def data_curta(d: date) -> str:
    """
    >>> data_curta(date(2026, 9, 5))
    '05/09/2026'
    """
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


# ── Aritmética do investimento ───────────────────────────────────────

def mensalidade(vidas: int, valor_por_vida: Decimal) -> Decimal:
    """
    Mensalidade = vidas x valor por vida.

    Derivada, nunca digitada. Deixar o vendedor digitar os dois abriria a
    porta para proposta com 50 vidas a R$ 20,00 e mensalidade de R$ 900 —
    e o cliente cobra o que está escrito.
    """
    return (Decimal(vidas) * Decimal(valor_por_vida)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def investimento(
    mensal: Decimal,
    treinamentos: Decimal = Decimal(0),
    laudos: Decimal = Decimal(0),
) -> Decimal:
    """Total do quadro de investimento: mensalidade + treinamentos + laudos."""
    total = Decimal(mensal) + Decimal(treinamentos or 0) + Decimal(laudos or 0)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validade_padrao(data_proposta: date, dias: int = DIAS_VALIDADE_PADRAO) -> date:
    """
    Vencimento sugerido. Dias CORRIDOS, não úteis: o cliente lê a data no
    slide, e "10 dias úteis" viraria uma conta que ninguém refaz.
    """
    return data_proposta + timedelta(days=dias)


# ── Validação ────────────────────────────────────────────────────────

def validar(
    *,
    vidas: int,
    valor_por_vida: Decimal,
    treinamentos: Decimal,
    laudos: Decimal,
    escopo: list[str],
    data_proposta: date,
    validade: date,
) -> None:
    """
    Levanta PropostaInvalida na primeira regra quebrada.

    As mensagens são as que o vendedor vê na tela — por isso explicam o que
    fazer, não o que aconteceu.
    """
    if vidas < 1:
        raise PropostaInvalida("A proposta precisa de pelo menos 1 vida.")
    if vidas > MAX_VIDAS:
        raise PropostaInvalida(
            f"Quantidade de vidas acima do limite ({MAX_VIDAS:,}). "
            "Confira o número antes de gerar.".replace(",", ".")
        )
    for rotulo, valor in (
        ("valor por vida", valor_por_vida),
        ("valor de treinamentos", treinamentos),
        ("valor de laudos", laudos),
    ):
        if valor is not None and Decimal(valor) < 0:
            raise PropostaInvalida(f"O {rotulo} não pode ser negativo.")
    if Decimal(valor_por_vida) <= 0:
        raise PropostaInvalida("O valor por vida precisa ser maior que zero.")

    limpos = [i.strip() for i in escopo if i and i.strip()]
    if not limpos:
        raise PropostaInvalida("A proposta precisa de ao menos um item de escopo.")
    if len(limpos) > MAX_ITENS_ESCOPO:
        raise PropostaInvalida(
            f"O escopo cabe em até {MAX_ITENS_ESCOPO} itens no slide. "
            f"Você informou {len(limpos)}."
        )

    if validade < data_proposta:
        raise PropostaInvalida(
            "A validade não pode ser anterior à data da proposta."
        )


def limpar_escopo(escopo: list[str]) -> list[str]:
    """Tira vazios e espaços das pontas, preservando a ordem digitada."""
    return [i.strip() for i in escopo if i and i.strip()]


# ── O que vai para dentro do .pptx ───────────────────────────────────

def substituicoes(
    *,
    cliente: str,
    vidas: int,
    valor_por_vida: Decimal,
    treinamentos: Decimal,
    laudos: Decimal,
    executivo_nome: str,
    executivo_email: str,
    executivo_telefone: str | None,
    data_proposta: date,
    validade: date,
    cidade: str = CIDADE_PADRAO,
) -> dict[str, str]:
    """
    O mapa marcador -> texto que o render aplica no modelo.

    Devolve STRING em tudo, inclusive nos números: o que entra num .pptx é
    texto formatado, e formatar aqui (e não no render) é o que deixa a
    formatação testável sem abrir arquivo nenhum.

    Telefone em branco vira '—' em vez de sumir: um rótulo "Telefone:" com
    o lado direito vazio parece defeito de geração; um travessão parece o
    que é — o cadastro não tem o número.
    """
    mensal = mensalidade(vidas, valor_por_vida)
    return {
        "{{CLIENTE}}": cliente,
        "{{VIDAS}}": str(vidas),
        "{{VALOR_VIDA}}": moeda(valor_por_vida),
        "{{MENSALIDADE}}": moeda(mensal),
        "{{TREINAMENTOS}}": moeda(treinamentos),
        "{{LAUDOS}}": moeda(laudos),
        "{{INVESTIMENTO}}": moeda(investimento(mensal, treinamentos, laudos)),
        "{{EXECUTIVO_NOME}}": executivo_nome,
        "{{EXECUTIVO_EMAIL}}": executivo_email,
        "{{EXECUTIVO_TELEFONE}}": (executivo_telefone or "").strip() or "—",
        "{{CIDADE}}": cidade,
        "{{DATA_EXTENSO}}": data_extenso(data_proposta),
        "{{VALIDADE}}": data_curta(validade),
    }


def nome_do_arquivo(numero_oportunidade: str, cliente: str, versao: int,
                    extensao: str) -> str:
    """
    Nome que o cliente vai ver na caixa de entrada.

    Começa pelo número da oportunidade porque é assim que a pasta de
    downloads fica ordenada de um jeito útil quando há dez propostas.
    """
    limpo = "".join(
        c if (c.isalnum() or c in " -_") else " " for c in (cliente or "")
    )
    limpo = " ".join(limpo.split())[:60].strip().replace(" ", "_")
    return f"{numero_oportunidade}_{limpo}_v{versao}.{extensao}"
