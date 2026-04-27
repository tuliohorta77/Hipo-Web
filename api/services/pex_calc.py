"""
HIPO — Serviço de Cálculo dos Indicadores PEX (v3)

Mudanças vs v2:
  - Retorno estruturado: lista de dicts, 1 por indicador (em vez de campos planos)
  - Cada dict: {codigo, pilar, nome, pts_max, realizado, meta, unidade, pct, pts, detalhes}
  - `detalhes` é JSON com numerador/denominador/filtros pra auditoria
  - Sem mudança nas faixas/fórmulas (mantém o que validamos na fase 2)
  - Compatível com o novo modelo pex_snapshot + pex_snapshot_indicadores
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple, Any
import asyncpg


# ═══════════════════════════════════════════════════════════════════════
# Funções de pontuação (1 por indicador) — faixas conforme manual v8.01
# ═══════════════════════════════════════════════════════════════════════

# ─── Pilar Resultado (17 indicadores, 60 pts) ───

def _pts_nmrr(pct: float) -> float:
    if pct < 80: return 0.0
    if pct < 85: return 5.0
    return round(min((pct / 100.0) * 10.0, 10.0), 2)

def _pts_sow(pct: float) -> float:
    if pct < 4: return 0.0
    if pct < 5: return 1.5
    return 3.0

def _pts_mapeamento_carteira(pct: float) -> float:
    if pct < 48: return 0.0
    if pct < 60: return 1.0
    return 2.0

def _pts_early_churn(pct: float) -> float:
    if pct <= 5.7: return 3.0
    if pct <= 7.1: return 1.5
    return 0.0

def _pts_utilizacao_desconto(pct: float) -> float:
    if pct <= 15: return 2.0
    if pct <= 19: return 1.0
    return 0.0

def _pts_crescimento_40(pct: float) -> float:
    if pct < 32: return 0.0
    if pct < 40: return 2.5
    return 5.0

def _pts_reunioes_ec_du(realizado: float) -> float:
    if realizado < 3.2: return 0.0
    if realizado < 4.0: return 1.5
    return 3.0

def _pts_contadores_trabalhados(pct: float) -> float:
    if pct < 72: return 0.0
    if pct < 90: return 1.0
    return 2.0

def _pts_contadores_indicando(pct: float) -> float:
    if pct < 20: return 0.0
    if pct < 25: return 1.5
    return 3.0

def _pts_contadores_ativando(pct: float) -> float:
    if pct < 6.4: return 0.0
    if pct < 8: return 2.0
    return 4.0

def _pts_demos_outbound(pct: float) -> float:
    if pct < 80: return 0.0
    if pct < 100: return 1.5
    return 3.0

def _pts_reuniao_contador_inbound(pct: float) -> float:
    if pct < 64: return 0.0
    if pct < 80: return 2.0
    return 4.0

def _pts_conversao_inbound(pct: float) -> float:
    if pct < 36: return 0.0
    if pct < 45: return 1.0
    return 2.0

def _pts_conversao_total(pct: float) -> float:
    if pct < 28: return 0.0
    if pct < 35: return 2.0
    return 4.0

def _pts_conversao_m0(pct: float) -> float:
    if pct < 16: return 0.0
    if pct < 20: return 1.5
    return 3.0

def _pts_demo_du(realizado: float) -> float:
    if realizado < 3.2: return 0.0
    if realizado < 4.0: return 2.0
    return 4.0

def _pts_uso_correto_cromie(pct: float) -> float:
    if pct < 80: return 0.0
    if pct < 100: return 1.0
    return 2.0

def _pts_big3(acoes: int) -> float:
    if acoes <= 0: return 0.0
    if acoes == 1: return 2.0
    if acoes == 2: return 4.0
    return 6.0


# ═══════════════════════════════════════════════════════════════════════
# Classificação
# ═══════════════════════════════════════════════════════════════════════

def _classificar_oficial(total: float) -> str:
    if total >= 95: return "EXCELENTE"
    if total >= 76: return "CERTIFICADA"
    if total >= 60: return "QUALIFICADA"
    if total >= 50: return "ADERENTE"
    if total >= 36: return "EM_DESENVOLVIMENTO"
    return "NAO_ADERENTE"

def _classificar(total: float) -> str:
    if total >= 76: return "VERDE"
    if total >= 50: return "LARANJA"
    if total >= 36: return "AMARELO"
    return "VERMELHO"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _safe_pct(numerador: Any, denominador: Any) -> float:
    if denominador is None or denominador <= 0: return 0.0
    if numerador is None: return 0.0
    return float(numerador) / float(denominador) * 100.0

def _mes_bounds(mes_ref: str) -> Tuple[date, date]:
    ano, mes = mes_ref.split("-")
    primeiro = date(int(ano), int(mes), 1)
    if int(mes) == 12:
        ultimo = date(int(ano) + 1, 1, 1)
    else:
        ultimo = date(int(ano), int(mes) + 1, 1)
    return primeiro, ultimo


def _ind(codigo: str, pilar: str, nome: str, pts_max: float, realizado, meta, unidade: str,
         pts_func, detalhes: dict, manual_zero: bool = False) -> dict:
    """
    Helper que monta o dict padronizado de cada indicador.
    - manual_zero=True → indicador manual (RH/Yungas), realizado/meta/pct ficam zerados,
                         pts=pts_func(0) (que pode dar pts máx em casos como early_churn=0%)
    """
    if manual_zero:
        realizado = 0.0
        pct_val = 0.0
        pts_val = pts_func(0.0) if pts_func else 0.0
    else:
        realizado_n = float(realizado) if realizado is not None else 0.0
        if unidade in ("R$", "%", "qtd"):
            # Indicadores de atingimento: pct = realizado/meta * 100
            pct_val = _safe_pct(realizado_n, meta)
        elif unidade == "/du":
            # Indicadores valor absoluto (Reuniões EC/du, Demo/du)
            # pct = realizado/meta * 100 (fim de auditoria)
            pct_val = _safe_pct(realizado_n, meta) if meta else 0.0
        else:
            pct_val = 0.0
        # pts: depende da unidade
        if unidade == "/du":
            pts_val = pts_func(realizado_n)
        elif unidade == "%_inverso":
            pts_val = pts_func(realizado_n)  # Early Churn / Util Desconto recebem o pct realizado direto
        else:
            pts_val = pts_func(pct_val)

    return {
        "codigo": codigo,
        "pilar": pilar,
        "nome": nome,
        "pts_max": pts_max,
        "realizado": realizado if realizado is not None else 0.0,
        "meta": meta if meta is not None else 0.0,
        "unidade": unidade,
        "pct": round(pct_val, 2),
        "pts": round(pts_val, 2),
        "detalhes": detalhes,
    }


async def _ler_metas(conn: asyncpg.Connection, mes_ref: str) -> dict:
    cab = await conn.fetchrow(
        "SELECT * FROM pex_metas_cabecalho WHERE mes_ref = $1", mes_ref
    )
    if cab is None:
        return {
            "cabecalho": None, "cluster": "BASE", "dias_uteis": 22,
            "ecs_ativos_m3": 0, "evs_ativos": 0,
            "carteira_total_contadores": 0, "apps_ativos": 0,
            "headcount_recomendado": None,
            "metas_indicadores": {}, "big3_atingidas": 0,
        }
    inds = await conn.fetch(
        "SELECT codigo, meta_valor FROM pex_metas_indicadores WHERE cabecalho_id = $1",
        cab["id"],
    )
    metas_ind = {r["codigo"]: float(r["meta_valor"]) if r["meta_valor"] is not None else None
                 for r in inds}
    big3 = await conn.fetch(
        "SELECT atingiu FROM pex_metas_big3 WHERE cabecalho_id = $1",
        cab["id"],
    )
    return {
        "cabecalho": cab,
        "cluster": cab["cluster_unidade"] or "BASE",
        "dias_uteis": int(cab["dias_uteis"] or 22),
        "ecs_ativos_m3": int(cab["ecs_ativos_m3"] or 0),
        "evs_ativos": int(cab["evs_ativos"] or 0),
        "carteira_total_contadores": int(cab["carteira_total_contadores"] or 0),
        "apps_ativos": int(cab["apps_ativos"] or 0),
        "headcount_recomendado": int(cab["headcount_recomendado"]) if cab["headcount_recomendado"] else None,
        "metas_indicadores": metas_ind,
        "big3_atingidas": sum(1 for r in big3 if r["atingiu"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Função principal — retorna lista de indicadores estruturados
# ═══════════════════════════════════════════════════════════════════════

async def calcular_pex_indicadores(
    conn: asyncpg.Connection,
    upload_id: str,
    mes_ref: str,
) -> dict:
    """
    Calcula os 30 indicadores PEX e devolve estrutura pronta pra persistir
    em pex_snapshot + pex_snapshot_indicadores.

    Retorno:
        {
            "totais": {
                "resultado_pts", "gestao_pts", "engajamento_pts", "geral_pts",
                "risco_classificacao", "classificacao_oficial"
            },
            "indicadores": [ {dict}, {dict}, ... 30 dicts ]
        }
    """
    metas = await _ler_metas(conn, mes_ref)
    DU = metas["dias_uteis"]
    ECS = metas["ecs_ativos_m3"]
    EVS = metas["evs_ativos"]
    CARTEIRA = metas["carteira_total_contadores"]
    APPS = metas["apps_ativos"]
    CLUSTER = metas["cluster"]
    primeiro_dia, primeiro_dia_prox_mes = _mes_bounds(mes_ref)

    indicadores: list[dict] = []

    # ════════════════════════════════════════════════════════════════════
    # PILAR RESULTADO (60 pts, 17 indicadores)
    # ════════════════════════════════════════════════════════════════════

    # ── 1. NMRR (10 pts) ────────────────────────────────────────────────
    nmrr_meta = metas["metas_indicadores"].get("nmrr") or 0.0
    nmrr_row = await conn.fetchrow("""
        SELECT COALESCE(SUM(mrr_bruto), 0) AS total, COUNT(*) AS qtd_ativacoes
        FROM bd_ativados
        WHERE LOWER(situacao) = 'active'
          AND data_ativacao >= $1 AND data_ativacao < $2
    """, primeiro_dia, primeiro_dia_prox_mes)
    nmrr_realizado = float(nmrr_row["total"] or 0)
    indicadores.append(_ind(
        "nmrr", "RESULTADO", "NMRR", 10, nmrr_realizado, nmrr_meta, "R$",
        _pts_nmrr,
        {
            "fonte": "bd_ativados.mrr_bruto",
            "filtro": f"situacao=ACTIVE + data_ativacao em {mes_ref}",
            "qtd_ativacoes_no_mes": int(nmrr_row["qtd_ativacoes"] or 0),
        },
    ))

    # ── 2. SoW (3 pts) ──────────────────────────────────────────────────
    # Numerador: APPS ativos (cabecalho)
    # Denominador: clientes ativos da carteira mapeada
    sow_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT ba.cnpj) AS clientes_mapeados
        FROM bd_ativados ba
        JOIN cromie_contador cnt ON cnt.cnpj = ba.contador_cnpj
        WHERE cnt.upload_id = $1
          AND cnt.sow_preenchido = TRUE
          AND LOWER(ba.situacao) = 'active'
    """, upload_id)
    clientes_mapeados = int(sow_row["clientes_mapeados"] or 0)
    indicadores.append(_ind(
        "sow", "RESULTADO", "Share of Wallet (SoW)", 3,
        APPS, clientes_mapeados, "%",
        _pts_sow,
        {
            "numerador": APPS,
            "denominador": clientes_mapeados,
            "filtro": "apps_ativos / clientes_ativos_mapeados",
            "fonte": "bd_ativados ⨝ cromie_contador WHERE sow_preenchido",
        },
    ))

    # ── 3. Mapeamento de Carteira (2 pts) ──────────────────────────────
    map_row = await conn.fetchrow("""
        SELECT COUNT(*) AS mapeados
        FROM cromie_contador
        WHERE upload_id = $1 AND sow_preenchido = TRUE
    """, upload_id)
    cont_mapeados = int(map_row["mapeados"] or 0)
    indicadores.append(_ind(
        "mapeamento_carteira", "RESULTADO", "Mapeamento de carteira", 2,
        cont_mapeados, CARTEIRA, "%",
        _pts_mapeamento_carteira,
        {
            "numerador": cont_mapeados,
            "denominador": CARTEIRA,
            "filtro": "contadores com sow_preenchido / carteira_total",
            "fonte": "cromie_contador WHERE sow_preenchido=TRUE",
        },
    ))

    # ── 4. Early Churn (3 pts) — manual ─────────────────────────────────
    indicadores.append(_ind(
        "early_churn", "RESULTADO", "Early Churn", 3,
        0.0, 5.7, "%_inverso",
        _pts_early_churn,
        {"manual": True, "fonte": "Apuração mensal Omie", "obs": "0 pts até página de realizados"},
        manual_zero=True,
    ))

    # ── 5. Utilização Desconto (2 pts) — manual ─────────────────────────
    indicadores.append(_ind(
        "utilizacao_desconto", "RESULTADO", "Utilização cupom de desconto", 2,
        0.0, 15.0, "%_inverso",
        _pts_utilizacao_desconto,
        {"manual": True, "fonte": "Apuração Omie", "obs": "0 pts até página de realizados"},
        manual_zero=True,
    ))

    # ── 6. Crescimento 40% (5 pts) — manual ─────────────────────────────
    indicadores.append(_ind(
        "crescimento_40", "RESULTADO", "Crescimento de 40%", 5,
        0.0, 40.0, "%",
        _pts_crescimento_40,
        {"manual": True, "fonte": "Apuração Financeiro Omie", "obs": "0 pts até página de realizados"},
        manual_zero=True,
    ))

    # ── 7. Reuniões EC/du (3 pts) ───────────────────────────────────────
    reunioes_row = await conn.fetchrow("""
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND LOWER(tipo_tarefa) = 'reunião'
          AND LOWER(finalidade) IN ('online', 'presencial', 'omie na rua')
          AND LOWER(resultado) IN ('sucesso', 'realizado', 'efetuado')
          AND data_tarefa >= $2 AND data_tarefa < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_reunioes = int(reunioes_row["total"] or 0)
    divisor = max(ECS * DU, 1) if (ECS > 0 and DU > 0) else 0
    reunioes_du = round(total_reunioes / divisor, 2) if divisor > 0 else 0.0
    indicadores.append(_ind(
        "reunioes_ec_du", "RESULTADO", "Reuniões por EC/dia útil", 3,
        reunioes_du, 4.0, "/du",
        _pts_reunioes_ec_du,
        {
            "numerador": total_reunioes,
            "denominador": f"ECs={ECS} × DU={DU} = {ECS*DU}",
            "filtro": "tipo=Reunião + finalidade in (Online/Presencial/Omie na Rua) + resultado in (Sucesso/Realizado/Efetuado)",
            "fonte": "cromie_tarefa_contador",
        },
    ))

    # ── 8. Contadores trabalhados (2 pts) ──────────────────────────────
    cont_trab_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND data_tarefa >= $2 AND data_tarefa < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    cont_trab = int(cont_trab_row["total"] or 0)
    indicadores.append(_ind(
        "contadores_trabalhados", "RESULTADO", "Contadores trabalhados", 2,
        cont_trab, CARTEIRA, "%",
        _pts_contadores_trabalhados,
        {
            "numerador": cont_trab,
            "denominador": CARTEIRA,
            "filtro": "contadores DISTINCT que tiveram qualquer tarefa no mês / carteira_total",
            "fonte": "cromie_tarefa_contador WHERE data_tarefa em mes",
        },
    ))

    # ── 9. Contadores indicando (3 pts) ────────────────────────────────
    cont_ind_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND contador_cnpj IS NOT NULL
          AND data_criacao >= $2 AND data_criacao < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    cont_ind = int(cont_ind_row["total"] or 0)
    indicadores.append(_ind(
        "contadores_indicando", "RESULTADO", "Contadores indicando", 3,
        cont_ind, CARTEIRA, "%",
        _pts_contadores_indicando,
        {
            "numerador": cont_ind,
            "denominador": CARTEIRA,
            "filtro": "contadores com lead criado no mês / carteira_total",
            "fonte": "cromie_cliente_final WHERE data_criacao em mes",
        },
    ))

    # ── 10. Contadores ativando (4 pts) ────────────────────────────────
    cont_ativ_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM bd_ativados
        WHERE LOWER(situacao) = 'active'
          AND contador_cnpj IS NOT NULL
          AND data_ativacao >= $1 AND data_ativacao < $2
    """, primeiro_dia, primeiro_dia_prox_mes)
    cont_ativ = int(cont_ativ_row["total"] or 0)
    indicadores.append(_ind(
        "contadores_ativando", "RESULTADO", "Contadores ativando", 4,
        cont_ativ, CARTEIRA, "%",
        _pts_contadores_ativando,
        {
            "numerador": cont_ativ,
            "denominador": CARTEIRA,
            "filtro": "contadores DISTINCT com ≥1 ativação no mês / carteira_total",
            "fonte": "bd_ativados WHERE situacao=ACTIVE + data_ativacao em mes",
        },
    ))

    # ── 11. Demos Outbound (3 pts) ─────────────────────────────────────
    meta_outbound = metas["metas_indicadores"].get("demos_outbound") or 0
    outbound_row = await conn.fetchrow("""
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_cliente
        WHERE upload_id = $1
          AND LOWER(finalidade) LIKE '%apresenta%'
          AND LOWER(resultado) = 'realizado'
          AND data_tarefa >= $2 AND data_tarefa < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_outbound = int(outbound_row["total"] or 0)
    indicadores.append(_ind(
        "demos_outbound", "RESULTADO", "Número de demos Outbound", 3,
        total_outbound, meta_outbound, "qtd",
        _pts_demos_outbound,
        {
            "numerador": total_outbound,
            "denominador": meta_outbound,
            "filtro": "tarefa_cliente: finalidade ~ 'apresenta' + resultado = Realizado + data em mes",
            "fonte": "cromie_tarefa_cliente",
        },
    ))

    # ── 12. Reunião com contador do lead Inbound (4 pts) ────────────────
    inb_row = await conn.fetchrow("""
        SELECT
            COUNT(DISTINCT cf.contador_cnpj) FILTER (WHERE cf.origem ILIKE '%inbound%') AS total_inbound,
            COUNT(DISTINCT cf.contador_cnpj) FILTER (
                WHERE cf.origem ILIKE '%inbound%'
                  AND EXISTS (
                    SELECT 1 FROM cromie_tarefa_contador tc
                    WHERE tc.upload_id = cf.upload_id
                      AND tc.contador_cnpj = cf.contador_cnpj
                      AND LOWER(tc.tipo_tarefa) = 'reunião'
                      AND LOWER(tc.resultado) IN ('sucesso','realizado','efetuado')
                  )
            ) AS com_reuniao
        FROM cromie_cliente_final cf
        WHERE cf.upload_id = $1
          AND cf.contador_cnpj IS NOT NULL
          AND cf.data_criacao >= $2 AND cf.data_criacao < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_inb = int(inb_row["total_inbound"] or 0)
    com_reuniao = int(inb_row["com_reuniao"] or 0)
    indicadores.append(_ind(
        "reuniao_contador_inbound", "RESULTADO", "Reunião com contador do lead Inbound", 4,
        com_reuniao, total_inb, "%",
        _pts_reuniao_contador_inbound,
        {
            "numerador": com_reuniao,
            "denominador": total_inb,
            "filtro": "contadores de leads inbound do mês com reunião realizada",
            "fonte": "cromie_cliente_final ⨝ cromie_tarefa_contador",
        },
    ))

    # ── 13. Conversão Inbound (2 pts) ──────────────────────────────────
    inb_conv_row = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE LOWER(origem) LIKE '%inbound%') AS total,
            COUNT(*) FILTER (WHERE LOWER(origem) LIKE '%inbound%' AND fase = '06. Conquistado') AS ganhos
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND data_ganho >= $2 AND data_ganho < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_inb_conv = int(inb_conv_row["total"] or 0)
    ganhos_inb = int(inb_conv_row["ganhos"] or 0)
    indicadores.append(_ind(
        "conversao_inbound", "RESULTADO", "Conversão total leads Inbound", 2,
        ganhos_inb, total_inb_conv, "%",
        _pts_conversao_inbound,
        {
            "numerador": ganhos_inb,
            "denominador": total_inb_conv,
            "filtro": "leads inbound conquistados no mês / total leads inbound do mês",
            "fonte": "cromie_cliente_final WHERE origem~inbound AND data_ganho em mes",
        },
    ))

    # ── 14. Conversão Total (4 pts) ────────────────────────────────────
    conv_row = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (
                WHERE fase IN ('03. Qualificação','04. Apresentação','05. Negociação','06. Conquistado','07. Perdido')
            ) AS qualificadas,
            COUNT(*) FILTER (WHERE fase = '06. Conquistado') AS ganhas
        FROM cromie_cliente_final
        WHERE upload_id = $1
    """, upload_id)
    qualificadas = int(conv_row["qualificadas"] or 0)
    ganhas = int(conv_row["ganhas"] or 0)
    indicadores.append(_ind(
        "conversao_total", "RESULTADO", "Conversão total de leads", 4,
        ganhas, qualificadas, "%",
        _pts_conversao_total,
        {
            "numerador": ganhas,
            "denominador": qualificadas,
            "filtro": "fase=Conquistado / fase IN (Qualificação..Perdido)",
            "fonte": "cromie_cliente_final (snapshot atual, sem filtro temporal)",
        },
    ))

    # ── 15. Conversão M0 (3 pts) ───────────────────────────────────────
    m0_row = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE fase = '06. Conquistado') AS ganhas_no_mes,
            COUNT(*) FILTER (
                WHERE fase = '06. Conquistado'
                  AND data_criacao >= $2 AND data_criacao < $3
            ) AS m0
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND data_ganho >= $2 AND data_ganho < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    ganhas_no_mes = int(m0_row["ganhas_no_mes"] or 0)
    m0 = int(m0_row["m0"] or 0)
    indicadores.append(_ind(
        "conversao_m0", "RESULTADO", "Conversão de leads no M0", 3,
        m0, ganhas_no_mes, "%",
        _pts_conversao_m0,
        {
            "numerador": m0,
            "denominador": ganhas_no_mes,
            "filtro": "ganhos com data_criacao no mesmo mês / total ganhos no mês",
            "fonte": "cromie_cliente_final WHERE data_ganho em mes",
        },
    ))

    # ── 16. Demo / dia útil (4 pts) ────────────────────────────────────
    demo_row = await conn.fetchrow("""
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_cliente
        WHERE upload_id = $1
          AND LOWER(tipo_tarefa) = 'registro'
          AND LOWER(finalidade) LIKE '%apresenta%'
          AND LOWER(resultado) = 'realizado'
          AND data_tarefa >= $2 AND data_tarefa < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_demos = int(demo_row["total"] or 0)
    divisor_demo = max(EVS * DU, 1) if (EVS > 0 and DU > 0) else 0
    demo_du = round(total_demos / divisor_demo, 2) if divisor_demo > 0 else 0.0
    indicadores.append(_ind(
        "demo_du", "RESULTADO", "Apresentação (demo) por dia útil", 4,
        demo_du, 4.0, "/du",
        _pts_demo_du,
        {
            "numerador": total_demos,
            "denominador": f"EVs={EVS} × DU={DU} = {EVS*DU}",
            "filtro": "tipo=Registro + finalidade~apresenta + resultado=Realizado + data em mes",
            "fonte": "cromie_tarefa_cliente",
        },
    ))

    # ── 17. Integração Contábil (3 pts) — manual ────────────────────────
    meta_integ = metas["metas_indicadores"].get("integracao_contabil") or 0
    indicadores.append(_ind(
        "integracao_contabil", "RESULTADO", "Integração Contábil", 3,
        0.0, meta_integ, "qtd",
        _pts_demos_outbound,  # mesma faixa
        {"manual": True, "fonte": "Apuração via chamados Yungas", "cluster": CLUSTER,
         "obs": "0 pts até página de realizados"},
        manual_zero=True,
    ))

    # ════════════════════════════════════════════════════════════════════
    # PILAR GESTÃO (20 pts, 7 indicadores)
    # ════════════════════════════════════════════════════════════════════

    # ── Uso Correto CROmie (2 pts) ──────────────────────────────────────
    uso_row = await conn.fetchrow("""
        SELECT
            COUNT(*) AS total_ativos,
            COUNT(*) FILTER (
                WHERE tarefa_futura = TRUE
                  AND (temperatura_preenchida = TRUE OR fase NOT IN ('03. Qualificação','04. Apresentação','05. Negociação'))
                  AND (previsao_preenchida   = TRUE OR fase NOT IN ('03. Qualificação','04. Apresentação','05. Negociação'))
                  AND (ticket_preenchido     = TRUE OR fase != '05. Negociação')
            ) AS em_compliance
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND fase NOT IN ('06. Conquistado', '07. Perdido')
    """, upload_id)
    total_ativos = int(uso_row["total_ativos"] or 0)
    em_compliance = int(uso_row["em_compliance"] or 0)
    indicadores.append(_ind(
        "uso_correto_cromie", "GESTAO", "Utilização correta do CROmie", 2,
        em_compliance, total_ativos, "%",
        _pts_uso_correto_cromie,
        {
            "numerador": em_compliance,
            "denominador": total_ativos,
            "filtro": "oportunidades ativas em compliance / total oportunidades ativas",
            "fonte": "cromie_cliente_final WHERE fase != Conquistado/Perdido",
        },
    ))

    # ── 6 indicadores manuais de Gestão ─────────────────────────────────
    for codigo, nome, pts_max, fn in [
        ("remuneracao_variavel", "Aderência ao Modelo Remuneração Variável", 2, lambda x: 0.0),
        ("gestao_quartis", "Adesão à gestão dos quartis", 4, lambda x: 0.0),
        ("headcount_recomendado", "Adesão ao headcount recomendado", 5, lambda x: 0.0),
        ("politica_contratacao", "Adesão à política de contratação", 3, lambda x: 0.0),
        ("trilhas_uc", "Conclusão das trilhas obrigatórias UC", 2, lambda x: 0.0),
        ("turnover_voluntario", "Turnover Voluntário", 2, lambda x: 0.0),
    ]:
        indicadores.append(_ind(
            codigo, "GESTAO", nome, pts_max, 0.0, 100.0, "%",
            fn,
            {"manual": True, "fonte": "Apuração RH/UC", "obs": "0 pts até página de realizados"},
            manual_zero=True,
        ))

    # ════════════════════════════════════════════════════════════════════
    # PILAR ENGAJAMENTO (20 pts, 6 indicadores)
    # ════════════════════════════════════════════════════════════════════

    # ── Big3 (6 pts) ─────────────────────────────────────────────────────
    big3_atingidas = metas["big3_atingidas"]
    indicadores.append(_ind(
        "big3", "ENGAJAMENTO", "BIG 3 — Ações mensais", 6,
        big3_atingidas, 3, "qtd",
        _pts_big3,
        {
            "numerador": big3_atingidas,
            "denominador": 3,
            "fonte": "pex_metas_big3 WHERE atingiu=TRUE",
            "obs": "ADM marca atingimento na página /metas",
        },
    ))
    # Pra Big3 a fórmula é diferente (escala discreta), e _pts_big3 recebe contagem direta.
    # Mas _ind acima passa pelo path "qtd → pct = realizado/meta * 100" e depois pts_func(pct).
    # Pra esse caso específico, sobrescrevo o pts:
    indicadores[-1]["pts"] = round(_pts_big3(big3_atingidas), 2)
    indicadores[-1]["pct"] = round((big3_atingidas / 3.0) * 100, 2) if big3_atingidas else 0.0

    # ── Eventos (3 pts) — manual ────────────────────────────────────────
    meta_eventos = metas["metas_indicadores"].get("eventos") or 0
    indicadores.append(_ind(
        "eventos", "ENGAJAMENTO", "Realização de eventos", 3,
        0.0, meta_eventos, "qtd",
        _pts_demos_outbound,
        {"manual": True, "fonte": "Apuração Trade Marketing", "cluster": CLUSTER,
         "obs": "0 pts até página de realizados"},
        manual_zero=True,
    ))

    # ── 4 indicadores manuais de Engajamento ────────────────────────────
    for codigo, nome, pts_max in [
        ("treinamentos_franqueadora", "Participação em treinamentos da franqueadora", 4),
        ("leitura_yungas", "Leitura dos informes na Yungas", 3),
        ("verba_cooperada", "Utilização de verba cooperada", 2),
        ("instagram", "Mídias sociais — Instagram", 2),
    ]:
        indicadores.append(_ind(
            codigo, "ENGAJAMENTO", nome, pts_max, 0.0, 100.0, "%",
            lambda x: 0.0,
            {"manual": True, "fonte": "Apuração franqueadora", "obs": "0 pts até página de realizados"},
            manual_zero=True,
        ))

    # ════════════════════════════════════════════════════════════════════
    # TOTAIS
    # ════════════════════════════════════════════════════════════════════

    pts_resultado = sum(i["pts"] for i in indicadores if i["pilar"] == "RESULTADO")
    pts_gestao = sum(i["pts"] for i in indicadores if i["pilar"] == "GESTAO")
    pts_engajamento = sum(i["pts"] for i in indicadores if i["pilar"] == "ENGAJAMENTO")
    total_geral = pts_resultado + pts_gestao + pts_engajamento

    return {
        "totais": {
            "resultado_pts": round(pts_resultado, 2),
            "gestao_pts": round(pts_gestao, 2),
            "engajamento_pts": round(pts_engajamento, 2),
            "geral_pts": round(total_geral, 2),
            "risco_classificacao": _classificar(total_geral),
            "classificacao_oficial": _classificar_oficial(total_geral),
        },
        "indicadores": indicadores,
    }


