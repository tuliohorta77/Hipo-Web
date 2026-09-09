"""
HIPO — Regras da agenda de reuniões.

Funções puras: sem banco, sem I/O, sem `datetime.now()` escondido. Todo
cálculo que depende do relógio recebe `agora` (ou a data) como parâmetro —
mesmo padrão de services/tarefa.py e services/dias_uteis.py, e é o que
permite testar "esse horário está fora da grade" sem mockar o tempo.

Quatro assuntos moram aqui:

  1. A GRADE. Slots fixos de 30 minutos, 08:00–11:30 e 13:00–17:30, de
     segunda a sexta. É o desenho da planilha que originou o módulo.

  2. O HORÁRIO ESPECÍFICO. O slot é o padrão, não a prisão: quem agendou
     pode ajustar para 09:15 se o cliente só pode nesse horário. A grade
     continua desenhando por linha de slot, e o cartão fora do slot avisa
     que está fora — some seria pior que aparecer torto.

  3. O CONFLITO. Duas reuniões do mesmo anfitrião que se sobrepõem no
     tempo não podem existir: a pessoa não se divide.

  4. OS DOIS TEXTOS, e são dois porque são dois leitores. O RÓTULO
     ("CF - XPTO (Bruno) - ON") é o da planilha: curto, com sigla e
     primeiro nome, para caber na célula da grade e ser lido de relance
     por quem já conhece o negócio. O CONVITE (`titulo_evento` e
     `descricao_evento`) é lido pelo CLIENTE na agenda dele, ao lado de
     compromissos de outras empresas — leva razão social por extenso,
     CNPJ e os telefones de quem vai falar com quem.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# O mesmo fuso de services/tarefa.py, e pelo mesmo motivo: o dia e a hora
# que interessam são os do escritório. Importado de lá em vez de redefinido
# — duas constantes com o mesmo nome divergem no dia em que a operação
# mudar de cidade, e a que divergir vai ser a que ninguém está olhando.
from services.tarefa import FUSO_OPERACAO

__all__ = [
    "FUSO_OPERACAO", "PASSO_MIN", "DURACAO_PADRAO_MIN", "SLOTS",
    "DIAS_UTEIS_DA_GRADE", "MODALIDADES", "SIGLA_MODALIDADE",
    "ROTULO_MODALIDADE", "AgendaInvalida",
    "no_fuso", "slots", "eh_slot_canonico", "slot_ancora", "fora_da_grade",
    "rotulo_dia",
    "fim_de", "conflitam", "segunda_da_semana", "dias_da_semana",
    "janela_da_semana", "validar_duracao", "validar_modalidade",
    "validar_dia_da_semana", "normalizar_convidados",
    "primeiro_nome", "rotulo", "EMPRESA", "titulo_evento", "descricao_evento",
]

# Teto de convidados externos numa reunião. Não é limite do Google (que
# aceita centenas): é o ponto a partir do qual isto deixou de ser uma
# reunião comercial e virou uma lista de transmissão — e uma lista de
# transmissão digitada num campo de texto é o caminho mais curto para o
# domínio ser marcado como spam.
MAX_CONVIDADOS = 20

# Validação deliberadamente frouxa: "tem arroba, tem ponto depois, não tem
# espaço". A validação rigorosa de e-mail não existe (o RFC aceita coisas
# que nenhum provedor entrega), e a única checagem que vale de verdade é o
# convite chegar. O papel daqui é pegar o dedo escorregado — vírgula no
# lugar do ponto, nome sem domínio — antes de o Google recusar o evento
# INTEIRO por causa de um endereço, derrubando o convite dos outros junto.
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}$")


# ── A grade ──────────────────────────────────────────────────────────
#
# 08:00–11:30 de manhã e 13:00–17:30 à tarde, de 30 em 30 minutos. O
# último slot de cada bloco é um HORÁRIO DE INÍCIO, não o fim do
# expediente: a reunião das 11:30 termina às 12:00, e a das 17:30, às
# 18:00.
#
# O intervalo do almoço não é "um slot vazio", é ausência de slot: um
# buraco desenhado na grade diz mais do que uma linha de células cinzas,
# e é o que faz a coluna do dia caber na tela sem rolar.

PASSO_MIN = 30
DURACAO_PADRAO_MIN = 30

_BLOCOS = (
    (time(8, 0), time(11, 30)),
    (time(13, 0), time(17, 30)),
)

# Segunda a sexta. `date.weekday()` devolve 0 para segunda.
#
# Sábado e domingo NÃO são slots, e a API recusa reunião neles — não por
# rigor de RH, mas porque a grade não tem coluna para eles: uma reunião
# marcada no sábado existiria no banco, sairia no convite do cliente e
# seria INVISÍVEL na única tela que promete mostrar a semana. Registro
# que a tela esconde é pior que registro recusado.
DIAS_UTEIS_DA_GRADE = (0, 1, 2, 3, 4)

_ROTULO_DIA = {
    0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sáb", 6: "dom",
}


def _monta_slots() -> tuple[time, ...]:
    saida: list[time] = []
    for inicio, fim in _BLOCOS:
        atual = datetime.combine(date(2000, 1, 1), inicio)
        limite = datetime.combine(date(2000, 1, 1), fim)
        while atual <= limite:
            saida.append(atual.time())
            atual += timedelta(minutes=PASSO_MIN)
    return tuple(saida)


SLOTS = _monta_slots()

MODALIDADES = ("online", "presencial")

# A sigla vai para o rótulo, onde cabem poucos caracteres; o rótulo por
# extenso vai para o formulário, onde a pessoa precisa entender o que está
# escolhendo. São os mesmos dois papéis de sigla/nome em tipos_reuniao.
SIGLA_MODALIDADE = {"online": "ON", "presencial": "PRES"}
ROTULO_MODALIDADE = {"online": "Online", "presencial": "Presencial"}


class AgendaInvalida(ValueError):
    """Operação recusada pelas regras da agenda."""


def slots() -> tuple[time, ...]:
    """Os horários de início da grade, em ordem. Cópia imutável."""
    return SLOTS


# ── Onde o horário cai na grade ──────────────────────────────────────


def _local(quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO) -> datetime:
    """
    O instante no fuso da operação.

    asyncpg devolve TIMESTAMPTZ com fuso; teste puro costuma montar
    datetime ingênuo. Como em services/tarefa.py, o ingênuo é tratado como
    já estando no fuso da operação — é o que a pessoa digitou no formulário.
    """
    if quando.tzinfo is None:
        return quando.replace(tzinfo=fuso)
    return quando.astimezone(fuso)


def no_fuso(quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO) -> datetime:
    """
    `_local` para quem está fora deste módulo.

    O router precisa da mesma conversão para agrupar as reuniões por dia e
    para escrever a hora na mensagem de conflito. Reimplementar lá — ou
    importar o `_local` privado — criaria a segunda regra de fuso que o
    módulo inteiro existe para evitar.
    """
    return _local(quando, fuso)


def eh_slot_canonico(quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO) -> bool:
    """O horário começa exatamente em cima de um slot da grade?"""
    return _local(quando, fuso).time() in SLOTS


def slot_ancora(
    quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO
) -> time | None:
    """
    Em que LINHA da grade esta reunião é desenhada.

    Devolve o slot `s` tal que `s <= horário < s + 30min`. Fora dos dois
    blocos (madrugada, almoço, depois das 18h) devolve None, e aí a tela
    mostra a reunião numa faixa própria acima da grade — some seria pior
    que aparecer fora do lugar.

        09:00 -> 09:00        (em cima do slot)
        09:15 -> 09:00        (dentro da janela do slot das 09:00)
        12:10 -> None         (almoço)
        17:45 -> 17:30        (a janela do último slot vai até as 18:00)
        18:30 -> None
    """
    momento = _local(quando, fuso).time()
    anterior = None
    for s in SLOTS:
        if s <= momento:
            anterior = s
        else:
            break
    if anterior is None:
        return None
    # Só ancora se ainda estiver DENTRO da janela daquele slot. Sem esta
    # checagem, 12:10 seria ancorado às 11:30 e a reunião do almoço
    # apareceria empilhada com a das 11:30 — duas reuniões na mesma linha,
    # sem nenhuma relação entre elas.
    base = datetime.combine(date(2000, 1, 1), anterior)
    if datetime.combine(date(2000, 1, 1), momento) >= base + timedelta(minutes=PASSO_MIN):
        return None
    return anterior


def fora_da_grade(quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO) -> bool:
    """
    Este horário foge do desenho da grade?

    True tanto para o que caiu fora dos blocos (12:10) quanto para o que
    caiu dentro mas desalinhado (09:15). São a mesma coisa para quem lê a
    tela: "isto aqui não é um slot", e o cartão avisa.
    """
    return not eh_slot_canonico(quando, fuso)


def fim_de(inicio: datetime, duracao_min: int) -> datetime:
    """O fim da reunião. O par [início, fim) é sempre meio-aberto."""
    return inicio + timedelta(minutes=duracao_min)


def conflitam(
    a_inicio: datetime, a_fim: datetime,
    b_inicio: datetime, b_fim: datetime,
) -> bool:
    """
    Dois intervalos meio-abertos [início, fim) se sobrepõem?

    Meio-aberto é o que faz a reunião das 09:00–09:30 conviver com a das
    09:30–10:00: uma termina exatamente onde a outra começa, e isso é a
    grade funcionando, não conflito. Comparar com `<=` recusaria a agenda
    cheia — justamente o dia que se quer poder marcar.
    """
    return a_inicio < b_fim and b_inicio < a_fim


# ── A semana ─────────────────────────────────────────────────────────


def segunda_da_semana(dia: date) -> date:
    """
    A segunda-feira da semana de `dia`. Sábado e domingo pertencem à
    semana que acabou de passar (weekday 5 e 6 recuam até o dia 0).

    A tela navega por semana, e a URL carrega um dia qualquer — normalizar
    aqui é o que faz "?inicio=2026-09-11" (uma sexta) abrir a mesma semana
    que "?inicio=2026-09-07".
    """
    return dia - timedelta(days=dia.weekday())


def dias_da_semana(dia: date) -> list[date]:
    """Os cinco dias úteis da semana de `dia`, de segunda a sexta."""
    inicio = segunda_da_semana(dia)
    return [inicio + timedelta(days=d) for d in DIAS_UTEIS_DA_GRADE]


def rotulo_dia(dia: date) -> str:
    return _ROTULO_DIA[dia.weekday()]


def janela_da_semana(
    dia: date, fuso: ZoneInfo = FUSO_OPERACAO
) -> tuple[datetime, datetime]:
    """
    O par de instantes `[segunda 00:00, sábado 00:00)` no fuso da operação,
    para o SQL recortar.

    Meia-aberta pela mesma razão de `services/tarefa.janela_utc`: fechar em
    23:59:59 perde o que caiu no último segundo, e `<=` contra timestamp de
    precisão de microssegundo é a classe de bug que só aparece em produção.

    O fim é SÁBADO e não sexta 18:00 de propósito. A janela é o recorte da
    consulta, não a regra do expediente: uma reunião gravada fora do
    horário (a das 19h que alguém marcou antes de a regra existir, ou a de
    07:30 registrada como exceção) precisa aparecer na semana dela. Recorte
    que esconde dado é a mesma armadilha do registro invisível no sábado.
    """
    segunda = segunda_da_semana(dia)
    inicio = datetime.combine(segunda, time.min, tzinfo=fuso)
    fim = datetime.combine(segunda + timedelta(days=5), time.min, tzinfo=fuso)
    return inicio, fim


# ── Validações ───────────────────────────────────────────────────────


def validar_duracao(duracao_min: int) -> int:
    if duracao_min is None:
        raise AgendaInvalida("Informe a duração da reunião.")
    if not (5 <= duracao_min <= 480):
        raise AgendaInvalida(
            "A duração precisa ficar entre 5 minutos e 8 horas."
        )
    return duracao_min


def validar_modalidade(modalidade: str) -> str:
    if modalidade not in MODALIDADES:
        raise AgendaInvalida(
            f"Modalidade inválida: '{modalidade}'. Use: {', '.join(MODALIDADES)}."
        )
    return modalidade


def validar_dia_da_semana(
    quando: datetime, fuso: ZoneInfo = FUSO_OPERACAO
) -> datetime:
    """
    Recusa sábado e domingo.

    Não é rigor de expediente: a grade tem cinco colunas, e uma reunião no
    sábado existiria no banco, sairia no convite do cliente e nunca
    apareceria na tela que promete mostrar a semana. Registro invisível é
    pior que registro recusado — quem precisar de sábado pede a coluna, e
    aí a regra muda num lugar só.
    """
    local = _local(quando, fuso)
    if local.weekday() not in DIAS_UTEIS_DA_GRADE:
        raise AgendaInvalida(
            "A agenda vai de segunda a sexta. Escolha um dia útil."
        )
    return quando


def normalizar_convidados(valores: list[str] | None) -> list[str]:
    """
    Limpa a lista de e-mails do cliente: sem espaço, sem vazio, sem
    repetido, na ordem em que foram digitados.

    A deduplicação é por minúscula porque o Google recusa o evento inteiro
    com 400 quando o mesmo endereço aparece duas vezes — e "Ana@x.com"
    digitado à mão ao lado de "ana@x.com" vindo do cadastro do contato é
    exatamente como isso acontece.

    Ordem preservada de propósito: a lista é relida pela pessoa que a
    digitou, e ordenar alfabeticamente embaralharia o que ela acabou de
    escrever.
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for bruto in valores or []:
        limpo = (bruto or "").strip()
        if not limpo:
            continue
        if not _EMAIL.match(limpo):
            raise AgendaInvalida(f"E-mail de convidado inválido: '{limpo}'.")
        chave = limpo.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(limpo)
    if len(saida) > MAX_CONVIDADOS:
        raise AgendaInvalida(
            f"No máximo {MAX_CONVIDADOS} convidados externos por reunião."
        )
    return saida


