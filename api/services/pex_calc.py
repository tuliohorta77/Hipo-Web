"""
HIPO — Serviço de Cálculo dos Indicadores PEX
Calcula os indicadores que dependem do CROmie a partir do último upload.
"""
from datetime import date
from typing import Optional
import asyncpg


def _pts_reunioes_ec_du(realizado: float, meta: float = 4.0) -> float:
    if realizado < 3.2: return 0
    if realizado < 4.0: return 1.5
    return 3.0

def _pts_contadores_trabalhados(pct: float) -> float:
    if pct < 0.72: return 0
    if pct < 0.90: return 1.0
    return 2.0

def _pts_contadores_indicando(pct: float) -> float:
    if pct < 0.20: return 0
    if pct < 0.25: return 1.5
    return 3.0

def _pts_contadores_ativando(pct: float) -> float:
    if pct < 0.064: return 0
    if pct < 0.08:  return 2.0
    return 4.0

def _pts_conversao_total(pct: float) -> float:
    if pct < 0.28: return 0
    if pct < 0.35: return 2.0
    return 4.0

def _pts_conversao_m0(pct: float) -> float:
    if pct < 0.16: return 0
    if pct < 0.20: return 1.5
    return 3.0

def _pts_conversao_inbound(pct: float) -> float:
    if pct < 0.36: return 0
    if pct < 0.45: return 1.0
    return 2.0

def _pts_demo_du(realizado: float) -> float:
    if realizado < 3.2: return 0
    if realizado < 4.0: return 2.0
    return 4.0

def _pts_demos_outbound(pct: float) -> float:
    if pct < 0.80: return 0
    if pct < 1.00: return 1.5
    return 3.0

def _pts_sow(pct: float) -> float:
    if pct < 0.04: return 0
    if pct < 0.05: return 1.5
    return 3.0

def _pts_mapeamento(pct: float) -> float:
    if pct < 0.48: return 0
    if pct < 0.60: return 1.0
    return 2.0

def _pts_reuniao_inbound(pct: float) -> float:
    if pct < 0.64: return 0
    if pct < 0.80: return 2.0
    return 4.0

def _pts_integracao(pct: float) -> float:
    if pct < 0.80: return 0
    if pct < 1.00: return 1.5
    return 3.0

def _pts_early_churn(pct: float) -> float:
    if pct <= 0.057: return 3.0
    if pct <= 0.071: return 1.5
    return 0.0

def _pts_crescimento(pct: float) -> float:
    if pct < 0.32: return 0
    if pct < 0.40: return 2.5
    return 5.0

def _pts_utilizacao_desconto(pct: float) -> float:
    if pct <= 0.15: return 2.0
    if pct <= 0.19: return 1.0
    return 0.0

def _pts_uso_cromie(pct: float) -> float:
    if pct < 0.80: return 0
    if pct < 1.00: return 1.0
    return 2.0

def _classificar_risco(total: float) -> str:
    if total >= 75: return "VERDE"
    if total >= 55: return "LARANJA"
    if total >= 36: return "AMARELO"
    return "VERMELHO"


