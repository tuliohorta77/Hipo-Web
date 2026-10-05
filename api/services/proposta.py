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
    mensal: Decimal | None = None,
    sem_extras: bool = False,
    faixas: list[dict] | None = None,
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
    if mensal is None:
        mensal = mensalidade(vidas, valor_por_vida)
    # Proposta POR CNPJ, recortada de uma consolidada: treinamentos e laudos
    # são do negócio inteiro, não deste CNPJ. Repetir o valor cheio em cada
    # arquivo faria o cliente somar e enxergar o extra cobrado N vezes.
    if sem_extras:
        treinamentos = laudos = Decimal(0)
    return {
        "{{CLIENTE}}": cliente,
        "{{VIDAS}}": str(vidas),
        # Na modalidade tabela não há valor por vida; o slide que o usa é
        # removido, mas o mapa não pode deixar marcador sem valor.
        "{{VALOR_VIDA}}": moeda(valor_por_vida) if valor_por_vida else "—",
        "{{MENSALIDADE}}": moeda(mensal),
        "{{TREINAMENTOS}}": "—" if sem_extras else moeda(treinamentos),
        "{{LAUDOS}}": "—" if sem_extras else moeda(laudos),
        "{{INVESTIMENTO}}": moeda(investimento(mensal, treinamentos, laudos)),
        "{{TABELA_RODAPE}}": rodape_tabela(faixas or TABELA_PADRAO),
        "{{EXECUTIVO_NOME}}": executivo_nome,
        "{{EXECUTIVO_EMAIL}}": executivo_email,
        "{{EXECUTIVO_TELEFONE}}": (executivo_telefone or "").strip() or "—",
        "{{CIDADE}}": cidade,
        "{{DATA_EXTENSO}}": data_extenso(data_proposta),
        "{{VALIDADE}}": data_curta(validade),
    }


def nome_do_arquivo(numero_oportunidade: str, cliente: str, versao: int,
                    extensao: str, cnpj: str | None = None) -> str:
    """
    Nome que o cliente vai ver na caixa de entrada.

    Começa pelo número da oportunidade porque é assim que a pasta de
    downloads fica ordenada de um jeito útil quando há dez propostas.
    """
    limpo = "".join(
        c if (c.isalnum() or c in " -_") else " " for c in (cliente or "")
    )
    limpo = " ".join(limpo.split())[:60].strip().replace(" ", "_")
    # Proposta de UM CNPJ, recortada da consolidada: o CNPJ no nome é o que
    # separa os arquivos de duas filiais com a mesma razão social.
    sufixo = f"_{''.join(c for c in cnpj if c.isdigit())}" if cnpj else ""
    return f"{numero_oportunidade}_{limpo}_v{versao}{sufixo}.{extensao}"


# ══════════════════════════════════════════════════════════════════════
# 042 — Vários CNPJs na mesma proposta e tabela de preço por faixa
# ══════════════════════════════════════════════════════════════════════
#
# Cliente com vários CNPJs é UMA negociação: uma oportunidade, uma proposta,
# uma linha por CNPJ com as vidas e a mensalidade daquele CNPJ. A
# mensalidade da proposta é a SOMA das linhas.
#
# Duas modalidades:
#
#   * 'por_vida' — o que já existia: cada CNPJ paga vidas x valor por vida.
#     O valor da linha é derivado, não se digita.
#   * 'tabela'   — cada CNPJ paga pela faixa de vidas em que cai (até 5
#     vidas, R$ 180; ...; acima de 20, R$ 15 por vida). A tabela SUGERE;
#     o vendedor pode negociar o valor da linha, e a tela mostra o desconto.

MODALIDADES = ("por_vida", "tabela")
MODALIDADE_PADRAO = "tabela"

TIPOS_FAIXA = ("fixo", "por_vida")

# A tabela da Controller MedSeg (material "VARIOS CNPJs", out/2026). É o
# que a migration 026 grava e o que vale se a tabela do banco estiver vazia
# — sem ela, a modalidade tabela não teria de onde sugerir preço.
TABELA_PADRAO: list[dict] = [
    {"vidas_ate": 5, "tipo": "fixo", "valor": Decimal("180.00")},
    {"vidas_ate": 10, "tipo": "fixo", "valor": Decimal("220.00")},
    {"vidas_ate": 15, "tipo": "fixo", "valor": Decimal("260.00")},
    {"vidas_ate": 20, "tipo": "fixo", "valor": Decimal("300.00")},
    {"vidas_ate": None, "tipo": "por_vida", "valor": Decimal("15.00")},
]

MAX_FAIXAS = 8
MAX_CNPJS = 30

