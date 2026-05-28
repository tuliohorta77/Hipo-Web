"""
HIPO — Serviço de classificação do Funil de Vendas (CROmie).

Dois usos distintos, NÃO confundir:

1. Régua de conformidade (aba "Conformidade") — verifica se as
   oportunidades estão com o CROmie bem preenchido. É a régua INTERNA
   de utilização correta do CROmie, mais exigente que o indicador PEX
   oficial (cobra tarefa futura em todas as fases). O percentual NÃO é
   a apuração oficial do PEX.

2. Funil de Vendas (aba "Funil") — visão comercial. Agrega as
   oportunidades ATIVAS por fase x faixa de temperatura. Aqui a
   TEMPERATURA é a previsão de venda: quanto mais alta, mais perto de
   fechar. Por isso a faixa de 90 ("fechando") é separada da de 80
   ("quente") — 90 é a venda iminente.

── Régua de conformidade ──
Regras por fase:
  Fase               | tarefa_futura | temperatura | previsao | ticket
  -------------------|---------------|-------------|----------|--------
  01. Suspect        |      sim      |     —       |    —     |   —
  02. Cadência       |      sim      |     —       |    —     |   —
  03. Qualificação   |      sim      |    sim      |   sim    |   —
  04. Apresentação   |      sim      |    sim      |   sim    |   —
  05. Negociação     |      sim      |    sim      |   sim    |  sim
  06. Conquistado    |  fora da análise

Responsável: SDR (sdr_fr) em Suspect/Cadência; executivo
(executivo_vendas) nas demais fases.

── Regra de tarefa: três estados (v1.3.2) ──
A regra de tarefa deixou de ser binária. Com base nos dados de produção
do CROmie:
  - tarefa_futura = 1  <=>  próxima tarefa é estritamente futura (data > hoje);
  - tarefa_futura = 0 com ult_prox_tarefa = HOJE  ->  tarefa para hoje;
  - tarefa_futura = 0 com data passada ou sem data ->  sem tarefa futura.

Estados resultantes (campo 'estado' da classificação):
  - 'conforme'  : cumpre todas as regras aplicáveis (verde).
  - 'atencao'   : o ÚNICO pendente seria a tarefa, mas há tarefa para
                  HOJE — não conta como problema nem como conforme
                  (amarelo). SAI do cálculo de pct_conforme.
  - 'problema'  : falta tarefa (vencida/ausente) OU falta outra regra
                  (temperatura/previsão/ticket) — vermelho. Se houver
                  tarefa para hoje E outro problema, o estado é
                  'problema' mas a flag tarefa_hoje fica True (badge
                  informativo).

Resumo (resumir_funil) ganha 'atencao_hoje': contagem de OPs em estado
'atencao'. O pct_conforme = conformes / (conformes + nao_conformes)
exclui as de atenção naturalmente.

"Hoje" é injetável (parâmetro 'hoje') para testes determinísticos;
default é date.today() do servidor. O servidor roda em UTC e o CROmie é
horário de SP — a comparação é por DATA e o upload é diário de manhã,
então a borda de fuso é aceitável para v1.

── Funil de Vendas ──
Faixas de temperatura (escala 0..100, valores de 10 em 10):
  - sem      : temperatura nula / 0
  - fria     : 10 a 40
  - morna    : 50 a 70
  - quente   : 80
  - fechando : 90
Temperatura 100 = oportunidade conquistada. Uma OP ATIVA com
temperatura 100 é uma INCOERÊNCIA (provável OP fechada sem atualizar o
status no CROmie). Essas OPs não entram no funil e são sinalizadas na
aba Conformidade.

Valor do funil: coluna proposta_nmrr (receita recorrente da proposta).
Normalmente só preenchida em Apresentação e Negociação — fases
anteriores ficam com valor zero, e isso é esperado.

Tipos das colunas em cliente_oportunidade (conferidos no schema/dados):
  - previsao_preenchido : VARCHAR(10) — "Sim" / "Não"
  - ticket_preenchido   : VARCHAR(10) — "Sim" / "Não"
  - tarefa_futura       : INT          — 0 / 1
  - ult_prox_tarefa     : TIMESTAMPTZ  — última/próxima tarefa (data)
  - temperatura         : NUMERIC      — 0..100, de 10 em 10
  - proposta_nmrr       : NUMERIC      — valor recorrente da proposta
ATENÇÃO: bool() direto numa string NÃO serve — bool("Não") é True em
Python. Por isso as flags de texto passam por _flag_texto().
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Códigos de regra — usados na lista de problemas de cada oportunidade.
REGRA_TAREFA_FUTURA = "tarefa_futura"
REGRA_TEMPERATURA = "temperatura"
REGRA_PREVISAO = "previsao"
REGRA_TICKET = "ticket"

ROTULO_REGRA = {
    REGRA_TAREFA_FUTURA: "Sem tarefa futura",
    REGRA_TEMPERATURA: "Falta temperatura",
    REGRA_PREVISAO: "Falta previsão de fechamento",
    REGRA_TICKET: "Falta valor do ticket",
}

# Estados de conformidade de uma oportunidade analisada (v1.3.2).
ESTADO_CONFORME = "conforme"
ESTADO_ATENCAO = "atencao"
ESTADO_PROBLEMA = "problema"

REGRAS_POR_FASE: dict[str, list[str]] = {
    "01. Suspect":      [REGRA_TAREFA_FUTURA],
    "02. Cadência":     [REGRA_TAREFA_FUTURA],
    "03. Qualificação": [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO],
    "04. Apresentação": [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO],
    "05. Negociação":   [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO,
                         REGRA_TICKET],
}

# Fases que entram na análise (as ativas, na ordem do funil).
FASES_ANALISADAS = [
    "01. Suspect",
    "02. Cadência",
    "03. Qualificação",
    "04. Apresentação",
    "05. Negociação",
]

# Fases iniciais em que o responsável é o SDR (e não o executivo).
FASES_DO_SDR = {"01. Suspect", "02. Cadência"}

# ── Faixas de temperatura (funil de vendas) ──────────────────────────
FAIXA_SEM = "sem"
FAIXA_FRIA = "fria"
FAIXA_MORNA = "morna"
FAIXA_QUENTE = "quente"
FAIXA_FECHANDO = "fechando"

# Ordem canônica das faixas (o frontend renderiza nesta ordem).
FAIXAS_TEMPERATURA = [
    FAIXA_SEM, FAIXA_FRIA, FAIXA_MORNA, FAIXA_QUENTE, FAIXA_FECHANDO,
]

ROTULO_FAIXA = {
    FAIXA_SEM: "Sem temperatura",
    FAIXA_FRIA: "Fria (10–40)",
    FAIXA_MORNA: "Morna (50–70)",
    FAIXA_QUENTE: "Quente (80)",
    FAIXA_FECHANDO: "Fechando (90)",
}

# Faixa de temperatura -> intervalo [min, max] inclusivo. Usado pelo
# router para filtrar o recorte de uma faixa (clique no funil).
# FAIXA_SEM não tem intervalo (é temperatura nula/0) — tratada à parte.
INTERVALO_FAIXA: dict[str, tuple[int, int]] = {
    FAIXA_FRIA:     (10, 40),
    FAIXA_MORNA:    (50, 70),
    FAIXA_QUENTE:   (80, 80),
    FAIXA_FECHANDO: (90, 90),
}

# Temperatura que indica oportunidade conquistada.
TEMPERATURA_CONQUISTADO = 100

# Valores de texto que contam como "sim" nas colunas VARCHAR de flag.
_TEXTO_SIM = {"sim", "s", "true", "1", "verdadeiro", "yes", "y"}


def _flag_texto(valor: Any) -> bool:
    """
    Interpreta uma coluna VARCHAR de flag (ex.: previsao_preenchido).
    NUNCA usar bool() direto: bool("Não") é True em Python.
    """
    if valor is None:
        return False
    return str(valor).strip().lower() in _TEXTO_SIM


def _flag_inteira(valor: Any) -> bool:
    """Interpreta uma coluna INT de flag (tarefa_futura: 0/1)."""
    if valor is None:
        return False
    try:
        return int(valor) > 0
    except (TypeError, ValueError):
        return False


def _data_de(valor: Any) -> date | None:
    """
    Extrai a parte DATA de um campo que pode vir como datetime, date ou
    string ISO. Devolve None se ausente/inválido.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    # String: tenta ISO (YYYY-MM-DD...) pegando os 10 primeiros chars.
    s = str(valor).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _proxima_tarefa_eh_hoje(op: dict, hoje: date) -> bool:
    """
    True quando a próxima/última tarefa registrada (ult_prox_tarefa) cai
    exatamente em 'hoje'. Usado para distinguir o estado de ATENÇÃO
    (tarefa para hoje) do estado de PROBLEMA (tarefa vencida/ausente)
    quando tarefa_futura = 0.
    """
    d = _data_de(op.get("ult_prox_tarefa"))
    return d is not None and d == hoje