# ── O rótulo ─────────────────────────────────────────────────────────


def primeiro_nome(nome: str | None) -> str:
    """
    'Bruno Gonçalo' -> 'Bruno'.

    O rótulo mora num cartão de ~13rem e no `summary` de um evento do
    Google, que a agenda do celular corta em poucos caracteres. O nome
    inteiro comeria o espaço da empresa, que é o que identifica a reunião.
    """
    partes = (nome or "").split()
    return partes[0] if partes else ""


def rotulo(
    *,
    sigla_tipo: str | None,
    empresa: str | None,
    anfitriao: str | None,
    modalidade: str,
    limite_empresa: int = 34,
) -> str:
    """
    Monta "CF - XPTO (Bruno) - ON" — o formato da planilha que originou o
    módulo, mantido porque é o que a equipe já lê sem pensar.

    As quatro partes respondem, nessa ordem, ao que se pergunta olhando a
    grade: que reunião é essa, com quem, quem conduz, e se eu preciso sair
    de casa.

    Toda parte é opcional e some sem deixar separador solto. Reunião sem
    tipo é comum — a lista de tipos é esvaziada pelo TRUNCATE do conftest e
    pode estar incompleta em produção — e um rótulo que virasse " - XPTO"
    faria a tela parecer quebrada por causa de um campo que o próprio
    sistema aceita vazio.
    """
    empresa = (empresa or "").strip()
    if len(empresa) > limite_empresa:
        # Reticências e não corte seco: sem elas "CONTROLLER SERVICOS" e
        # "CONTROLLER SERVIÇOS MEDICOS" viram o mesmo texto na tela, e o
        # vendedor abre a reunião errada.
        empresa = empresa[: limite_empresa - 1].rstrip() + "…"

    miolo = empresa
    curto = primeiro_nome(anfitriao)
    if curto:
        miolo = f"{miolo} ({curto})" if miolo else f"({curto})"

    partes = [p for p in ((sigla_tipo or "").strip(), miolo) if p]
    texto = " - ".join(partes)

    sigla_mod = SIGLA_MODALIDADE.get(modalidade)
    if sigla_mod:
        texto = f"{texto} - {sigla_mod}" if texto else sigla_mod
    return texto


