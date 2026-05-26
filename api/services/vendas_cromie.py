"""
HIPO — Serviço de classificação do Funil de Vendas (CROmie).

Implementa a "régua interna" de utilização correta do CROmie, inspirada
no indicador PEX "Utilização correta do CROmie" (Metade 1 — Funil de
Vendas), porém MAIS EXIGENTE que o indicador oficial:

  >>> ATENÇÃO: esta NÃO é a apuração oficial do PEX. <<<

  O indicador PEX cobra "tarefa futura" apenas nas fases Suspect,
  Cadência e Qualificação. Por decisão de gestão da unidade, esta régua
  cobra tarefa futura em TODAS as fases ativas (boa prática: toda
  oportunidade aberta deve ter um próximo passo agendado).

  Consequência: o "% conforme" calculado aqui tende a ser MENOR que o
  número que a consultoria de campo da Omie apura. Isso é intencional —
  é uma régua interna, e a tela deixa isso explícito.

  A Metade 2 do indicador PEX (gestão de parceiro/não-parceiro) NÃO é
  avaliada aqui.

Regras por fase (régua interna):

  Fase               | tarefa_futura | temperatura | previsao | ticket
  -------------------|---------------|-------------|----------|--------
  01. Suspect        |      sim      |     —       |    —     |   —
  02. Cadência       |      sim      |     —       |    —     |   —
  03. Qualificação   |      sim      |    sim      |   sim    |   —
  04. Apresentação   |      sim      |    sim      |   sim    |   —
  05. Negociação     |      sim      |    sim      |   sim    |  sim
  06. Conquistado    |  fora da análise (não é oportunidade ativa)

Uma oportunidade é "conforme" se cumpre TODAS as regras aplicáveis à
sua fase. Se falha em qualquer uma, é "não conforme" e o serviço lista
exatamente quais regras falharam.
"""
from __future__ import annotations

from typing import Any

# Códigos de regra — usados na lista de problemas de cada oportunidade.
REGRA_TAREFA_FUTURA = "tarefa_futura"
REGRA_TEMPERATURA = "temperatura"
REGRA_PREVISAO = "previsao"
REGRA_TICKET = "ticket"

# Rótulo legível de cada regra (o frontend pode usar direto).
ROTULO_REGRA = {
    REGRA_TAREFA_FUTURA: "Sem tarefa futura",
    REGRA_TEMPERATURA: "Falta temperatura",
    REGRA_PREVISAO: "Falta previsão de fechamento",
    REGRA_TICKET: "Falta valor do ticket",
}

# Quais regras se aplicam a cada fase (régua interna).
# A chave é a fase EXATA como gravada em cliente_oportunidade.fase.
REGRAS_POR_FASE: dict[str, list[str]] = {
    "01. Suspect":      [REGRA_TAREFA_FUTURA],
    "02. Cadência":     [REGRA_TAREFA_FUTURA],
    "03. Qualificação": [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO],
    "04. Apresentação": [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO],
    "05. Negociação":   [REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA, REGRA_PREVISAO,
                         REGRA_TICKET],
    # "06. Conquistado" não entra: não é oportunidade ativa.
}

# Fases que entram na análise (as ativas, na ordem do funil).
FASES_ANALISADAS = [
    "01. Suspect",
    "02. Cadência",
    "03. Qualificação",
    "04. Apresentação",
    "05. Negociação",
]


def _temperatura_preenchida(op: dict) -> bool:
    """Temperatura conta como preenchida se existe e é maior que zero."""
    t = op.get("temperatura")
    if t is None:
        return False
    try:
        return float(t) > 0
    except (TypeError, ValueError):
        return False


def _regra_cumprida(op: dict, regra: str) -> bool:
    """Verifica se a oportunidade cumpre uma regra específica."""
    if regra == REGRA_TAREFA_FUTURA:
        return bool(op.get("tarefa_futura"))
    if regra == REGRA_TEMPERATURA:
        return _temperatura_preenchida(op)
    if regra == REGRA_PREVISAO:
        return bool(op.get("previsao_preenchido"))
    if regra == REGRA_TICKET:
        return bool(op.get("ticket_preenchido"))
    # Regra desconhecida: trata como não cumprida (defensivo).
    return False


def classificar_oportunidade(op: dict) -> dict[str, Any]:
    """
    Classifica UMA oportunidade pela régua interna do funil CROmie.

    Args:
      op: dict com pelo menos 'fase' e as flags 'tarefa_futura',
          'previsao_preenchido', 'ticket_preenchido' e 'temperatura'.

    Returns:
      dict com:
        - fase_analisada: bool — False se a fase está fora da análise
          (ex.: Conquistado, ou fase desconhecida).
        - conforme: bool — True se cumpre todas as regras da fase.
          Sempre False quando fase_analisada é False.
        - problemas: list[str] — códigos das regras que falharam.
        - problemas_rotulos: list[str] — os mesmos, em texto legível.
        - regras_aplicaveis: list[str] — regras que a fase exige.
    """
    fase = op.get("fase")
    regras = REGRAS_POR_FASE.get(fase)

    if regras is None:
        # Fase fora da análise (Conquistado, nula, ou valor inesperado).
        return {
            "fase_analisada": False,
            "conforme": False,
            "problemas": [],
            "problemas_rotulos": [],
            "regras_aplicaveis": [],
        }

    problemas = [r for r in regras if not _regra_cumprida(op, r)]

    return {
        "fase_analisada": True,
        "conforme": len(problemas) == 0,
        "problemas": problemas,
        "problemas_rotulos": [ROTULO_REGRA[r] for r in problemas],
        "regras_aplicaveis": list(regras),
    }


def resumir_funil(oportunidades: list[dict]) -> dict[str, Any]:
    """
    Classifica uma lista de oportunidades e devolve cada uma anotada
    + um resumo agregado.

    Só oportunidades em fase analisada entram no cálculo do percentual;
    oportunidades fora da análise (Conquistado etc.) são contadas à
    parte e não afetam o '% conforme'.

    Args:
      oportunidades: lista de dicts de cliente_oportunidade.

    Returns:
      dict com:
        - itens: list[dict] — cada oportunidade + a chave 'classificacao'.
        - resumo: dict — total_analisadas, conformes, nao_conformes,
          pct_conforme (0..100, arredondado a 2 casas), fora_da_analise.
        - por_fase: dict[fase] -> {total, conformes, nao_conformes}.
    """
    itens: list[dict] = []
    conformes = 0
    nao_conformes = 0
    fora = 0
    por_fase: dict[str, dict[str, int]] = {
        f: {"total": 0, "conformes": 0, "nao_conformes": 0}
        for f in FASES_ANALISADAS
    }

    for op in oportunidades:
        cls = classificar_oportunidade(op)
        item = dict(op)
        item["classificacao"] = cls
        itens.append(item)

        if not cls["fase_analisada"]:
            fora += 1
            continue

        fase = op.get("fase")
        bucket = por_fase.get(fase)
        if cls["conforme"]:
            conformes += 1
            if bucket:
                bucket["total"] += 1
                bucket["conformes"] += 1
        else:
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
            "pct_conforme": pct,
            "fora_da_analise": fora,
        },
        "por_fase": por_fase,
    }