async def calcular_pex_snapshot(
    conn: asyncpg.Connection,
    upload_id: str,
    mes_ref: str,
    dias_uteis: int,
    ecs_ativos_m3: int,
    evs_ativos: int,
    carteira_total: int,
) -> dict:
    """
    Calcula todos os indicadores do Pilar Resultado que dependem do CROmie.
    Retorna o dicionário pronto para inserir em pex_snapshot.
    """
    r = {}

    # ── NMRR ─────────────────────────────────────────────────────────────────
    nmrr_meta_row = await conn.fetchrow(
        "SELECT nmrr_meta FROM pex_metas_mensais WHERE mes_ref = $1", mes_ref
    )
    nmrr_meta = float(nmrr_meta_row["nmrr_meta"]) if nmrr_meta_row else 0

    nmrr_realizado_row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(ticket), 0) AS total
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND LOWER(fase) LIKE '%conquistado%'
          AND data_ganho >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    nmrr_realizado = float(nmrr_realizado_row["total"]) if nmrr_realizado_row else 0
    nmrr_pct = (nmrr_realizado / nmrr_meta * 100) if nmrr_meta > 0 else 0

    def pts_nmrr(pct):
        if pct < 80: return 0
        if pct < 85: return 5
        return round((pct / 100) * 10, 2)

    r["nmrr_realizado"] = nmrr_realizado
    r["nmrr_meta"] = nmrr_meta
    r["nmrr_pct"] = round(nmrr_pct, 2)
    r["nmrr_pts"] = pts_nmrr(nmrr_pct)

    # ── REUNIÕES EC/DU ────────────────────────────────────────────────────────
    reunioes_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND LOWER(tipo_tarefa) = 'reunião'
          AND LOWER(finalidade) IN ('online', 'presencial', 'omie na rua')
          AND LOWER(resultado) IN ('sucesso', 'realizado', 'efetuado')
          AND data_tarefa >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    total_reunioes = int(reunioes_row["total"]) if reunioes_row else 0
    divisor = max(ecs_ativos_m3 * dias_uteis, 1)
    reunioes_du = round(total_reunioes / divisor, 2)
    r["reunioes_ec_du_realizado"] = reunioes_du
    r["reunioes_ec_du_pts"] = _pts_reunioes_ec_du(reunioes_du)

    # ── CONTADORES TRABALHADOS ────────────────────────────────────────────────
    cont_trab_row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND data_tarefa >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    cont_trabalhados = int(cont_trab_row["total"]) if cont_trab_row else 0
    pct_trab = cont_trabalhados / max(carteira_total, 1)
    r["contadores_trabalhados_pct"] = round(pct_trab * 100, 2)
    r["contadores_trabalhados_pts"] = _pts_contadores_trabalhados(pct_trab)

    # ── CONTADORES INDICANDO ──────────────────────────────────────────────────
    cont_ind_row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND contador_cnpj IS NOT NULL
          AND data_criacao >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    cont_indicando = int(cont_ind_row["total"]) if cont_ind_row else 0
    pct_ind = cont_indicando / max(carteira_total, 1)
    r["contadores_indicando_pct"] = round(pct_ind * 100, 2)
    r["contadores_indicando_pts"] = _pts_contadores_indicando(pct_ind)

    # ── CONVERSÃO TOTAL DE LEADS ──────────────────────────────────────────────
    conv_row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE LOWER(fase) LIKE '%conquistado%') AS ganhos,
            COUNT(*) FILTER (WHERE LOWER(fase) NOT LIKE '%suspect%') AS qualificados
        FROM cromie_cliente_final
        WHERE upload_id = $1
        """, upload_id
    )
    ganhos = int(conv_row["ganhos"] or 0)
    qualificados = int(conv_row["qualificados"] or 1)
    pct_conv = ganhos / max(qualificados, 1)
    r["conversao_total_pct"] = round(pct_conv * 100, 2)
    r["conversao_total_pts"] = _pts_conversao_total(pct_conv)

    # ── CONVERSÃO M0 ──────────────────────────────────────────────────────────
    m0_row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE LOWER(fase) LIKE '%conquistado%'
                  AND DATE_TRUNC('month', data_criacao) = DATE_TRUNC('month', data_ganho)
            ) AS m0,
            COUNT(*) FILTER (WHERE LOWER(fase) LIKE '%conquistado%') AS total_ganhos
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND data_ganho >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    m0 = int(m0_row["m0"] or 0)
    total_ganhos = int(m0_row["total_ganhos"] or 1)
    pct_m0 = m0 / max(total_ganhos, 1)
    r["conversao_m0_pct"] = round(pct_m0 * 100, 2)
    r["conversao_m0_pts"] = _pts_conversao_m0(pct_m0)

    # ── CONVERSÃO INBOUND ─────────────────────────────────────────────────────
    inb_row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE LOWER(fase) LIKE '%conquistado%'
                  AND LOWER(origem) LIKE '%inbound%'
            ) AS ganhos_inbound,
            COUNT(*) FILTER (WHERE LOWER(origem) LIKE '%inbound%') AS total_inbound
        FROM cromie_cliente_final
        WHERE upload_id = $1
        """, upload_id
    )
    ganhos_inb = int(inb_row["ganhos_inbound"] or 0)
    total_inb = int(inb_row["total_inbound"] or 1)
    pct_inb = ganhos_inb / max(total_inb, 1)
    r["conversao_inbound_pct"] = round(pct_inb * 100, 2)
    r["conversao_inbound_pts"] = _pts_conversao_inbound(pct_inb)

    # ── DEMO / DIA ÚTIL ───────────────────────────────────────────────────────
    demo_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_cliente
        WHERE upload_id = $1
          AND LOWER(tipo_tarefa) = 'registro'
          AND LOWER(finalidade) LIKE '%apresentação%'
          AND LOWER(resultado) = 'realizado'
          AND data_tarefa >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    total_demos = int(demo_row["total"] or 0)
    demo_du = round(total_demos / max(evs_ativos * dias_uteis, 1), 2)
    r["demo_du_realizado"] = demo_du
    r["demo_du_pts"] = _pts_demo_du(demo_du)

    # ── DEMOS OUTBOUND ────────────────────────────────────────────────────────
    meta_outbound_row = await conn.fetchrow(
        "SELECT demos_outbound_meta FROM pex_metas_mensais WHERE mes_ref = $1", mes_ref
    )
    meta_outbound = int(meta_outbound_row["demos_outbound_meta"]) if meta_outbound_row else 0
    outbound_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_cliente
        WHERE upload_id = $1
          AND LOWER(finalidade) LIKE '%apresentação%'
          AND LOWER(resultado) = 'realizado'
          AND data_tarefa >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    total_outbound = int(outbound_row["total"] or 0)
    pct_outbound = total_outbound / max(meta_outbound, 1)
    r["demos_outbound_pct"] = round(pct_outbound * 100, 2)
    r["demos_outbound_pts"] = _pts_demos_outbound(pct_outbound)

    # ── SOW ───────────────────────────────────────────────────────────────────
    # SOW = apps ativos / clientes mapeados (BD Ativados vs Contador)
    # Simplificado: contadores com SOW preenchido vs carteira
    sow_row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE sow_preenchido = TRUE) AS com_sow,
            COUNT(*) AS total
        FROM cromie_contador
        WHERE upload_id = $1
        """, upload_id
    )
    com_sow = int(sow_row["com_sow"] or 0)
    total_cont = int(sow_row["total"] or 1)
    pct_sow = com_sow / max(total_cont, 1)
    r["sow_pct"] = round(pct_sow * 100, 2)
    r["sow_pts"] = _pts_sow(pct_sow)

    # ── MAPEAMENTO DE CARTEIRA ────────────────────────────────────────────────
    r["mapeamento_carteira_pct"] = r["sow_pct"]
    r["mapeamento_carteira_pts"] = _pts_mapeamento(pct_sow)

    # ── REUNIÃO COM CONTADOR INBOUND ──────────────────────────────────────────
    # Leads inbound vs reunião realizada com o contador em até 5DU
    inb_cnt_row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT cf.contador_cnpj) AS com_reuniao,
               COUNT(DISTINCT cf2.contador_cnpj) AS total_inbound
        FROM cromie_cliente_final cf
        JOIN cromie_cliente_final cf2
            ON cf2.upload_id = cf.upload_id
           AND cf2.origem ILIKE '%inbound%'
        JOIN cromie_tarefa_contador tc
            ON tc.upload_id = cf.upload_id
           AND tc.contador_cnpj = cf.contador_cnpj
           AND LOWER(tc.tipo_tarefa) = 'reunião'
           AND LOWER(tc.resultado) IN ('sucesso', 'realizado', 'efetuado')
        WHERE cf.upload_id = $1
          AND cf.origem ILIKE '%inbound%'
        """, upload_id
    )
    com_reuniao = int(inb_cnt_row["com_reuniao"] or 0)
    total_inbound_cnt = int(inb_cnt_row["total_inbound"] or 1)
    pct_reuniao_inb = com_reuniao / max(total_inbound_cnt, 1)
    r["reuniao_contador_inbound_pct"] = round(pct_reuniao_inb * 100, 2)
    r["reuniao_contador_inbound_pts"] = _pts_reuniao_inbound(pct_reuniao_inb)

    # ── INTEGRAÇÃO CONTÁBIL ───────────────────────────────────────────────────
    integ_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND LOWER(finalidade) LIKE '%integração contábil%'
          AND data_tarefa >= DATE_TRUNC('month', CURRENT_DATE)
        """, upload_id
    )
    total_integ = int(integ_row["total"] or 0)
    meta_integ = 8  # Cluster Platina
    pct_integ = total_integ / max(meta_integ, 1)
    r["integracao_contabil_pct"] = round(pct_integ * 100, 2)
    r["integracao_contabil_pts"] = _pts_integracao(pct_integ)

    # ── USO CROMIE (compliance) ───────────────────────────────────────────────
    uso_row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total_ativos,
            COUNT(*) FILTER (
                WHERE tarefa_futura = TRUE
                  AND (temperatura_preenchida = TRUE OR LOWER(fase) NOT IN ('qualificação','negociação','apresentação'))
                  AND (previsao_preenchida = TRUE OR LOWER(fase) NOT IN ('qualificação','negociação','apresentação'))
                  AND (ticket_preenchido = TRUE OR LOWER(fase) != 'negociação')
            ) AS em_compliance
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND LOWER(fase) NOT IN ('conquistado', 'perdido')
        """, upload_id
    )
    total_ativos = int(uso_row["total_ativos"] or 1)
    em_compliance = int(uso_row["em_compliance"] or 0)
    pct_uso = em_compliance / max(total_ativos, 1)
    r["uso_cromie_pts"] = _pts_uso_cromie(pct_uso)

    # ── TOTAIS ────────────────────────────────────────────────────────────────
    pts_resultado = sum([
        r.get("nmrr_pts", 0),
        r.get("reunioes_ec_du_pts", 0),
        r.get("contadores_trabalhados_pts", 0),
        r.get("contadores_indicando_pts", 0),
        r.get("contadores_ativando_pts", 0),
        r.get("conversao_total_pts", 0),
        r.get("conversao_m0_pts", 0),
        r.get("conversao_inbound_pts", 0),
        r.get("demo_du_pts", 0),
        r.get("demos_outbound_pts", 0),
        r.get("sow_pts", 0),
        r.get("mapeamento_carteira_pts", 0),
        r.get("reuniao_contador_inbound_pts", 0),
        r.get("integracao_contabil_pts", 0),
        r.get("early_churn_pts", 0),
        r.get("crescimento_40_pts", 0),
        r.get("utilizacao_desconto_pts", 0),
    ])

    r["total_resultado_pts"] = round(pts_resultado, 2)
    r["total_gestao_pts"] = r.get("uso_cromie_pts", 0)  # Será expandido nas próximas fases
    r["total_engajamento_pts"] = 0  # Será expandido nas próximas fases
    r["total_geral_pts"] = round(
        r["total_resultado_pts"] + r["total_gestao_pts"] + r["total_engajamento_pts"], 2
    )
    r["risco_classificacao"] = _classificar_risco(r["total_geral_pts"])

    return r