# ═══════════════════════════════════════════════════════════════════════
# Compatibilidade: função antiga calcular_pex_snapshot (chamada pelo router)
# ═══════════════════════════════════════════════════════════════════════

async def calcular_pex_snapshot(
    conn: asyncpg.Connection,
    upload_id: str,
    mes_ref: str,
    dias_uteis: Optional[int] = None,
    ecs_ativos_m3: Optional[int] = None,
    evs_ativos: Optional[int] = None,
    carteira_total: Optional[int] = None,
) -> dict:
    """
    Wrapper de compatibilidade: invoca calcular_pex_indicadores e devolve
    no formato antigo (campos planos pct/pts) pra não quebrar caller existente.
    Mas devolve TAMBÉM o objeto novo dentro da chave `_v3` pra quem migrou.
    """
    resultado = await calcular_pex_indicadores(conn, upload_id, mes_ref)
    flat = {}
    for ind in resultado["indicadores"]:
        c = ind["codigo"]
        flat[f"{c}_pct"] = ind["pct"]
        flat[f"{c}_pts"] = ind["pts"]
        # alguns campos especiais que o schema legacy esperava:
        if c == "nmrr":
            flat["nmrr_realizado"] = ind["realizado"]
            flat["nmrr_meta"] = ind["meta"]
        if c == "reunioes_ec_du":
            flat["reunioes_ec_du_realizado"] = ind["realizado"]
        if c == "demo_du":
            flat["demo_du_realizado"] = ind["realizado"]

    flat.update({
        "total_resultado_pts": resultado["totais"]["resultado_pts"],
        "total_gestao_pts": resultado["totais"]["gestao_pts"],
        "total_engajamento_pts": resultado["totais"]["engajamento_pts"],
        "total_geral_pts": resultado["totais"]["geral_pts"],
        "risco_classificacao": resultado["totais"]["risco_classificacao"],
        "classificacao_oficial": resultado["totais"]["classificacao_oficial"],
        "_v3": resultado,
    })
    return flat


