"""
HIPO — Regras da carteira de parceiros.

Funções puras: sem banco, sem I/O, sem `date.today()` escondido. Todo cálculo
que depende do relógio recebe `hoje` como parâmetro — mesmo padrão de
services/tarefa.py e services/dias_uteis.py.

O que mora aqui:

  1. AS DUAS TAXAS. Conversão e cancelamento respondem perguntas diferentes e
     têm denominadores diferentes. Misturar as duas foi o erro que a regra do
     funil já tinha decidido evitar (`cancelado` fica fora do denominador de
     conversão), e a mesma decisão vale aqui.

  2. SITUAÇÃO DA RELAÇÃO. O parceiro não tem coluna de estado — o estado sai
     da data da última indicação contra o relógio. Pelo mesmo motivo das
     tarefas: guardar 'dormente' numa coluna exigiria um job virando o estado
     todo dia, e falha de job produz dado mentiroso.

  3. OS PERÍODOS. A tela abre no acumulado histórico e recorta sob demanda.
     Quem só olha acumulado não enxerga o parceiro que indicava bem e parou —
     e é exatamente esse que precisa de visita.

  4. O FAROL SEMANAL. Cadência de contato, semana a semana. Mora aqui e não
     em services/tarefa.py porque é regra da RELAÇÃO com o parceiro, irmã de
     `situacao()` — a tarefa é só o insumo. O service de tarefa continua
     sendo sobre o ciclo de vida de uma tarefa; este é sobre o ritmo de uma
     parceria.
"""
from __future__ import annotations

from datetime import date, timedelta

# ── Períodos da tela ─────────────────────────────────────────────────
#
# 'sempre' é o padrão: a relação com um parceiro é longa, e o número que
# importa na maior parte do tempo é o acumulado. Os recortes existem para
# responder "e ultimamente?".

PERIODOS = ("sempre", "90d", "ano")

ROTULOS_PERIODO = {
    "sempre": "Desde sempre",
    "90d": "Últimos 90 dias",
    "ano": "Ano corrente",
}

DIAS_PERIODO = {"90d": 90}


def inicio_do_periodo(periodo: str, hoje: date | None = None) -> date | None:
    """
    Primeira data que entra no recorte, ou None para 'sempre'.

    None não é ausência de resposta: é a resposta. O SQL usa
    `($n::date IS NULL OR o.criado_em >= $n)`, então 'sempre' vira um filtro
    que não filtra — e a consulta continua sendo uma só.
    """
    if periodo not in PERIODOS:
        raise ValueError(f"Período inválido. Use: {', '.join(PERIODOS)}.")
    if periodo == "sempre":
        return None
    hoje = hoje or date.today()
    if periodo == "ano":
        return date(hoje.year, 1, 1)
    return hoje - timedelta(days=DIAS_PERIODO[periodo])


# ── Situação da relação ──────────────────────────────────────────────
#
# Os cortes são em dias corridos, não em dias úteis: a pergunta é "há quanto
# tempo esse parceiro não lembra da gente", e o calendário do parceiro não é
# o nosso.
#
# 90 dias porque é o ciclo de um trimestre — parceiro que passou um trimestre
# sem indicar nada não está devagar, está parado.

DIAS_ATIVO = 90
DIAS_ESFRIANDO = 180

SITUACOES = ("sem_indicacao", "ativo", "esfriando", "dormente")

ROTULOS_SITUACAO = {
    "sem_indicacao": "Sem indicação",
    "ativo": "Ativo",
    "esfriando": "Esfriando",
    "dormente": "Dormente",
}

# Ordem de atenção para a tela: quem precisa de ação primeiro.
# 'sem_indicacao' vem na frente de 'dormente' porque parceiro que nunca
# indicou nada é promessa não cumprida — e normalmente é mais barato ativar
# do que ressuscitar.
ORDEM_SITUACAO = {s: i for i, s in enumerate(
    ("sem_indicacao", "dormente", "esfriando", "ativo")
)}


def situacao(ultima_indicacao_em: date | None, hoje: date | None = None) -> str:
    """
    Estado da relação com o parceiro, derivado da última indicação.

        nunca indicou          -> sem_indicacao
        até 90 dias atrás      -> ativo
        de 91 a 180 dias atrás -> esfriando
        mais de 180 dias       -> dormente

    IMPORTANTE: quem chama deve passar a data da última indicação de TODA a
    história, não a do período selecionado na tela. Filtrar os dois pelo
    mesmo recorte faria um parceiro de anos aparecer como 'sem indicação'
    sempre que alguém olhasse os últimos 90 dias.
    """
    if ultima_indicacao_em is None:
        return "sem_indicacao"
    hoje = hoje or date.today()
    dias = (hoje - ultima_indicacao_em).days
    if dias <= DIAS_ATIVO:
        return "ativo"
    if dias <= DIAS_ESFRIANDO:
        return "esfriando"
    return "dormente"


def validar_situacao(valor: str) -> str:
    if valor not in SITUACOES:
        raise ValueError(f"Situação inválida. Use: {', '.join(SITUACOES)}.")
    return valor


# ── As duas taxas ────────────────────────────────────────────────────


def taxa_conversao(conquistadas: int, perdidas: int) -> float | None:
    """
    Quanto do que o parceiro indicou e chegou ao fim virou cliente.

    Denominador é conquistadas + perdidas. Fora dele ficam:

      * CANCELADAS — erro nosso de CRM (lead errado, duplicata, empresa que
        não existe). Já é decisão do funil que cancelado não entra em
        denominador nenhum; contá-lo aqui puniria o parceiro por um erro que
        não é dele. A qualidade da indicação é medida separado, pela taxa de
        cancelamento.
      * EM ABERTO — ainda não são resultado. Contá-las como não-conversão
        derrubaria a taxa de todo parceiro que acabou de indicar.

    Devolve None quando nada fechou ainda: 0% e "sem resposta" são coisas
    diferentes, e mostrar 0% para quem indicou ontem é mentira.
    """
    fechadas = conquistadas + perdidas
    if fechadas <= 0:
        return None
    return round(conquistadas / fechadas, 4)


