"""
HIPO — O conteúdo do CRM no fechamento diário.

O QUE ESTE MÓDULO EXISTE PARA RESOLVER

`services/telemetria.py` responde "quem usou o sistema". Este responde "o que
tem para fazer no negócio" — que é a pergunta que o dono da operação fez ao
ler o primeiro e-mail.

A distinção não é estética. A narrativa da IA só pode falar do que está no
JSON: com `operacao()` mandando apenas contagens (`tarefas_em_atraso: 22`), o
modelo não tem como apontar UMA oportunidade, e pedir que aponte é pedir que
invente. A guarda de `validacao_numerica` não pegaria — inventar nome não é
inventar número. Colocar as oportunidades no payload é o que torna a pergunta
respondível sem inventar.

DUAS LISTAS, NÃO UMA RANQUEADA

  precisa_de_acao   — a promessa que furou: previsão vencida, oportunidade
                      sem próxima tarefa, negócio parado numa fase avançada.
  perto_de_fechar   — o que dá para ganhar: temperatura alta, previsão nos
                      próximos dias.

Uma lista só, ordenada por um score, obrigaria o leitor a adivinhar por que
cada linha está ali. Duas listas com MOTIVO escrito em cada item respondem
sozinhas — e dão à IA material concreto para narrar.

AÇÃO GANHA DE CELEBRAÇÃO. Uma oportunidade que dispara sinal dos dois lados
aparece só em `precisa_de_acao`. "Quente e sem próximo passo" é a coisa mais
urgente do CRM inteiro, e mostrá-la na lista das boas notícias esconderia
exatamente o que precisa de gente.

TEMPERATURA É DADO, NÃO PALPITE. A coluna existe, é obrigatória para
oportunidade ativa (`ck_opp_temperatura_ativa`) e é o próprio time que
preenche. Inventar um "score de maturidade" paralelo seria criar uma segunda
fonte de verdade para a mesma pergunta.

`hoje` é sempre parâmetro, nunca `date.today()` — mesma regra de
services/tarefa.py e services/parceiro.py: teste determinístico sem mockar o
relógio.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# ── Limiares ────────────────────────────────────────────────────────────
#
# PREVISAO_PROXIMA_DIAS: uma semana. É o horizonte em que ainda dá para fazer
# alguma coisa a respeito — previsão para daqui a 20 dias não é assunto de
# hoje, e enchê-la no e-mail treina o leitor a pular a seção.
PREVISAO_PROXIMA_DIAS = 7

# PARADA_DIAS: duas semanas sem nenhuma alteração numa fase avançada. Menos
# que isso pega quem está só esperando o cliente responder; mais que isso e o
# negócio já esfriou antes de alguém ser avisado.
PARADA_DIAS = 14

# TEMPERATURA_QUENTE: a escala é 0..90 de dez em dez. 70 para cima é o terço
# superior — o time já disse que acredita nesse negócio.
TEMPERATURA_QUENTE = 70

# Fases em que "parado" significa alguma coisa. Suspect parado é normal: é a
# boca do funil, ninguém tocou ainda de propósito.
FASES_AVANCADAS = ("apresentacao", "negociacao")

# Quantos itens por lista no e-mail. O resto vira "e mais N".
#
# Cinco porque a lista existe para produzir ação hoje, e ninguém age sobre
# vinte linhas. O número total continua aparecendo, então nada some — só sai
# do destaque.
LIMITE_DESTAQUES = 5


@dataclass(frozen=True)
class Destaque:
    """Uma oportunidade escolhida, com o porquê junto."""
    numero: str
    conta: str
    fase: str
    status: str
    temperatura: int | None
    valor: float | None
    previsao: date | None
    motivos: tuple[str, ...]
    peso: int

    def como_dict(self) -> dict:
        return {
            "numero": self.numero,
            "conta": self.conta,
            "fase": self.fase,
            "status": self.status,
            "temperatura": self.temperatura,
            "valor": self.valor,
            "previsao": self.previsao.isoformat() if self.previsao else None,
            "motivos": list(self.motivos),
        }


def dias_ate(alvo: date | None, hoje: date) -> int | None:
    """
    Dias de `hoje` até `alvo`. Negativo = já passou. None se não há data.

    >>> dias_ate(date(2026, 9, 4), date(2026, 9, 1))
    3
    >>> dias_ate(date(2026, 8, 25), date(2026, 9, 1))
    -7
    >>> dias_ate(None, date(2026, 9, 1)) is None
    True
    """
    return None if alvo is None else (alvo - hoje).days


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular}" if n == 1 else f"{n} {plural}"


def sinais_de_acao(
    *,
    fase: str,
    previsao: date | None,
    dias_parada: int | None,
    tem_proxima_tarefa: bool,
    hoje: date,
) -> list[tuple[int, str]]:
    """
    (peso, motivo) para cada furo encontrado. Lista vazia = nada a cobrar.

    A ORDEM DOS PESOS É UM ARGUMENTO, não um ajuste fino:

      120  previsão vencida ...... a promessa JÁ furou; é o único sinal sobre
                                   um compromisso que deixou de ser cumprido.
       80  sem próxima tarefa .... é o buraco que o CRM existe para tapar.
                                   Não é atraso ainda, é a garantia de que vai
                                   virar um.
       50  parada em fase avançada  vazamento lento: ninguém quebrou promessa
                                   nenhuma, o negócio só está esfriando.

    Vencida pesa mais que "sem tarefa" porque uma tem data e a outra não: dá
    para responder à primeira hoje e a segunda em qualquer dia desta semana.

    >>> sinais_de_acao(fase="negociacao", previsao=date(2026, 8, 25),
    ...                dias_parada=3, tem_proxima_tarefa=True,
    ...                hoje=date(2026, 9, 1))
    [(120, 'previsão venceu há 7 dias')]
    >>> sinais_de_acao(fase="suspect", previsao=None, dias_parada=90,
    ...                tem_proxima_tarefa=True, hoje=date(2026, 9, 1))
    []
    """
    achados: list[tuple[int, str]] = []

    dias = dias_ate(previsao, hoje)
    if dias is not None and dias < 0:
        achados.append((120, f"previsão venceu há {_plural(-dias, 'dia', 'dias')}"))

    if not tem_proxima_tarefa:
        achados.append((80, "sem próxima tarefa marcada"))

    if (
        fase in FASES_AVANCADAS
        and dias_parada is not None
        and dias_parada >= PARADA_DIAS
    ):
        achados.append((50, f"parada há {_plural(dias_parada, 'dia', 'dias')}"))

    return achados


def sinais_de_fechamento(
    *,
    temperatura: int | None,
    previsao: date | None,
    hoje: date,
) -> list[tuple[int, str]]:
    """
    (peso, motivo) para o que está maduro. Lista vazia = nada a comemorar.

    >>> sinais_de_fechamento(temperatura=80, previsao=None, hoje=date(2026, 9, 1))
    [(60, 'temperatura 80')]
    >>> sinais_de_fechamento(temperatura=20, previsao=date(2026, 9, 3),
    ...                      hoje=date(2026, 9, 1))
    [(70, 'previsão em 2 dias')]
    """
    achados: list[tuple[int, str]] = []

    dias = dias_ate(previsao, hoje)
    if dias is not None and 0 <= dias <= PREVISAO_PROXIMA_DIAS:
        quando = "previsão é hoje" if dias == 0 else f"previsão em {_plural(dias, 'dia', 'dias')}"
        achados.append((70, quando))

    if temperatura is not None and temperatura >= TEMPERATURA_QUENTE:
        achados.append((60, f"temperatura {temperatura}"))

    return achados


def classificar(
    *,
    numero: str,
    conta: str,
    fase: str,
    status: str,
    temperatura: int | None,
    valor: float | None,
    previsao: date | None,
    dias_parada: int | None,
    tem_proxima_tarefa: bool,
    hoje: date,
) -> tuple[str | None, Destaque | None]:
    """
    Devolve ('acao'|'fechar'|None, Destaque|None) para UMA oportunidade.

    Ação ganha de celebração — ver o docstring do módulo. Oportunidade sem
    sinal nenhum devolve (None, None) e não entra em lista alguma: o e-mail
    mostra o que precisa de gente, não o inventário.
    """
    acao = sinais_de_acao(
        fase=fase, previsao=previsao, dias_parada=dias_parada,
        tem_proxima_tarefa=tem_proxima_tarefa, hoje=hoje,
    )
    if acao:
        escolhidos, categoria = acao, "acao"
    else:
        fechar = sinais_de_fechamento(
            temperatura=temperatura, previsao=previsao, hoje=hoje,
        )
        if not fechar:
            return None, None
        escolhidos, categoria = fechar, "fechar"

    return categoria, Destaque(
        numero=numero, conta=conta, fase=fase, status=status,
        temperatura=temperatura, valor=valor, previsao=previsao,
        motivos=tuple(m for _, m in escolhidos),
        peso=sum(p for p, _ in escolhidos),
    )


def ordenar(destaques: list[Destaque]) -> list[Destaque]:
    """
    Peso primeiro, valor como desempate, número como último critério.

    O VALOR NÃO ENTRA NO PESO, só desempata. Se entrasse, um contrato grande e
    saudável passaria na frente de um pequeno com a previsão vencida — e a
    lista deixaria de responder "o que precisa de mim" para responder "o que
    vale mais", que é outra pergunta e já tem o funil para respondê-la.

    `numero` no fim garante ordem estável entre iguais: sem ele, dois itens
    empatados trocariam de lugar entre um e-mail e outro sem nada ter mudado.
    """
    return sorted(
        destaques,
        key=lambda d: (-d.peso, -(d.valor or 0), d.numero),
    )


def cortar(destaques: list[Destaque], limite: int = LIMITE_DESTAQUES) -> tuple[list[dict], int]:
    """
    Top `limite` como dict, mais quantos ficaram de fora.

    >>> cortar([], 5)
    ([], 0)
    """
    ordenados = ordenar(destaques)
    return [d.como_dict() for d in ordenados[:limite]], max(0, len(ordenados) - limite)


# ════════════════════════════════════════════════════════════════════════
# As consultas. Mesma organização de services/telemetria.py: as regras acima
# são puras e testáveis sem Postgres; daqui para baixo é leitura do banco.
# ════════════════════════════════════════════════════════════════════════

_SQL_OPORTUNIDADES = f"""
    SELECT o.numero,
           c.razao_social                                        AS conta,
           o.fase, o.status, o.temperatura,
           o.valor_mensalidade                                   AS valor,
           o.previsao_fechamento                                 AS previsao,
           ($1::date - (o.atualizado_em AT TIME ZONE $2::text)::date) AS dias_parada,
           EXISTS (
               SELECT 1 FROM tarefas t
                WHERE t.oportunidade_id = o.id
                  AND t.concluida_em IS NULL
                  AND t.cancelada_em IS NULL
           )                                                     AS tem_proxima_tarefa
      FROM oportunidades o
      JOIN contas c ON c.id = o.conta_id
     WHERE o.status IN ('ativa', 'suspensa')