async def calcular_gaps_compliance(
    conn: asyncpg.Connection,
    upload_id: str,
) -> list[dict]:
    """Mantida igual da fase 2 — agrega gaps de compliance por usuário."""
    rows = await conn.fetch("""
        SELECT
            COALESCE(usuario_responsavel, 'Sem responsável') AS usuario_responsavel,
            COUNT(*) FILTER (
                WHERE tarefa_futura = FALSE
                  AND fase NOT IN ('06. Conquistado', '07. Perdido')
            ) AS leads_sem_tarefa_futura,
            COUNT(*) FILTER (
                WHERE temperatura_preenchida = FALSE
                  AND fase IN ('03. Qualificação','04. Apresentação','05. Negociação')
            ) AS leads_sem_temperatura,
            COUNT(*) FILTER (
                WHERE previsao_preenchida = FALSE
                  AND fase IN ('03. Qualificação','04. Apresentação','05. Negociação')
            ) AS leads_sem_previsao,
            COUNT(*) FILTER (
                WHERE ticket_preenchido = FALSE
                  AND fase = '05. Negociação'
            ) AS leads_sem_ticket
        FROM cromie_cliente_final
        WHERE upload_id = $1
        GROUP BY usuario_responsavel
        HAVING COUNT(*) FILTER (
                WHERE (tarefa_futura = FALSE AND fase NOT IN ('06. Conquistado','07. Perdido'))
                   OR (temperatura_preenchida = FALSE AND fase IN ('03. Qualificação','04. Apresentação','05. Negociação'))
                   OR (previsao_preenchida = FALSE AND fase IN ('03. Qualificação','04. Apresentação','05. Negociação'))
                   OR (ticket_preenchido = FALSE AND fase = '05. Negociação')
              ) > 0
        ORDER BY 1
    """, upload_id)

    out = []
    for r in rows:
        gaps = sum([
            int(r["leads_sem_tarefa_futura"] or 0),
            int(r["leads_sem_temperatura"] or 0),
            int(r["leads_sem_previsao"] or 0),
            int(r["leads_sem_ticket"] or 0),
        ])
        pontos_em_risco = round(min(gaps * 0.1, 2.0), 2)
        out.append({
            "usuario_responsavel": r["usuario_responsavel"],
            "leads_sem_tarefa_futura": int(r["leads_sem_tarefa_futura"] or 0),
            "leads_sem_temperatura": int(r["leads_sem_temperatura"] or 0),
            "leads_sem_previsao": int(r["leads_sem_previsao"] or 0),
            "leads_sem_ticket": int(r["leads_sem_ticket"] or 0),
            "contadores_sem_tarefa_mes": 0,
            "inbound_sem_reuniao_5du": 0,
            "pontos_em_risco": pontos_em_risco,
        })
    return out
