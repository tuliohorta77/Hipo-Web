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