async def calcular_gaps_compliance(
    conn: asyncpg.Connection,
    upload_id: str,
) -> list[dict]:
    """
    Calcula os gaps de compliance por usuário responsável.
    Retorna uma lista de dicts prontos para inserir em pex_compliance_gaps.
    """
    rows = await conn.fetch(
        """
        SELECT
            usuario_responsavel,
            COUNT(*) FILTER (
                WHERE tarefa_futura = FALSE
                  AND LOWER(fase) IN ('suspect','cadência','qualificação')
            ) AS leads_sem_tarefa_futura,
            COUNT(*) FILTER (
                WHERE temperatura_preenchida = FALSE
                  AND LOWER(fase) NOT IN ('suspect','cadência')
            ) AS leads_sem_temperatura,
            COUNT(*) FILTER (
                WHERE previsao_preenchida = FALSE
                  AND LOWER(fase) NOT IN ('suspect','cadência')
            ) AS leads_sem_previsao,
            COUNT(*) FILTER (
                WHERE ticket_preenchido = FALSE
                  AND LOWER(fase) = 'negociação'
            ) AS leads_sem_ticket
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND LOWER(fase) NOT IN ('conquistado','perdido')
          AND usuario_responsavel IS NOT NULL
        GROUP BY usuario_responsavel
        """, upload_id
    )

    # Contadores sem tarefa no mês por usuário
    cont_rows = await conn.fetch(
        """
        SELECT
            cc.usuario_responsavel,
            COUNT(*) AS contadores_sem_tarefa
        FROM cromie_contador cc
        WHERE cc.upload_id = $1
          AND cc.possui_tarefa = FALSE
          AND cc.usuario_responsavel IS NOT NULL
        GROUP BY cc.usuario_responsavel
        """, upload_id
    )
    cont_map = {r["usuario_responsavel"]: int(r["contadores_sem_tarefa"]) for r in cont_rows}

    gaps = []
    for row in rows:
        usuario = row["usuario_responsavel"]
        sem_tarefa   = int(row["leads_sem_tarefa_futura"] or 0)
        sem_temp     = int(row["leads_sem_temperatura"] or 0)
        sem_prev     = int(row["leads_sem_previsao"] or 0)
        sem_ticket   = int(row["leads_sem_ticket"] or 0)
        cont_sem     = cont_map.get(usuario, 0)

        # Estimativa de pontos em risco (heurística)
        pontos_em_risco = round(
            (sem_tarefa * 0.05) +
            (sem_temp * 0.03) +
            (sem_prev * 0.03) +
            (sem_ticket * 0.04) +
            (cont_sem * 0.04),
            2
        )

        gaps.append({
            "usuario_responsavel":      usuario,
            "leads_sem_tarefa_futura":  sem_tarefa,
            "leads_sem_temperatura":    sem_temp,
            "leads_sem_previsao":       sem_prev,
            "leads_sem_ticket":         sem_ticket,
            "contadores_sem_tarefa_mes": cont_sem,
            "inbound_sem_reuniao_5du":  0,  # calculado separadamente
            "pontos_em_risco":          pontos_em_risco,
        })

    return gaps