# ── O convite que o cliente recebe ───────────────────────────────────
#
# DOIS FORMATOS, DOIS LEITORES. O `rotulo` acima é o da PLANILHA: curto,
# com sigla e primeiro nome, feito para caber numa célula de 13rem e ser
# lido de relance por quem já conhece o negócio. O que vai para o Google é
# outra coisa: quem lê é o CLIENTE, que não sabe o que é "CF", não conhece
# "Bruno" e precisa reconhecer a própria empresa na agenda dele três
# semanas depois.
#
# Por isso o evento leva razão social por extenso, CNPJ e o nome da nossa
# empresa; e por isso os dois formatos são funções separadas, e não uma com
# um parâmetro `curto=True` — parâmetro booleano de formatação é onde os
# dois públicos acabam recebendo o texto um do outro.
#
# O formato abaixo reproduz o convite que a operação já manda hoje à mão.
# Foi copiado de um evento real, e não inventado: a equipe e os clientes já
# leem esse desenho, e mudá-lo junto com a automação misturaria duas
# mudanças numa só.

EMPRESA = "Controller MedSeg"


def titulo_evento(
    *, razao_social: str | None, cnpj: str | None, tipo_nome: str | None,
) -> str:
    """
    'NN MANUTENCAO ... LTDA 06.335.181/0001-93 | Apresentação Controller MedSeg'

    Razão social por extenso, e não nome fantasia: na agenda do cliente
    este texto vive ao lado de compromissos de outras empresas, e o nome
    do contrato é o que ele reconhece. O CNPJ vem junto porque grupos com
    várias razões sociais parecidas são comuns na carteira, e é ele que
    diz de qual filial é a reunião.

    Cada parte some sozinha se faltar, sem deixar separador solto — o
    mesmo cuidado do `rotulo`.
    """
    from services.cnpj import formatar as formatar_cnpj

    esquerda = " ".join(
        p for p in ((razao_social or "").strip(), formatar_cnpj(cnpj)) if p
    )
    direita = " ".join(p for p in ((tipo_nome or "").strip(), EMPRESA) if p)
    return " | ".join(p for p in (esquerda, direita) if p)