def _temperatura_num(op: dict) -> float | None:
    """Devolve a temperatura como float, ou None se ausente/inválida."""
    t = op.get("temperatura")
    if t is None:
        return None
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def _temperatura_preenchida(op: dict) -> bool:
    """Temperatura conta como preenchida se existe e é maior que zero."""
    t = _temperatura_num(op)
    return t is not None and t > 0


def _valor_nmrr(op: dict) -> float:
    """Devolve proposta_nmrr como float; 0.0 se ausente/inválida."""
    v = op.get("proposta_nmrr")
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def faixa_temperatura(op: dict) -> str | None:
    """
    Classifica a oportunidade numa faixa de temperatura do funil:
      - FAIXA_SEM      : temperatura nula ou 0
      - FAIXA_FRIA     : 10 a 40
      - FAIXA_MORNA    : 50 a 70
      - FAIXA_QUENTE   : 80
      - FAIXA_FECHANDO : 90

    Retorna None para temperatura 100 (conquistado) — essa OP NÃO
    entra no funil; ver temperatura_incoerente(). Também retorna None
    para qualquer valor fora das faixas conhecidas (defensivo).
    """
    t = _temperatura_num(op)
    if t is None or t <= 0:
        return FAIXA_SEM
    if 10 <= t <= 40:
        return FAIXA_FRIA
    if 50 <= t <= 70:
        return FAIXA_MORNA
    if t == 80:
        return FAIXA_QUENTE
    if t == 90:
        return FAIXA_FECHANDO
    # 100 (conquistado) ou valor inesperado: fora do funil.
    return None