"""

# Parceiro que JÁ indicou e esfriou é candidato melhor que parceiro que nunca
# indicou: tem histórico, sabe o que a gente vende e já viu dar certo. Por
# isso `indicacoes > 0` e a ordenação por conquistadas.
#
# `finder_conta_id` é a ligação — a mesma que a tela de Parceiros usa. A
# última indicação olha TODA a história, nunca um recorte: é a armadilha
# central da Sprint 6, com teste de regressão dedicado lá.
#
# O FUSO É $1 AQUI, e $2 nas outras duas. Não por capricho: esta consulta não
# usa a data de referência, e parâmetro declarado e não usado faz o Postgres
# recusar a preparação inteira com `could not determine data type of
# parameter $1`. Manter a numeração "bonita" custaria um erro em produção às
# 03:10 da manhã.
_SQL_PARCEIROS = """
    SELECT c.razao_social                                          AS conta,
           count(o.id)                                             AS indicacoes,
           count(o.id) FILTER (WHERE o.status = 'conquistado')      AS conquistadas,
           count(o.id) FILTER (WHERE o.status IN ('ativa','suspensa')) AS em_aberto,
           (max(o.criado_em) AT TIME ZONE $1::text)::date          AS ultima_indicacao
      FROM contas c
      JOIN oportunidades o ON o.finder_conta_id = c.id
     WHERE c.eh_finder AND c.ativo
     GROUP BY c.id, c.razao_social