def descricao_evento(
    *,
    titulo: str,
    inicio: datetime,
    modalidade: str,
    contato_nome: str | None = None,
    contato_telefone: str | None = None,
    contato_email: str | None = None,
    anfitriao_nome: str | None = None,
    anfitriao_telefone: str | None = None,
    endereco: str | None = None,
    observacoes: str | None = None,
    fuso: ZoneInfo = FUSO_OPERACAO,
) -> str:
    """
    O corpo do convite, no desenho que a operação já usa:

        NN MANUTENCAO ... | Apresentação Controller MedSeg
        09/09 às 09:30
        ONLINE
        Contato: Nivaldo
        Cel: (11) 99947-7607
        Email: ADM.Nnredutores@gmail.com
        Consultor: Jakeline Santana
        Cel: (11) 94251-9976

    A data repetida no corpo não é redundância: o cliente encaminha esse
    convite por WhatsApp, e no encaminhamento sobra o texto, não o campo de
    horário do evento.

    Linha vazia é linha OMITIDA, nunca "Cel: —". Um campo em branco no
    convite do cliente parece cadastro pela metade, e é a única peça deste
    módulo que uma pessoa de fora lê.

    O número da oportunidade NÃO entra. É vocabulário nosso, e o cliente vê
    tudo o que estiver aqui — quem precisa dele tem o CNPJ no título.
    """
    quando = _local(inicio, fuso)
    linhas = [
        titulo,
        f"{quando.strftime('%d/%m')} às {quando.strftime('%H:%M')}",
        ROTULO_MODALIDADE.get(modalidade, modalidade).upper(),
    ]
    if endereco and (endereco or "").strip():
        linhas.append(endereco.strip())

    for prefixo, valor in (
        ("Contato", contato_nome),
        ("Cel", contato_telefone),
        ("Email", contato_email),
        ("Consultor", anfitriao_nome),
        ("Cel", anfitriao_telefone),
    ):
        if valor and str(valor).strip():
            linhas.append(f"{prefixo}: {str(valor).strip()}")

    if observacoes and observacoes.strip():
        linhas.append("")
        linhas.append(observacoes.strip())

    return "\n".join(linhas)