def temperatura_incoerente(op: dict) -> bool:
    """
    True quando a oportunidade está numa fase ATIVA mas tem
    temperatura 100 — valor reservado a oportunidades conquistadas.
    Rede de segurança contra OP fechada sem atualização de status.
    """
    fase = op.get("fase")
    if fase not in REGRAS_POR_FASE:
        return False
    t = _temperatura_num(op)
    return t is not None and t >= TEMPERATURA_CONQUISTADO


def _txt(valor: Any) -> str | None:
    """Normaliza um campo de texto: strip; vazio vira None."""
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def responsavel_da_op(op: dict) -> str | None:
    """
    Responsável pela oportunidade conforme a fase:
      - Suspect / Cadência -> sdr_fr (o SDR);
      - demais fases       -> executivo_vendas.
    """
    fase = op.get("fase")
    if fase in FASES_DO_SDR:
        return _txt(op.get("sdr_fr"))
    return _txt(op.get("executivo_vendas"))


def _regra_cumprida(op: dict, regra: str) -> bool:
    """Verifica se a oportunidade cumpre uma regra específica."""
    if regra == REGRA_TAREFA_FUTURA:
        return _flag_inteira(op.get("tarefa_futura"))
    if regra == REGRA_TEMPERATURA:
        return _temperatura_preenchida(op)
    if regra == REGRA_PREVISAO:
        return _flag_texto(op.get("previsao_preenchido"))
    if regra == REGRA_TICKET:
        return _flag_texto(op.get("ticket_preenchido"))
    return False