# Texto fixo do rodapé do slide da tabela; a frase do excedente é montada
# a partir da faixa aberta.
RODAPE_TABELA_BASE = (
    "Assessoria permanente em segurança e Medicina do Trabalho enquanto "
    "vigorar o contrato*** Os exames complementares (quando necessários) "
    "terão seus valores acertados de acordo com a tabela vigente na data de "
    "realização. A mensalidade apresentada considera o número de vidas "
    "informado nesta proposta."
)

# ── Capacidade da lista no slide ──
#
# A caixa do escopo tem altura fixa e entrelinha fixa (36,39 pt). Contado
# no material: no slide por vida cabem 9 linhas acima do quadro de
# investimento; no slide da tabela, 12 acima da mensalidade. Passando
# disso, fonte e entrelinha encolhem juntas até ESCALA_MINIMA — abaixo
# dela o texto fica pequeno demais para um cliente ler, e a proposta é
# recusada com a sugestão de gerar por CNPJ.
CAPACIDADE_LINHAS = {"por_vida": 9, "tabela": 12, "faixas": 6}
CARACTERES_POR_LINHA = 88
ESCALA_MINIMA = Decimal("0.6")


def _dinheiro(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Tabela ───────────────────────────────────────────────────────────

def normalizar_tabela(faixas: list[dict]) -> list[dict]:
    """
    Valida e ordena a tabela. Levanta PropostaInvalida com mensagem para a
    gestão, que é quem edita.

    Regras: pelo menos uma faixa; exatamente UMA aberta (sem limite), que é
    a última; limites crescentes e sem repetição; valor positivo.
    """
    if not faixas:
        raise PropostaInvalida("A tabela precisa de pelo menos uma faixa.")
    if len(faixas) > MAX_FAIXAS:
        raise PropostaInvalida(
            f"A tabela cabe em até {MAX_FAIXAS} faixas no slide."
        )

    limpas = []
    for f in faixas:
        tipo = f.get("tipo")
        if tipo not in TIPOS_FAIXA:
            raise PropostaInvalida("Tipo de faixa inválido: use fixo ou por vida.")
        valor = f.get("valor")
        if valor is None or Decimal(str(valor)) <= 0:
            raise PropostaInvalida("Toda faixa precisa de valor maior que zero.")
        ate = f.get("vidas_ate")
        if ate is not None:
            ate = int(ate)
            if ate < 1:
                raise PropostaInvalida("O limite de vidas da faixa começa em 1.")
        limpas.append({"vidas_ate": ate, "tipo": tipo, "valor": _dinheiro(valor)})

    abertas = [f for f in limpas if f["vidas_ate"] is None]
    if len(abertas) != 1:
        raise PropostaInvalida(
            "A tabela precisa de exatamente uma faixa sem limite (\"acima de\")."
        )
    fechadas = sorted((f for f in limpas if f["vidas_ate"] is not None),
                      key=lambda f: f["vidas_ate"])
    limites = [f["vidas_ate"] for f in fechadas]
    if len(set(limites)) != len(limites):
        raise PropostaInvalida("Duas faixas com o mesmo limite de vidas.")
    return fechadas + abertas


def tabela_para_json(faixas: list[dict]) -> list[dict]:
    """Forma gravável em jsonb (Decimal vira string, sem perder centavo)."""
    return [
        {"vidas_ate": f["vidas_ate"], "tipo": f["tipo"], "valor": str(_dinheiro(f["valor"]))}
        for f in faixas
    ]


def tabela_de_json(bruto) -> list[dict]:
    return [
        {"vidas_ate": f.get("vidas_ate"), "tipo": f["tipo"], "valor": _dinheiro(f["valor"])}
        for f in (bruto or [])
    ]


def faixa_de(vidas: int, faixas: list[dict]) -> dict:
    """A faixa em que `vidas` cai. A tabela chega normalizada."""
    for f in faixas:
        if f["vidas_ate"] is None or vidas <= f["vidas_ate"]:
            return f
    return faixas[-1]


def valor_tabela(vidas: int, faixas: list[dict]) -> Decimal:
    """
    Mensalidade sugerida para um CNPJ.

    >>> valor_tabela(4, TABELA_PADRAO)
    Decimal('180.00')
    >>> valor_tabela(23, TABELA_PADRAO)
    Decimal('345.00')
    """
    f = faixa_de(vidas, faixas)
    if f["tipo"] == "por_vida":
        return _dinheiro(Decimal(vidas) * f["valor"])
    return _dinheiro(f["valor"])


def _dois(n: int) -> str:
    return f"{n:02d}"


def linhas_tabela(faixas: list[dict]) -> list[str]:
    """
    As linhas do slide da tabela, no texto do material:

        CNPJs até 05 funcionários registrados – R$ 180,00 mensais
        CNPJs entre 06 e 10 funcionários registrados – R$ 220,00 mensais
        CNPJs acima de 20 funcionários registrados – R$ 15,00 por funcionário/mês
    """
    linhas = []
    anterior = 0
    for f in faixas:
        if f["tipo"] == "fixo":
            preco = f"{moeda(f['valor'])} mensais"
        else:
            preco = f"{moeda(f['valor'])} por funcionário/mês"
        if f["vidas_ate"] is None:
            faixa = f"acima de {_dois(anterior)}" if anterior else "a partir de 01"
        elif anterior == 0:
            faixa = f"até {_dois(f['vidas_ate'])}"
        elif f["vidas_ate"] == anterior + 1:
            faixa = f"com {_dois(f['vidas_ate'])}"
        else:
            faixa = f"entre {_dois(anterior + 1)} e {_dois(f['vidas_ate'])}"
        linhas.append(f"CNPJs {faixa} funcionários registrados – {preco}")
        if f["vidas_ate"] is not None:
            anterior = f["vidas_ate"]
    return linhas


def rodape_tabela(faixas: list[dict]) -> str:
    """
    O rodapé do slide da tabela. A frase do excedente sai da faixa aberta
    — escrita fixa no slide, ela mentiria no primeiro reajuste.
    """
    aberta = faixas[-1]
    fechadas = [f for f in faixas if f["vidas_ate"] is not None]
    if not fechadas:
        return RODAPE_TABELA_BASE
    limite = fechadas[-1]["vidas_ate"]
    if aberta["tipo"] == "por_vida":
        excedente = (
            f" Fica estabelecido que cada vida adicional que ultrapassar o "
            f"limite de {limite} funcionários acarretará o acréscimo de "
            f"{moeda(aberta['valor'])} ao valor mensal."
        )
    else:
        excedente = (
            f" Acima de {limite} funcionários, a mensalidade é de "
            f"{moeda(aberta['valor'])}."
        )
    return (
        f"{RODAPE_TABELA_BASE}{excedente} Para até {limite} vidas, "
        "prevalecem os valores indicados na tabela acima."
    )


# ── Itens (CNPJs) ────────────────────────────────────────────────────

def calcular_itens(
    *,
    modalidade: str,
    itens: list[dict],
    valor_por_vida: Decimal | None,
    faixas: list[dict] | None,
) -> list[dict]:
    """
    Fecha o valor de cada CNPJ.

    Recebe `[{vidas, mensalidade?, ...}]` e devolve as mesmas linhas com
    `mensalidade` e `valor_tabela` resolvidos:

      * por_vida: mensalidade = vidas x valor por vida, SEMPRE — o que veio
        digitado é ignorado, pelo mesmo motivo de sempre: a conta do slide
        tem que fechar com o que está escrito nele. valor_tabela = None.
      * tabela: valor_tabela = o que a faixa sugere; mensalidade = o que o
        vendedor negociou, ou a sugestão quando veio em branco.
    """
    if modalidade not in MODALIDADES:
        raise PropostaInvalida("Modalidade inválida: use por vida ou tabela.")
    if modalidade == "por_vida" and (valor_por_vida is None or Decimal(valor_por_vida) <= 0):
        raise PropostaInvalida("O valor por vida precisa ser maior que zero.")
    if modalidade == "tabela" and not faixas:
        raise PropostaInvalida("Sem tabela de preço para a modalidade tabela.")
    resolvidos = []
    for item in itens:
        vidas = int(item["vidas"])
        if vidas < 1:
            raise PropostaInvalida(
                f"{item.get('razao_social') or item.get('cnpj')}: informe pelo menos 1 vida."
            )
        novo = dict(item)
        if modalidade == "por_vida":
            novo["mensalidade"] = mensalidade(vidas, valor_por_vida)
            novo["valor_tabela"] = None
        else:
            sugerido = valor_tabela(vidas, faixas)
            negociado = item.get("mensalidade")
            novo["valor_tabela"] = sugerido
            novo["mensalidade"] = sugerido if negociado is None else _dinheiro(negociado)
        resolvidos.append(novo)
    return resolvidos


def total_itens(itens: list[dict]) -> Decimal:
    return _dinheiro(sum((Decimal(str(i["mensalidade"])) for i in itens), Decimal(0)))


def vidas_itens(itens: list[dict]) -> int:
    return sum(int(i["vidas"]) for i in itens)


def desconto_percentual(mensal: Decimal | None, tabela: Decimal | None) -> Decimal | None:
    """
    Quanto a linha ficou ABAIXO da tabela, em %, uma casa. None quando não
    há tabela ou quando o valor está na tabela ou acima dela.

    >>> desconto_percentual(Decimal("299"), Decimal("345"))
    Decimal('13.3')
    """
    if mensal is None or not tabela:
        return None
    m, t = Decimal(str(mensal)), Decimal(str(tabela))
    if m >= t:
        return None
    return ((t - m) / t * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def linha_cnpj(item: dict) -> str:
    """
    A linha de um CNPJ no slide, no formato do material:

        METALURGICA ALFA LTDA (11.222.333/0001-81) - 4 vidas - Mensalidade R$ 180,00

    A razão social é cortada em 34 caracteres para a linha caber numa só —
    linha que dobra come o espaço de outro CNPJ.
    """
    from services.cnpj import formatar
    razao = " ".join((item.get("razao_social") or "").split())
    if len(razao) > 34:
        razao = razao[:33].rstrip() + "…"
    vidas = int(item["vidas"])
    return (
        f"{razao} ({formatar(item['cnpj'])}) - {vidas} vida{'s' if vidas != 1 else ''}"
        f" - Mensalidade {moeda(item['mensalidade'])}"
    )


def linhas_da_lista(
    *,
    modalidade: str,
    escopo: list[str],
    itens: list[dict],
    treinamentos: Decimal = Decimal(0),
    laudos: Decimal = Decimal(0),
    consolidada: bool = True,
) -> list[str]:
    """
    O que vai na lista do slide do escopo: os itens de escopo, depois uma
    linha por CNPJ (só na consolidada com mais de um), depois os extras na
    modalidade tabela — que não tem o quadro de investimento onde eles
    apareciam.
    """
    linhas = list(escopo)
    if consolidada and len(itens) > 1:
        linhas += [linha_cnpj(i) for i in itens]
    if consolidada and modalidade == "tabela":
        if treinamentos and Decimal(str(treinamentos)) > 0:
            linhas.append(f"Treinamentos - {moeda(treinamentos)}")
        if laudos and Decimal(str(laudos)) > 0:
            linhas.append(f"Laudos (outros) - {moeda(laudos)}")
    return linhas


def escala_da_lista(linhas: list[str], capacidade: int) -> Decimal | None:
    """
    Fator de fonte e entrelinha para a lista caber na caixa. 1 = tamanho do
    material; None = não cabe nem no mínimo legível.

    Linha longa conta como várias: com a fonte menor, cabe mais texto por
    linha E mais linhas na caixa, por isso as duas contas usam a escala.
    """
    escala = Decimal("1.00")
    passo = Decimal("0.05")
    while escala >= ESCALA_MINIMA:
        por_linha = int(CARACTERES_POR_LINHA / escala)
        ocupadas = sum(max(1, -(-len(t) // por_linha)) for t in linhas)
        if ocupadas <= int(capacidade / escala):
            return escala
        escala -= passo
    return None


def validar_itens(
    *,
    modalidade: str,
    itens: list[dict],
    valor_por_vida: Decimal | None,
    escopo: list[str],
    treinamentos: Decimal = Decimal(0),
    laudos: Decimal = Decimal(0),
) -> None:
    """Regras da 042, depois de `validar`. Mensagens para o vendedor."""
    if modalidade not in MODALIDADES:
        raise PropostaInvalida("Modalidade inválida: use por vida ou tabela.")
    if modalidade == "por_vida" and (valor_por_vida is None or Decimal(valor_por_vida) <= 0):
        raise PropostaInvalida("O valor por vida precisa ser maior que zero.")
    if not itens:
        raise PropostaInvalida("A proposta precisa de pelo menos um CNPJ.")
    if len(itens) > MAX_CNPJS:
        raise PropostaInvalida(
            f"Até {MAX_CNPJS} CNPJs por proposta. Gere em mais de uma."
        )
    cnpjs = [i["cnpj"] for i in itens]
    if len(set(cnpjs)) != len(cnpjs):
        raise PropostaInvalida("O mesmo CNPJ aparece duas vezes na proposta.")
    for i in itens:
        if int(i["vidas"]) < 1:
            raise PropostaInvalida(
                f"{i.get('razao_social') or i['cnpj']}: informe pelo menos 1 vida."
            )
        if int(i["vidas"]) > MAX_VIDAS:
            raise PropostaInvalida("Quantidade de vidas acima do limite. Confira o número.")
        if i.get("mensalidade") is not None and Decimal(str(i["mensalidade"])) < 0:
            raise PropostaInvalida("A mensalidade de um CNPJ não pode ser negativa.")
    if total_itens(itens) <= 0:
        raise PropostaInvalida("A mensalidade total precisa ser maior que zero.")

    linhas = linhas_da_lista(
        modalidade=modalidade, escopo=escopo, itens=itens,
        treinamentos=treinamentos, laudos=laudos,
    )
    if escala_da_lista(linhas, CAPACIDADE_LINHAS[modalidade]) is None:
        raise PropostaInvalida(
            f"Escopo e CNPJs somam {len(linhas)} linhas e não cabem no slide "
            "nem com a fonte reduzida. Tire itens do escopo ou gere as "
            "propostas por CNPJ."
        )
