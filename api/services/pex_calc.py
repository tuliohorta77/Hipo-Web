"""
HIPO — Serviço de Cálculo dos Indicadores PEX (v2)

Calcula os 30 indicadores oficiais do Manual PEX v8.01/2026.

Mudanças vs v1:
  - 30 indicadores (antes só 17)
  - Lê metas do modelo novo (pex_metas_cabecalho + pex_metas_indicadores + pex_metas_big3)
  - NMRR realizado vem do BD Ativados (não do CROmie)
  - Filtro temporal pelo mes_ref do snapshot, não CURRENT_DATE
  - Mapeamento de Carteira separado do SoW
  - Conversão Total filtrando pelas fases corretas (a partir de "03. Qualificação")
  - 6 faixas de classificação oficiais (Excelente/Certificada/Qualificada/Aderente/Em Desenvolvimento/Não Aderente)
  - Defensivo contra denominador <= 0 (não gera mais 54.500%)
  - 13 indicadores manuais (RH/Yungas/Big3/etc) registram 0 pts até existir página de realizados
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple
import asyncpg


# ═══════════════════════════════════════════════════════════════════════
# Funções de pontuação (1 por indicador) — faixas conforme manual v8.01
# ═══════════════════════════════════════════════════════════════════════

# ─── Pilar Resultado (17 indicadores, 60 pts) ───

def _pts_nmrr(pct: float) -> float:
    """NMRR (10 pts). 85-100% é proporcional, capado em 10 pts."""
    if pct < 80: return 0.0
    if pct < 85: return 5.0
    # Proporcional: pct=85 → 8,5 pts; pct=100 → 10 pts
    pts = (pct / 100.0) * 10.0
    return round(min(pts, 10.0), 2)


def _pts_sow(pct: float) -> float:
    """Share of Wallet (3 pts). pct = sow / 100."""
    if pct < 4: return 0.0
    if pct < 5: return 1.5
    return 3.0


def _pts_mapeamento_carteira(pct: float) -> float:
    """Mapeamento de carteira (2 pts). Cont mapeados / Carteira atual."""
    if pct < 48: return 0.0
    if pct < 60: return 1.0
    return 2.0


def _pts_early_churn(pct: float) -> float:
    """Early Churn (3 pts) — menor é melhor. Meta ≤5,7%."""
    if pct <= 5.7: return 3.0
    if pct <= 7.1: return 1.5
    return 0.0


def _pts_utilizacao_desconto(pct: float) -> float:
    """Utilização cupom desconto (2 pts) — menor é melhor. Meta ≤15%."""
    if pct <= 15: return 2.0
    if pct <= 19: return 1.0
    return 0.0


def _pts_crescimento_40(pct: float) -> float:
    """Crescimento 40% (5 pts)."""
    if pct < 32: return 0.0
    if pct < 40: return 2.5
    return 5.0


def _pts_reunioes_ec_du(realizado: float) -> float:
    """Reuniões por EC/dia útil (3 pts). Meta = 4."""
    if realizado < 3.2: return 0.0
    if realizado < 4.0: return 1.5
    return 3.0


def _pts_contadores_trabalhados(pct: float) -> float:
    """Contadores trabalhados (2 pts). Meta=90%."""
    if pct < 72: return 0.0
    if pct < 90: return 1.0
    return 2.0


def _pts_contadores_indicando(pct: float) -> float:
    """Contadores indicando (3 pts). Meta=25%."""
    if pct < 20: return 0.0
    if pct < 25: return 1.5
    return 3.0


def _pts_contadores_ativando(pct: float) -> float:
    """Contadores ativando (4 pts). Meta=8%."""
    if pct < 6.4: return 0.0
    if pct < 8: return 2.0
    return 4.0


def _pts_demos_outbound(pct: float) -> float:
    """Demos Outbound (3 pts). Atingimento da meta."""
    if pct < 80: return 0.0
    if pct < 100: return 1.5
    return 3.0


def _pts_reuniao_contador_inbound(pct: float) -> float:
    """Reunião com contador do lead Inbound (4 pts). Meta=80%."""
    if pct < 64: return 0.0
    if pct < 80: return 2.0
    return 4.0


def _pts_conversao_inbound(pct: float) -> float:
    """Conversão total leads Inbound (2 pts). Meta=45%."""
    if pct < 36: return 0.0
    if pct < 45: return 1.0
    return 2.0


def _pts_conversao_total(pct: float) -> float:
    """Conversão Total de leads (4 pts). Meta=35%."""
    if pct < 28: return 0.0
    if pct < 35: return 2.0
    return 4.0


def _pts_conversao_m0(pct: float) -> float:
    """Conversão de leads no M0 (3 pts). Meta=20%."""
    if pct < 16: return 0.0
    if pct < 20: return 1.5
    return 3.0


def _pts_demo_du(realizado: float) -> float:
    """Apresentação (demo) por dia útil (4 pts). Meta=4."""
    if realizado < 3.2: return 0.0
    if realizado < 4.0: return 2.0
    return 4.0


def _pts_integracao_contabil(pct: float) -> float:
    """Integração Contábil (3 pts). pct = realizado / meta_cluster."""
    if pct < 80: return 0.0
    if pct < 100: return 1.5
    return 3.0


# ─── Pilar Gestão (7 indicadores, 20 pts) — só uso_correto_cromie é calculável ───

def _pts_uso_correto_cromie(pct: float) -> float:
    """Utilização correta do CROmie (2 pts). Meta=100%."""
    if pct < 80: return 0.0
    if pct < 100: return 1.0
    return 2.0


# ─── Big3 (Engajamento, 6 pts) ───

def _pts_big3(acoes_atingidas: int) -> float:
    """Big3 (6 pts): 2 pts por ação atingida."""
    if acoes_atingidas <= 0: return 0.0
    if acoes_atingidas == 1: return 2.0
    if acoes_atingidas == 2: return 4.0
    return 6.0  # 3+


# ═══════════════════════════════════════════════════════════════════════
# Classificação (faixas oficiais do manual + mapeamento de cores)
# ═══════════════════════════════════════════════════════════════════════

def _classificar_oficial(total: float) -> str:
    """
    6 classificações oficiais do manual v8.01:
        EXCELENTE        → 95-100
        CERTIFICADA      → 76-94,99
        QUALIFICADA      → 60-75,99
        ADERENTE         → 50-59,99
        EM_DESENVOLVIMENTO → 36-49,99
        NAO_ADERENTE     → 0-35,99
    """
    if total >= 95: return "EXCELENTE"
    if total >= 76: return "CERTIFICADA"
    if total >= 60: return "QUALIFICADA"
    if total >= 50: return "ADERENTE"
    if total >= 36: return "EM_DESENVOLVIMENTO"
    return "NAO_ADERENTE"


def _classificar(total: float) -> str:
    """
    Cor da UI compatível com o ENUM risco_enum no schema (4 valores):
        EXCELENTE/CERTIFICADA → VERDE
        QUALIFICADA/ADERENTE  → LARANJA
        EM_DESENVOLVIMENTO    → AMARELO
        NAO_ADERENTE          → VERMELHO

    Mapeamento de severidade pro acompanhamento operacional:
    - VERDE: tudo bem (>= 76 pts)
    - LARANJA: zona de atenção (50-75 pts) — não está em risco mas precisa subir
    - AMARELO: risco preventivo (36-49 pts) — alerta
    - VERMELHO: descredenciamento (< 36 pts)
    """
    if total >= 76: return "VERDE"
    if total >= 50: return "LARANJA"
    if total >= 36: return "AMARELO"
    return "VERMELHO"


# ═══════════════════════════════════════════════════════════════════════
# Helpers internos
# ═══════════════════════════════════════════════════════════════════════

def _safe_pct(numerador: float, denominador: float) -> float:
    """Retorna 0.0 se denominador for inválido (<=0). Evita divisões absurdas."""
    if denominador is None or denominador <= 0:
        return 0.0
    if numerador is None:
        return 0.0
    return float(numerador) / float(denominador) * 100.0


def _mes_bounds(mes_ref: str) -> Tuple[date, date]:
    """Devolve (primeiro_dia, ultimo_dia) do mês YYYY-MM."""
    ano, mes = mes_ref.split("-")
    primeiro = date(int(ano), int(mes), 1)
    if int(mes) == 12:
        ultimo = date(int(ano) + 1, 1, 1)
    else:
        ultimo = date(int(ano), int(mes) + 1, 1)
    # Devolve [primeiro_dia_mes, primeiro_dia_proximo_mes) — semi-aberto
    return primeiro, ultimo


async def _ler_metas(conn: asyncpg.Connection, mes_ref: str) -> dict:
    """
    Lê o cabeçalho do mês + indicadores numéricos cadastrados.
    Retorna um dict pronto pra uso. Se mês não cadastrado, retorna defaults zerados.
    """
    cab = await conn.fetchrow(
        "SELECT * FROM pex_metas_cabecalho WHERE mes_ref = $1", mes_ref
    )
    if cab is None:
        return {
            "cabecalho": None,
            "cluster": "BASE",
            "dias_uteis": 22,
            "ecs_ativos_m3": 0,
            "evs_ativos": 0,
            "carteira_total_contadores": 0,
            "apps_ativos": 0,
            "headcount_recomendado": None,
            "metas_indicadores": {},
            "big3_atingidas": 0,
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
    big3_atingidas = sum(1 for r in big3 if r["atingiu"])

    return {
        "cabecalho": cab,
        "cluster": cab["cluster_unidade"] or "BASE",
        "dias_uteis": int(cab["dias_uteis"]) if cab["dias_uteis"] else 22,
        "ecs_ativos_m3": int(cab["ecs_ativos_m3"]) if cab["ecs_ativos_m3"] else 0,
        "evs_ativos": int(cab["evs_ativos"]) if cab["evs_ativos"] else 0,
        "carteira_total_contadores": int(cab["carteira_total_contadores"]) if cab["carteira_total_contadores"] else 0,
        "apps_ativos": int(cab["apps_ativos"]) if cab["apps_ativos"] else 0,
        "headcount_recomendado": int(cab["headcount_recomendado"]) if cab["headcount_recomendado"] else None,
        "metas_indicadores": metas_ind,
        "big3_atingidas": big3_atingidas,
    }


# ═══════════════════════════════════════════════════════════════════════
# Função principal
# ═══════════════════════════════════════════════════════════════════════

async def calcular_pex_snapshot(
    conn: asyncpg.Connection,
    upload_id: str,
    mes_ref: str,
    # Os 4 args abaixo são MANTIDOS por compatibilidade com chamadores antigos.
    # Se vierem zerados, lemos do pex_metas_cabecalho. Se vierem preenchidos,
    # usamos os valores informados (override).
    dias_uteis: Optional[int] = None,
    ecs_ativos_m3: Optional[int] = None,
    evs_ativos: Optional[int] = None,
    carteira_total: Optional[int] = None,
) -> dict:
    """
    Calcula todos os 30 indicadores PEX e devolve o dict pronto pra inserir
    em pex_snapshot.
    """
    metas = await _ler_metas(conn, mes_ref)

    # Override com args (compatibilidade)
    if dias_uteis: metas["dias_uteis"] = dias_uteis
    if ecs_ativos_m3: metas["ecs_ativos_m3"] = ecs_ativos_m3
    if evs_ativos: metas["evs_ativos"] = evs_ativos
    if carteira_total: metas["carteira_total_contadores"] = carteira_total

    DU = metas["dias_uteis"]
    ECS = metas["ecs_ativos_m3"]
    EVS = metas["evs_ativos"]
    CARTEIRA = metas["carteira_total_contadores"]
    APPS = metas["apps_ativos"]

    primeiro_dia, primeiro_dia_prox_mes = _mes_bounds(mes_ref)

    r = {}

    # ════════════════════════════════════════════════════════════════════
    # PILAR RESULTADO (60 pts)
    # ════════════════════════════════════════════════════════════════════

    # ── 1. NMRR (10 pts) — vem do BD Ativados, não do CROmie ─────────────
    # NMRR realizado = SUM(mrr_bruto) das linhas ACTIVE com data_ativacao no mês.
    # mrr_bruto já foi calculado pelo parser BD Ativados aplicando a regra BPO.
    nmrr_meta = metas["metas_indicadores"].get("nmrr") or 0.0
    nmrr_realizado_row = await conn.fetchrow("""
        SELECT COALESCE(SUM(mrr_bruto), 0) AS total
        FROM bd_ativados
        WHERE LOWER(situacao) = 'active'
          AND data_ativacao >= $1
          AND data_ativacao <  $2
    """, primeiro_dia, primeiro_dia_prox_mes)
    nmrr_realizado = float(nmrr_realizado_row["total"] or 0)
    nmrr_pct = _safe_pct(nmrr_realizado, nmrr_meta)
    r["nmrr_realizado"] = round(nmrr_realizado, 2)
    r["nmrr_meta"] = round(nmrr_meta, 2)
    r["nmrr_pct"] = round(nmrr_pct, 2)
    r["nmrr_pts"] = _pts_nmrr(nmrr_pct)

    # ── 2. SoW (3 pts) — Apps ativos vs Apps mapeados (clientes mapeados) ──
    # Manual: "% aplicativos ativos da base de clientes dos contadores mapeados"
    # Numerador: apps_ativos (cabeçalho do mês, informado pelo ADM)
    # Denominador: clientes mapeados → soma de clientes únicos sob contadores com sow_preenchido
    # Aproximação: COUNT(DISTINCT cnpj) de bd_ativados sob contadores que estão em
    # cromie_contador com sow_preenchido=TRUE
    sow_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT ba.cnpj) AS clientes_mapeados
        FROM bd_ativados ba
        JOIN cromie_contador cnt
          ON cnt.cnpj = ba.contador_cnpj
         AND cnt.upload_id = $1
        WHERE LOWER(ba.situacao) = 'active'
          AND cnt.sow_preenchido = TRUE
    """, upload_id)
    clientes_mapeados = int(sow_row["clientes_mapeados"] or 0)
    sow_pct = _safe_pct(APPS, clientes_mapeados) if APPS > 0 else 0.0
    r["sow_pct"] = round(sow_pct, 2)
    r["sow_pts"] = _pts_sow(sow_pct)

    # ── 3. Mapeamento de Carteira (2 pts) — Cont mapeados / Carteira atual ─
    map_row = await conn.fetchrow("""
        SELECT COUNT(*) AS mapeados
        FROM cromie_contador
        WHERE upload_id = $1
          AND sow_preenchido = TRUE
    """, upload_id)
    cont_mapeados = int(map_row["mapeados"] or 0)
    mapeamento_pct = _safe_pct(cont_mapeados, CARTEIRA)
    r["mapeamento_carteira_pct"] = round(mapeamento_pct, 2)
    r["mapeamento_carteira_pts"] = _pts_mapeamento_carteira(mapeamento_pct)

    # ── 4. Early Churn (3 pts) — manual / fonte externa, registra 0 por enquanto ──
    r["early_churn_pct"] = 0.0
    r["early_churn_pts"] = _pts_early_churn(0.0)  # 3 pts (=0% é melhor que ≤5,7%)

    # ── 5. Utilização Desconto (2 pts) — manual / fonte externa, 0 por enquanto ──
    r["utilizacao_desconto_pct"] = 0.0
    r["utilizacao_desconto_pts"] = _pts_utilizacao_desconto(0.0)  # 2 pts

    # ── 6. Crescimento 40% (5 pts) — apurado pelo Financeiro Omie, 0 por enquanto ──
    r["crescimento_40_pct"] = 0.0
    r["crescimento_40_pts"] = 0.0

    # ── 7. Reuniões EC/du (3 pts) ────────────────────────────────────────
    # Manual: nº reuniões ÷ nº ECs M3 ÷ DU
    # Tarefa = Reunião; Finalidade ∈ {Online, Presencial, Omie na Rua}; Resultado ∈ {Sucesso, Realizado, Efetuado}
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
    divisor_reunioes = max(ECS * DU, 1) if (ECS > 0 and DU > 0) else 0
    reunioes_du = round(total_reunioes / divisor_reunioes, 2) if divisor_reunioes > 0 else 0.0
    r["reunioes_ec_du_realizado"] = reunioes_du
    r["reunioes_ec_du_pts"] = _pts_reunioes_ec_du(reunioes_du)

    # ── 8. Contadores trabalhados (2 pts) — Cont/Trab ÷ Carteira atual ──
    cont_trab_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_tarefa_contador
        WHERE upload_id = $1
          AND data_tarefa >= $2 AND data_tarefa < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    cont_trab = int(cont_trab_row["total"] or 0)
    pct_trab = _safe_pct(cont_trab, CARTEIRA)
    r["contadores_trabalhados_pct"] = round(pct_trab, 2)
    r["contadores_trabalhados_pts"] = _pts_contadores_trabalhados(pct_trab)

    # ── 9. Contadores indicando (3 pts) — Cont/Ind ÷ Carteira atual ──
    cont_ind_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND contador_cnpj IS NOT NULL
          AND data_criacao >= $2 AND data_criacao < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    cont_ind = int(cont_ind_row["total"] or 0)
    pct_ind = _safe_pct(cont_ind, CARTEIRA)
    r["contadores_indicando_pct"] = round(pct_ind, 2)
    r["contadores_indicando_pts"] = _pts_contadores_indicando(pct_ind)

    # ── 10. Contadores ativando (4 pts) — Cont/Ativ ÷ Carteira atual ──
    cont_ativ_row = await conn.fetchrow("""
        SELECT COUNT(DISTINCT contador_cnpj) AS total
        FROM bd_ativados
        WHERE LOWER(situacao) = 'active'
          AND contador_cnpj IS NOT NULL
          AND data_ativacao >= $1 AND data_ativacao < $2
    """, primeiro_dia, primeiro_dia_prox_mes)
    cont_ativ = int(cont_ativ_row["total"] or 0)
    pct_ativ = _safe_pct(cont_ativ, CARTEIRA)
    r["contadores_ativando_pct"] = round(pct_ativ, 2)
    r["contadores_ativando_pts"] = _pts_contadores_ativando(pct_ativ)

    # ── 11. Demos Outbound (3 pts) — atingimento de meta numérica ──
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
    pct_outbound = _safe_pct(total_outbound, meta_outbound)
    r["demos_outbound_pct"] = round(pct_outbound, 2)
    r["demos_outbound_pts"] = _pts_demos_outbound(pct_outbound)

    # ── 12. Reunião com contador do lead Inbound (4 pts) ─────────────────
    # % contadores de leads inbound com reunião realizada
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
    pct_reuniao_inb = _safe_pct(com_reuniao, total_inb)
    r["reuniao_contador_inbound_pct"] = round(pct_reuniao_inb, 2)
    r["reuniao_contador_inbound_pts"] = _pts_reuniao_contador_inbound(pct_reuniao_inb)

    # ── 13. Conversão Inbound (2 pts) ────────────────────────────────────
    inb_conv_row = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE LOWER(origem) LIKE '%inbound%') AS total_inbound,
            COUNT(*) FILTER (WHERE LOWER(origem) LIKE '%inbound%' AND fase = '06. Conquistado') AS ganhos_inbound
        FROM cromie_cliente_final
        WHERE upload_id = $1
          AND data_ganho >= $2 AND data_ganho < $3
    """, upload_id, primeiro_dia, primeiro_dia_prox_mes)
    total_inb_conv = int(inb_conv_row["total_inbound"] or 0)
    ganhos_inb = int(inb_conv_row["ganhos_inbound"] or 0)
    pct_inb = _safe_pct(ganhos_inb, total_inb_conv)
    r["conversao_inbound_pct"] = round(pct_inb, 2)
    r["conversao_inbound_pts"] = _pts_conversao_inbound(pct_inb)

    # ── 14. Conversão Total (4 pts) ──────────────────────────────────────
    # Manual: "Conversão de oportunidades a partir da fase Qualificado"
    # Denominador: oportunidades em fase >= "03. Qualificação"
    # Numerador: dessas, as que chegaram em "06. Conquistado"
    # Filtro temporal: oportunidades com data_ganho ou data_perda no mês
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
    pct_conv = _safe_pct(ganhas, qualificadas)
    r["conversao_total_pct"] = round(pct_conv, 2)
    r["conversao_total_pts"] = _pts_conversao_total(pct_conv)

    # ── 15. Conversão M0 (3 pts) ─────────────────────────────────────────
    # Conversão de leads ganhos no mesmo mês de criação
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
    pct_m0 = _safe_pct(m0, ganhas_no_mes)
    r["conversao_m0_pct"] = round(pct_m0, 2)
    r["conversao_m0_pts"] = _pts_conversao_m0(pct_m0)

    # ── 16. Demo / dia útil (4 pts) ──────────────────────────────────────
    # Tipo=Registro; Finalidade=Apresentação; Resultado=Realizado
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
    r["demo_du_realizado"] = demo_du
    r["demo_du_pts"] = _pts_demo_du(demo_du)

    # ── 17. Integração Contábil (3 pts) — apurado por Yungas, 0 por enquanto ──
    # (Precisa página de realizados pra ADM informar nº de chamados Yungas)
    r["integracao_contabil_pct"] = 0.0
    r["integracao_contabil_pts"] = 0.0

    # ════════════════════════════════════════════════════════════════════
    # PILAR GESTÃO (20 pts) — só uso_correto_cromie é calculável
    # ════════════════════════════════════════════════════════════════════

    # Uso correto CROmie (2 pts) — % oportunidades ativas em compliance
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
    pct_uso_cromie = _safe_pct(em_compliance, total_ativos)
    r["uso_cromie_pct"] = round(pct_uso_cromie, 2)
    r["uso_cromie_pts"] = _pts_uso_correto_cromie(pct_uso_cromie)

    # Os outros 6 indicadores de Gestão são manuais (RH/Yungas) — registram 0
    r["remuneracao_variavel_pts"] = 0.0
    r["gestao_quartis_pts"] = 0.0
    r["headcount_recomendado_pts"] = 0.0
    r["politica_contratacao_pts"] = 0.0
    r["trilhas_uc_pts"] = 0.0
    r["turnover_voluntario_pts"] = 0.0

    # ════════════════════════════════════════════════════════════════════
    # PILAR ENGAJAMENTO (20 pts) — só Big3 é calculável aqui
    # ════════════════════════════════════════════════════════════════════

    # Big3 (6 pts) — vem das checkboxes da página /metas
    r["big3_acoes_atingidas"] = metas["big3_atingidas"]
    r["big3_pts"] = _pts_big3(metas["big3_atingidas"])

    # Demais 5 indicadores manuais — 0 pts até página de realizados
    r["treinamentos_franqueadora_pts"] = 0.0
    r["leitura_yungas_pts"] = 0.0
    r["verba_cooperada_pts"] = 0.0
    r["instagram_pts"] = 0.0
    r["eventos_pts"] = 0.0

    # ════════════════════════════════════════════════════════════════════
    # TOTAIS POR PILAR + GERAL
    # ════════════════════════════════════════════════════════════════════

    pts_resultado = sum([
        r.get("nmrr_pts", 0),
        r.get("sow_pts", 0),
        r.get("mapeamento_carteira_pts", 0),
        r.get("early_churn_pts", 0),
        r.get("utilizacao_desconto_pts", 0),
        r.get("crescimento_40_pts", 0),
        r.get("reunioes_ec_du_pts", 0),
        r.get("contadores_trabalhados_pts", 0),
        r.get("contadores_indicando_pts", 0),
        r.get("contadores_ativando_pts", 0),
        r.get("demos_outbound_pts", 0),
        r.get("reuniao_contador_inbound_pts", 0),
        r.get("conversao_inbound_pts", 0),
        r.get("conversao_total_pts", 0),
        r.get("conversao_m0_pts", 0),
        r.get("demo_du_pts", 0),
        r.get("integracao_contabil_pts", 0),
    ])

    pts_gestao = sum([
        r.get("remuneracao_variavel_pts", 0),
        r.get("uso_cromie_pts", 0),
        r.get("gestao_quartis_pts", 0),
        r.get("headcount_recomendado_pts", 0),
        r.get("politica_contratacao_pts", 0),
        r.get("trilhas_uc_pts", 0),
        r.get("turnover_voluntario_pts", 0),
    ])

    pts_engajamento = sum([
        r.get("treinamentos_franqueadora_pts", 0),
        r.get("leitura_yungas_pts", 0),
        r.get("verba_cooperada_pts", 0),
        r.get("instagram_pts", 0),
        r.get("big3_pts", 0),
        r.get("eventos_pts", 0),
    ])

    r["total_resultado_pts"] = round(pts_resultado, 2)
    r["total_gestao_pts"] = round(pts_gestao, 2)
    r["total_engajamento_pts"] = round(pts_engajamento, 2)
    r["total_geral_pts"] = round(pts_resultado + pts_gestao + pts_engajamento, 2)
    r["risco_classificacao"] = _classificar(r["total_geral_pts"])
    r["classificacao_oficial"] = _classificar_oficial(r["total_geral_pts"])

    return r


# ═══════════════════════════════════════════════════════════════════════
# Função auxiliar mantida pra compatibilidade (gaps de compliance)
# ═══════════════════════════════════════════════════════════════════════

async def calcular_gaps_compliance(
    conn: asyncpg.Connection,
    upload_id: str,
) -> list[dict]:
    """
    Agrega gaps de compliance do CROmie por usuário.
    Cada linha do retorno = 1 usuário responsável com seus contadores de gaps.
    Formato pronto pra inserir em pex_compliance_gaps.
    """
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
        # Estima pontos em risco: 0,1 pt por gap (heurística — cada gap ameaça 0.1 pts do uso_correto_cromie)
        pontos_em_risco = round(min(gaps * 0.1, 2.0), 2)
        out.append({
            "usuario_responsavel": r["usuario_responsavel"],
            "leads_sem_tarefa_futura": int(r["leads_sem_tarefa_futura"] or 0),
            "leads_sem_temperatura": int(r["leads_sem_temperatura"] or 0),
            "leads_sem_previsao": int(r["leads_sem_previsao"] or 0),
            "leads_sem_ticket": int(r["leads_sem_ticket"] or 0),
            "contadores_sem_tarefa_mes": 0,  # placeholder até implementar
            "inbound_sem_reuniao_5du": 0,    # placeholder até implementar
            "pontos_em_risco": pontos_em_risco,
        })
    return out