def classificar_oportunidade(op: dict, hoje: date | None = None) -> dict[str, Any]:
    """
    Classifica UMA oportunidade pela régua interna do funil CROmie.

    v1.3.2: introduz três estados (campo 'estado'):
      - ESTADO_CONFORME : cumpre todas as regras aplicáveis.
      - ESTADO_ATENCAO  : o único pendente seria a tarefa, mas há tarefa
                          para HOJE. Não é conforme nem problema. Sai do
                          pct_conforme.
      - ESTADO_PROBLEMA : falta tarefa (vencida/ausente) ou outra regra.

    Mecânica da tarefa-hoje:
      Quando a regra de tarefa NÃO está cumprida (tarefa_futura=0) mas a
      próxima tarefa é HOJE, a regra de tarefa é "neutralizada": sai da
      lista de problemas e a flag tarefa_hoje vira True. Se, removida a
      tarefa, não sobrar nenhum outro problema -> ESTADO_ATENCAO. Se
      sobrar outro problema (temperatura/previsão/ticket) -> ESTADO_PROBLEMA
      com tarefa_hoje=True (badge informativo).

    Args:
      op: dict da oportunidade (linha de cliente_oportunidade).
      hoje: data de referência (default date.today()). Injetável p/ testes.

    Returns dict com: fase_analisada, estado, conforme, problemas,
    problemas_rotulos, regras_aplicaveis, temperatura_incoerente,
    tarefa_hoje.

    Compat: 'conforme' (bool) é mantido — True apenas no ESTADO_CONFORME.
    """
    if hoje is None:
        hoje = date.today()

    fase = op.get("fase")
    regras = REGRAS_POR_FASE.get(fase)
    incoerente = temperatura_incoerente(op)

    if regras is None:
        return {
            "fase_analisada": False,
            "estado": ESTADO_PROBLEMA,
            "conforme": False,
            "problemas": [],
            "problemas_rotulos": [],
            "regras_aplicaveis": [],
            "temperatura_incoerente": incoerente,
            "tarefa_hoje": False,
        }

    problemas = [r for r in regras if not _regra_cumprida(op, r)]

    # Regra de tarefa não cumprida + próxima tarefa é hoje => neutraliza
    # a regra de tarefa (vira "atenção"), removendo-a dos problemas.
    tarefa_hoje = False
    if (
        REGRA_TAREFA_FUTURA in problemas
        and _proxima_tarefa_eh_hoje(op, hoje)
    ):
        tarefa_hoje = True
        problemas = [p for p in problemas if p != REGRA_TAREFA_FUTURA]

    if problemas:
        estado = ESTADO_PROBLEMA
    elif tarefa_hoje:
        estado = ESTADO_ATENCAO
    else:
        estado = ESTADO_CONFORME

    return {
        "fase_analisada": True,
        "estado": estado,
        "conforme": estado == ESTADO_CONFORME,
        "problemas": problemas,
        "problemas_rotulos": [ROTULO_REGRA[r] for r in problemas],
        "regras_aplicaveis": list(regras),
        "temperatura_incoerente": incoerente,
        "tarefa_hoje": tarefa_hoje,
    }


