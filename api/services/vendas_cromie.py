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

Funil de Vendas (aba "Funil"):
  Agrega as oportunidades ATIVAS por fase x faixa de temperatura.
  Faixas de temperatura (escala 0..100, valores de 10 em 10):
    - sem    : temperatura nula (não preenchida)
    - fria   : 10 a 40
    - morna  : 50 a 70
    - quente : 80 a 90
  Temperatura 100 = oportunidade conquistada. Uma OP ATIVA com
  temperatura 100 é uma INCOERÊNCIA (provavelmente foi fechada e o
  status não foi atualizado no CROmie). Essas OPs:
    - NÃO entram no funil (são excluídas das faixas);
    - são sinalizadas na aba Conformidade (flag temperatura_incoerente).

Tipos das colunas em cliente_oportunidade (conferidos no schema/dados):
  - previsao_preenchido : VARCHAR(10) — texto "Sim" / "Não"
  - ticket_preenchido   : VARCHAR(10) — texto "Sim" / "Não"
  - tarefa_futura       : INT          — 0 (não) / 1 (sim)
  - temperatura         : NUMERIC      — 0..100, de 10 em 10
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

# ── Faixas de temperatura (funil) ────────────────────────────────
# Códigos das faixas, na ordem fria -> quente.
FAIXA_SEM = "sem"
FAIXA_FRIA = "fria"
FAIXA_MORNA = "morna"
FAIXA_QUENTE = "quente"

# Ordem canônica das faixas (o frontend renderiza nesta ordem).
FAIXAS_TEMPERATURA = [FAIXA_SEM, FAIXA_FRIA, FAIXA_MORNA, FAIXA_QUENTE]

# Rótulo legível de cada faixa.
ROTULO_FAIXA = {
    FAIXA_SEM: "Sem temperatura",
    FAIXA_FRIA: "Fria (10–40)",
    FAIXA_MORNA: "Morna (50–70)",
    FAIXA_QUENTE: "Quente (80–90)",
}

# Temperatura que indica oportunidade conquistada. Numa OP ATIVA esse
# valor é uma incoerência (ver docstring do módulo).
TEMPERATURA_CONQUISTADO = 100

# Valores de texto que contam como "sim" nas colunas VARCHAR de flag.
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