"""

_SQL_TAREFAS_ATRASADAS = """
    SELECT t.titulo,
           u.nome                                              AS responsavel,
           ($1::date - (t.prazo AT TIME ZONE $2::text)::date)   AS dias_atraso,
           o.numero                                            AS oportunidade,
           pc.razao_social                                     AS parceiro
      FROM tarefas t
      JOIN usuarios u       ON u.id = t.responsavel_id
      LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
      LEFT JOIN contas pc       ON pc.id = t.conta_id
     WHERE t.concluida_em IS NULL
       AND t.cancelada_em IS NULL
       AND (t.prazo AT TIME ZONE $2::text)::date <= $1::date
     ORDER BY 3 DESC, t.prazo
     LIMIT $3
"""


async def conteudo(conn, dia: date, fuso: str = "America/Sao_Paulo") -> dict:
    """
    O que o CRM tem para fazer, na data de referência do fechamento.

    NÃO É RECORTE DO DIA. Diferente de `telemetria.operacao()`, que conta o que
    aconteceu NAQUELE dia, isto é o ESTADO em aberto: uma oportunidade com a
    previsão vencida em julho continua sendo assunto hoje. Recortar por dia
    esvaziaria a lista justamente nos dias parados, que são quando ela mais
    importa.
    """
    from services import parceiro as svc_parceiro

    linhas = await conn.fetch(_SQL_OPORTUNIDADES, dia, fuso)

    acao: list[Destaque] = []
    fechar: list[Destaque] = []
    for r in linhas:
        categoria, d = classificar(
            numero=r["numero"], conta=r["conta"], fase=r["fase"], status=r["status"],
            temperatura=r["temperatura"],
            valor=float(r["valor"]) if r["valor"] is not None else None,
            previsao=r["previsao"], dias_parada=r["dias_parada"],
            tem_proxima_tarefa=r["tem_proxima_tarefa"], hoje=dia,
        )
        if categoria == "acao":
            acao.append(d)
        elif categoria == "fechar":
            fechar.append(d)

    lista_acao, mais_acao = cortar(acao)
    lista_fechar, mais_fechar = cortar(fechar)

    # ── Parceiros ────────────────────────────────────────────────────────
    parceiros: list[dict] = []
    for r in await conn.fetch(_SQL_PARCEIROS, fuso):
        sit = svc_parceiro.situacao(r["ultima_indicacao"], hoje=dia)
        if sit not in ("esfriando", "dormente"):
            continue
        parceiros.append({
            "conta": r["conta"],
            "situacao": sit,
            "indicacoes": r["indicacoes"],
            "conquistadas": r["conquistadas"],
            "em_aberto": r["em_aberto"],
            "dias_sem_indicar": (dia - r["ultima_indicacao"]).days,
        })
    # Quem mais converteu primeiro: é o parceiro cuja reativação vale mais, e
    # o argumento da conversa já vem pronto ("suas indicações fecharam N").
    parceiros.sort(key=lambda p: (-p["conquistadas"], -p["indicacoes"], p["conta"]))
    mais_parceiros = max(0, len(parceiros) - LIMITE_DESTAQUES)
    parceiros = parceiros[:LIMITE_DESTAQUES]

    # ── Tarefas atrasadas ────────────────────────────────────────────────
    atrasadas = [
        {
            "titulo": r["titulo"],
            "responsavel": r["responsavel"],
            "dias_atraso": r["dias_atraso"],
            "alvo": r["oportunidade"] or r["parceiro"] or "—",
        }
        for r in await conn.fetch(_SQL_TAREFAS_ATRASADAS, dia, fuso, LIMITE_DESTAQUES)
    ]
    total_atrasadas = await conn.fetchval(f"""
        SELECT count(*) FROM tarefas t
         WHERE t.concluida_em IS NULL AND t.cancelada_em IS NULL
           AND (t.prazo AT TIME ZONE $2::text)::date <= $1::date
    """, dia, fuso)

    return {
        "precisa_de_acao": lista_acao,
        "precisa_de_acao_mais": mais_acao,
        "perto_de_fechar": lista_fechar,
        "perto_de_fechar_mais": mais_fechar,
        "parceiros_para_acionar": parceiros,
        "parceiros_para_acionar_mais": mais_parceiros,
        "tarefas_atrasadas": atrasadas,
        "tarefas_atrasadas_total": total_atrasadas or 0,
        "totais": {
            "oportunidades_abertas": len(linhas),
            "com_acao_pendente": len(acao),
            "perto_de_fechar": len(fechar),
        },
    }