def resumir_funil(oportunidades: list[dict], hoje: date | None = None) -> dict[str, Any]:
    """
    Classifica uma lista de oportunidades (régua de conformidade) e
    devolve cada uma anotada + um resumo agregado.

    Cada item ganha 'classificacao' e 'responsavel'. O 'resumo' inclui:
      - total_analisadas : conformes + nao_conformes (NÃO inclui atenção)
      - conformes        : estado 'conforme'
      - nao_conformes    : estado 'problema'
      - atencao_hoje     : estado 'atencao' (tarefa para hoje, v1.3.2)
      - pct_conforme     : conformes / total_analisadas (atenção fora)
      - fora_da_analise  : fases não analisadas (ex.: Conquistado)
      - temperatura_incoerente : OPs com temp 100 em fase ativa

    'hoje' é repassado a classificar_oportunidade (injetável p/ testes).
    """
    itens: list[dict] = []
    conformes = 0
    nao_conformes = 0
    atencao = 0
    fora = 0
    incoerentes = 0
    por_fase: dict[str, dict[str, int]] = {
        f: {"total": 0, "conformes": 0, "nao_conformes": 0, "atencao": 0}
        for f in FASES_ANALISADAS
    }

    for op in oportunidades:
        cls = classificar_oportunidade(op, hoje=hoje)
        item = dict(op)
        item["classificacao"] = cls
        item["responsavel"] = responsavel_da_op(op)
        itens.append(item)

        if cls["temperatura_incoerente"]:
            incoerentes += 1

        if not cls["fase_analisada"]:
            fora += 1
            continue

        fase = op.get("fase")
        bucket = por_fase.get(fase)
        estado = cls["estado"]
        if estado == ESTADO_CONFORME:
            conformes += 1
            if bucket:
                bucket["total"] += 1
                bucket["conformes"] += 1
        elif estado == ESTADO_ATENCAO:
            atencao += 1
            if bucket:
                bucket["total"] += 1
                bucket["atencao"] += 1
        else:  # ESTADO_PROBLEMA
            nao_conformes += 1
            if bucket:
                bucket["total"] += 1
                bucket["nao_conformes"] += 1

    total_analisadas = conformes + nao_conformes
    pct = round(conformes / total_analisadas * 100, 2) if total_analisadas else 0.0

    return {
        "itens": itens,
        "resumo": {
            "total_analisadas": total_analisadas,
            "conformes": conformes,
            "nao_conformes": nao_conformes,
            "atencao_hoje": atencao,
            "pct_conforme": pct,
            "fora_da_analise": fora,
            "temperatura_incoerente": incoerentes,
        },
        "por_fase": por_fase,
    }


def montar_funil(oportunidades: list[dict]) -> dict[str, Any]:
    """
    Funil de Vendas — agrega as oportunidades ATIVAS por fase x faixa
    de temperatura.

    NÃO MUDOU na v1.3.2 — a aba Funil é a visão comercial e ignora a
    régua de conformidade (e portanto o estado de atenção/tarefa-hoje).

    Considera apenas as 5 fases ativas (Conquistado fora).
    Oportunidades com temperatura 100 não entram nas faixas — são
    contadas à parte como 'temperatura_incoerente'.

    O valor (proposta_nmrr) é somado por fase E por faixa, para que o
    frontend mostre tanto o total da fase quanto o de cada recorte.

    Returns:
      dict com:
        - fases: lista na ordem do funil; cada item:
            { 'fase', 'total', 'valor',
              'faixas': { <faixa>: {'total': int, 'valor': float} } }
          'total' e 'valor' da fase = soma das 5 faixas (sem as
          incoerentes).
        - total_geral: soma de 'total' de todas as fases.
        - valor_geral: soma de 'valor' de todas as fases.
        - temperatura_incoerente: nº de OPs ativas com temp 100.
    """
    fases: dict[str, dict[str, dict[str, float]]] = {
        f: {faixa: {"total": 0, "valor": 0.0} for faixa in FAIXAS_TEMPERATURA}
        for f in FASES_ANALISADAS
    }
    incoerentes = 0

    for op in oportunidades:
        fase = op.get("fase")
        if fase not in fases:
            continue
        if temperatura_incoerente(op):
            incoerentes += 1
            continue
        faixa = faixa_temperatura(op)
        if faixa is None:
            continue
        slot = fases[fase][faixa]
        slot["total"] += 1
        slot["valor"] += _valor_nmrr(op)

    lista = []
    total_geral = 0
    valor_geral = 0.0
    for f in FASES_ANALISADAS:
        faixas = fases[f]
        total = sum(int(faixas[k]["total"]) for k in FAIXAS_TEMPERATURA)
        valor = sum(faixas[k]["valor"] for k in FAIXAS_TEMPERATURA)
        total_geral += total
        valor_geral += valor
        # Arredonda o valor de cada faixa para 2 casas (evita ruído float).
        faixas_out = {
            k: {"total": int(faixas[k]["total"]),
                "valor": round(faixas[k]["valor"], 2)}
            for k in FAIXAS_TEMPERATURA
        }
        lista.append({
            "fase": f,
            "total": total,
            "valor": round(valor, 2),
            "faixas": faixas_out,
        })

    return {
        "fases": lista,
        "total_geral": total_geral,
        "valor_geral": round(valor_geral, 2),
        "temperatura_incoerente": incoerentes,
    }