def faixa_temperatura(op: dict) -> str | None:
    """
    Classifica a oportunidade numa faixa de temperatura do funil:
      - FAIXA_SEM    : temperatura nula ou 0
      - FAIXA_FRIA   : 10 a 40
      - FAIXA_MORNA  : 50 a 70
      - FAIXA_QUENTE : 80 a 90

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
    if 80 <= t <= 90:
        return FAIXA_QUENTE
    # 100 (conquistado) ou valor inesperado: fora do funil.
    return None


def temperatura_incoerente(op: dict) -> bool:
    """
    True quando a oportunidade está numa fase ATIVA (analisada) mas tem
    temperatura 100 — valor reservado a oportunidades conquistadas.

    É uma rede de segurança: hoje a base não tem nenhum caso (as OPs
    com temperatura 100 estão todas em '06. Conquistado'), mas se um
    upload futuro trouxer uma OP ativa marcada com 100, a aba
    Conformidade sinaliza para revisão no CROmie.
    """
    fase = op.get("fase")
    if fase not in REGRAS_POR_FASE:
        # Conquistado ou fase desconhecida: 100 ali é esperado/ignorado.
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
        return _flag_inteira(op.get("tarefa_futura"))
    if regra == REGRA_TEMPERATURA:
        return _temperatura_preenchida(op)
    if regra == REGRA_PREVISAO:
        return _flag_texto(op.get("previsao_preenchido"))
    if regra == REGRA_TICKET:
        return _flag_texto(op.get("ticket_preenchido"))
    # Regra desconhecida: trata como não cumprida (defensivo).
    return False


def classificar_oportunidade(op: dict) -> dict[str, Any]:
    """
    Classifica UMA oportunidade pela régua interna do funil CROmie.

    Returns:
      dict com:
        - fase_analisada: bool — False se a fase está fora da análise.
        - conforme: bool — True se cumpre todas as regras da fase.
        - problemas / problemas_rotulos / regras_aplicaveis.
        - temperatura_incoerente: bool — temp 100 em fase ativa.
    """
    fase = op.get("fase")
    regras = REGRAS_POR_FASE.get(fase)
    incoerente = temperatura_incoerente(op)

    if regras is None:
        return {
            "fase_analisada": False,
            "conforme": False,
            "problemas": [],
            "problemas_rotulos": [],
            "regras_aplicaveis": [],
            "temperatura_incoerente": incoerente,
        }

    problemas = [r for r in regras if not _regra_cumprida(op, r)]

    return {
        "fase_analisada": True,
        "conforme": len(problemas) == 0,
        "problemas": problemas,
        "problemas_rotulos": [ROTULO_REGRA[r] for r in problemas],
        "regras_aplicaveis": list(regras),
        "temperatura_incoerente": incoerente,
    }


def resumir_funil(oportunidades: list[dict]) -> dict[str, Any]:
    """
    Classifica uma lista de oportunidades (régua de conformidade) e
    devolve cada uma anotada + um resumo agregado.

    Cada item ganha:
      - 'classificacao': resultado de classificar_oportunidade();
      - 'responsavel'  : o responsável pela fase (SDR ou executivo).

    Só oportunidades em fase analisada entram no cálculo do percentual.

    Returns:
      dict com 'itens', 'resumo' e 'por_fase'. O 'resumo' inclui
      'temperatura_incoerente' — contagem de OPs com temp 100 em fase
      ativa (rede de segurança; normalmente 0).
    """
    itens: list[dict] = []
    conformes = 0
    nao_conformes = 0
    fora = 0
    incoerentes = 0
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

        if cls["temperatura_incoerente"]:
            incoerentes += 1

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
            "temperatura_incoerente": incoerentes,
        },
        "por_fase": por_fase,
    }


def montar_funil(oportunidades: list[dict]) -> dict[str, Any]:
    """
    Agrega as oportunidades ATIVAS por fase x faixa de temperatura,
    para a aba "Funil".

    Considera apenas as oportunidades nas fases analisadas (as 5 fases
    ativas — Conquistado fica de fora). Oportunidades com temperatura
    100 (conquistado) NÃO entram nas faixas: são contadas à parte como
    'temperatura_incoerente'.

    Args:
      oportunidades: lista de dicts de cliente_oportunidade já
        filtrada para status ativo (o router faz esse filtro no SQL).

    Returns:
      dict com:
        - fases: lista na ordem do funil, cada item:
            { 'fase', 'total', 'faixas': {sem, fria, morna, quente} }
          'total' é a soma das 4 faixas (NÃO inclui as incoerentes).
        - total_geral: soma de 'total' de todas as fases.
        - temperatura_incoerente: nº de OPs ativas com temp 100
          (excluídas do funil; sinalizadas na aba Conformidade).
    """
    # Estrutura zerada, na ordem do funil.
    fases: dict[str, dict[str, int]] = {
        f: {faixa: 0 for faixa in FAIXAS_TEMPERATURA}
        for f in FASES_ANALISADAS
    }
    incoerentes = 0

    for op in oportunidades:
        fase = op.get("fase")
        if fase not in fases:
            # Fora das 5 fases ativas (ex.: Conquistado). Ignora.
            continue
        if temperatura_incoerente(op):
            # Temp 100 em fase ativa: não entra no funil.
            incoerentes += 1
            continue
        faixa = faixa_temperatura(op)
        if faixa is None:
            # Temperatura fora das faixas conhecidas (defensivo).
            continue
        fases[fase][faixa] += 1

    lista = []
    total_geral = 0
    for f in FASES_ANALISADAS:
        faixas = fases[f]
        total = sum(faixas.values())
        total_geral += total
        lista.append({"fase": f, "total": total, "faixas": faixas})

    return {
        "fases": lista,
        "total_geral": total_geral,
        "temperatura_incoerente": incoerentes,
    }