def taxa_cancelamento(canceladas: int, indicacoes: int) -> float | None:
    """
    Qualidade da indicação: quanto do que o parceiro mandou era lead errado.

    Aqui o denominador é TUDO que ele indicou — inclusive o que está em
    aberto. É outra pergunta: conversão mede o que aconteceu com o negócio,
    cancelamento mede o que o parceiro nos entregou.

    Devolve None quando não há indicação nenhuma.
    """
    if indicacoes <= 0:
        return None
    return round(canceladas / indicacoes, 4)


# ── O farol semanal ──────────────────────────────────────────────────
#
# A situação (ativo / esfriando / dormente) mede o que o parceiro NOS deu.
# O farol mede o contrário: o que NÓS fizemos por ele. São perguntas
# diferentes e é de propósito que existam as duas na mesma linha — parceiro
# dormente com quatro semanas verdes é problema de produto ou de mercado;
# parceiro dormente com quatro semanas vermelhas é abandono, e a ação é
# outra.
#
# A SEMANA É DE SEGUNDA A DOMINGO, no calendário do escritório. Não é janela
# móvel de 7 dias: janela móvel muda de resposta todo dia e não dá para
# combinar numa reunião de segunda. "Falei com ele esta semana?" é pergunta
# de calendário.

SEMANAS_FAROL = 4

CORES = ("verde", "amarelo", "vermelho")

ROTULOS_COR = {
    "verde": "Contato feito",
    "amarelo": "Agendado, não feito",
    "vermelho": "Sem contato",
}


def inicio_da_semana(dia: date) -> date:
    """Segunda-feira da semana de `dia`. `weekday()` é 0 na segunda."""
    return dia - timedelta(days=dia.weekday())


def semanas_do_farol(hoje: date, quantidade: int = SEMANAS_FAROL) -> list[tuple[date, date]]:
    """
    As `quantidade` últimas semanas, MAIS ANTIGA PRIMEIRO e a corrente por
    último.

    A ordem importa: a trilha é lida da esquerda para a direita e termina em
    hoje, como qualquer linha do tempo. Invertida, o olho leria a semana
    corrente como a mais antiga.
    """
    if quantidade < 1:
        raise ValueError("O farol precisa de pelo menos uma semana.")
    corrente = inicio_da_semana(hoje)
    semanas = []
    for n in reversed(range(quantidade)):
        inicio = corrente - timedelta(weeks=n)
        semanas.append((inicio, inicio + timedelta(days=6)))
    return semanas


def cor_do_farol(concluidas: int, agendadas: int) -> str:
    """
    Verde  — houve contato: pelo menos uma tarefa CONCLUÍDA na semana.
    Amarelo— há tarefa na semana, nenhuma concluída ainda.
    Vermelho— nada na semana.

    O verde olha `concluida_em`, não `prazo`: o que vale é quando o contato
    aconteceu, não quando estava previsto. Agendar dez visitas e não fazer
    nenhuma não é semana verde.

    Amarelo tem duas leituras conforme a semana, e é de propósito que a cor
    seja a mesma: na semana corrente é "ainda dá tempo"; numa semana passada
    é "prometeu e não fez". As duas são o mesmo fato — tarefa que existe e
    não virou contato — e quem lê a trilha inteira distingue pela posição.
    """
    if concluidas > 0:
        return "verde"
    if agendadas > 0:
        return "amarelo"
    return "vermelho"


def farol(
    contagens: dict[date, dict[str, int]],
    hoje: date,
    quantidade: int = SEMANAS_FAROL,
) -> list[dict]:
    """
    Monta a trilha do farol.

    `contagens` é indexado pela SEGUNDA-FEIRA da semana e cada valor tem
    'concluidas' e 'agendadas'. Semana ausente do dicionário é semana sem
    nada — vermelha. Quem consulta o banco entrega só as semanas que têm
    linha; completar os buracos é trabalho daqui, não de um LEFT JOIN contra
    generate_series.
    """
    trilha = []
    for inicio, fim in semanas_do_farol(hoje, quantidade):
        c = contagens.get(inicio) or {}
        concluidas = int(c.get("concluidas", 0))
        agendadas = int(c.get("agendadas", 0))
        trilha.append({
            "inicio": inicio,
            "fim": fim,
            "concluidas": concluidas,
            "agendadas": agendadas,
            "cor": cor_do_farol(concluidas, agendadas),
            "corrente": inicio == inicio_da_semana(hoje),
        })
    return trilha


def sem_contato_na_semana(trilha: list[dict]) -> bool:
    """
    O parceiro está na fila de quem precisa de ação AGORA?

    Só o vermelho da semana corrente conta. Amarelo fica de fora de
    propósito: já tem tarefa marcada com alguém, e um KPI que cobra quem já
    agendou vira ruído que se aprende a ignorar. Este número existe para
    produzir ação, e a ação é "marque alguma coisa com esse parceiro".
    """
    for semana in trilha:
        if semana["corrente"]:
            return semana["cor"] == "vermelho"
    return False


def semanas_sem_contato(trilha: list[dict]) -> int:
    """
    Quantas semanas seguidas, contando da corrente para trás, sem verde.

    É a leitura de gravidade que a cor sozinha não dá: uma semana vermelha é
    uma semana corrida; quatro seguidas é uma relação que parou.
    """
    total = 0
    for semana in reversed(trilha):
        if semana["cor"] == "verde":
            break
        total += 1
    return total
