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

Responsável pela oportunidade (depende da fase):
  - Fases 01. Suspect e 02. Cadência -> o SDR (coluna sdr_fr).
  - Demais fases ativas              -> o executivo (executivo_vendas).
  Nas fases iniciais quem toca a oportunidade é o SDR; a partir da
  Qualificação ela passa para o executivo de vendas.

Tipos das colunas em cliente_oportunidade (conferidos no schema/dados):
  - previsao_preenchido : VARCHAR(10) — texto "Sim" / "Não"
  - ticket_preenchido   : VARCHAR(10) — texto "Sim" / "Não"
  - tarefa_futura       : INT          — 0 (não) / 1 (sim)
  - temperatura         : NUMERIC      — preenchida quando > 0
ATENÇÃO: bool() direto numa string NÃO serve — bool("Não") é True em
Python. Por isso as flags de texto passam por _flag_texto().
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

# Fases iniciais em que o responsável é o SDR (e não o executivo).
FASES_DO_SDR = {"01. Suspect", "02. Cadência"}

# Valores de texto que contam como "sim" nas colunas VARCHAR de flag.
# A base usa "Sim"/"Não"; aceitamos variações por robustez (acento,
# caixa, espaços, e formas alternativas que outro export possa trazer).
_TEXTO_SIM = {"sim", "s", "true", "1", "verdadeiro", "yes", "y"}


def _flag_texto(valor: Any) -> bool:
    """
    Interpreta uma coluna VARCHAR de flag (ex.: previsao_preenchido).

    NUNCA usar bool() direto: bool("Não") é True em Python. Esta função
    normaliza o texto e compara contra o conjunto de valores "sim".
    """
    if valor is None:
        return False
    return str(valor).strip().lower() in _TEXTO_SIM


def _flag_inteira(valor: Any) -> bool:
    """
    Interpreta uma coluna INT de flag (tarefa_futura: 0/1).
    Qualquer valor > 0 conta como verdadeiro.
    """
    if valor is None:
        return False
    try:
        return int(valor) > 0
    except (TypeError, ValueError):
        return False


def _temperatura_preenchida(op: dict) -> bool:
    """Temperatura conta como preenchida se existe e é maior que zero."""
    t = op.get("temperatura")
    if t is None:
        return False
    try:
        return float(t) > 0
    except (TypeError, ValueError):
        return False


def _txt(valor: Any) -> str | None:
    """Normaliza um campo de texto: strip; vazio vira None."""
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def responsavel_da_op(op: dict) -> str | None:
    """
    Devolve o responsável pela oportunidade conforme a fase:
      - Suspect / Cadência -> sdr_fr (o SDR);
      - demais fases       -> executivo_vendas.
    Retorna None se a coluna correspondente estiver vazia.
    """
    fase = op.get("fase")
    if fase in FASES_DO_SDR:
        return _txt(op.get("sdr_fr"))
    return _txt(op.get("executivo_vendas"))


def _regra_cumprida(op: dict, regra: str) -> bool:
    """Verifica se a oportunidade cumpre uma regra específica."""
    if regra == REGRA_TAREFA_FUTURA:
        # Coluna INT 0/1.
        return _flag_inteira(op.get("tarefa_futura"))
    if regra == REGRA_TEMPERATURA:
        # Coluna NUMERIC.
        return _temperatura_preenchida(op)
    if regra == REGRA_PREVISAO:
        # Coluna VARCHAR "Sim"/"Não".
        return _flag_texto(op.get("previsao_preenchido"))
    if regra == REGRA_TICKET:
        # Coluna VARCHAR "Sim"/"Não".
        return _flag_texto(op.get("ticket_preenchido"))
    # Regra desconhecida: trata como não cumprida (defensivo).
    return False


def classificar_oportunidade(op: dict) -> dict[str, Any]:
    """
    Classifica UMA oportunidade pela régua interna do funil CROmie.

    Args:
      op: dict de cliente_oportunidade com 'fase', 'tarefa_futura' (int),
          'previsao_preenchido' (texto), 'ticket_preenchido' (texto) e
          'temperatura' (numérico).

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

    Cada item ganha duas chaves novas:
      - 'classificacao': resultado de classificar_oportunidade();
      - 'responsavel'  : o responsável pela fase (SDR ou executivo).

    Só oportunidades em fase analisada entram no cálculo do percentual;
    oportunidades fora da análise (Conquistado etc.) são contadas à
    parte e não afetam o '% conforme'.

    Returns:
      dict com:
        - itens: list[dict] — cada oportunidade + 'classificacao' + 'responsavel'.
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
        item["responsavel"] = responsavel_da_op(op)
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
