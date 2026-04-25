-- ============================================================
-- HIPO — Migration 003: Expande precisão de pex_snapshot
-- ============================================================
-- Razão: NUMERIC(5,2) só aceita valores < 1000 (overflow em
-- bases reais grandes — ex: % de contadores indicando pode passar
-- de 1000% se a carteira mapeada é pequena vs a base ativada).
--
-- Aplica:
--   DROP da view vw_pex_mes_atual (depende das colunas alteradas)
--   ALTER 21 colunas para NUMERIC(8,2) — aceita até 999.999,99
--   Recria a view igual
--
-- Rodar na EC2:
--   psql $DATABASE_URL -f migrations/003_pex_snapshot_precisao.sql
-- ============================================================

BEGIN;

DROP VIEW IF EXISTS vw_pex_mes_atual;

ALTER TABLE pex_snapshot
    ALTER COLUMN nmrr_pct                      TYPE NUMERIC(8,2),
    ALTER COLUMN reunioes_ec_du_realizado      TYPE NUMERIC(8,2),
    ALTER COLUMN contadores_trabalhados_pct    TYPE NUMERIC(8,2),
    ALTER COLUMN contadores_indicando_pct      TYPE NUMERIC(8,2),
    ALTER COLUMN contadores_ativando_pct       TYPE NUMERIC(8,2),
    ALTER COLUMN conversao_total_pct           TYPE NUMERIC(8,2),
    ALTER COLUMN conversao_m0_pct              TYPE NUMERIC(8,2),
    ALTER COLUMN conversao_inbound_pct         TYPE NUMERIC(8,2),
    ALTER COLUMN demo_du_realizado             TYPE NUMERIC(8,2),
    ALTER COLUMN demos_outbound_pct            TYPE NUMERIC(8,2),
    ALTER COLUMN sow_pct                       TYPE NUMERIC(8,2),
    ALTER COLUMN mapeamento_carteira_pct       TYPE NUMERIC(8,2),
    ALTER COLUMN reuniao_contador_inbound_pct  TYPE NUMERIC(8,2),
    ALTER COLUMN integracao_contabil_pct       TYPE NUMERIC(8,2),
    ALTER COLUMN early_churn_pct               TYPE NUMERIC(8,2),
    ALTER COLUMN crescimento_40_pct            TYPE NUMERIC(8,2),
    ALTER COLUMN utilizacao_desconto_pct       TYPE NUMERIC(8,2),
    ALTER COLUMN total_resultado_pts           TYPE NUMERIC(8,2),
    ALTER COLUMN total_gestao_pts              TYPE NUMERIC(8,2),
    ALTER COLUMN total_engajamento_pts         TYPE NUMERIC(8,2),
    ALTER COLUMN total_geral_pts               TYPE NUMERIC(8,2);

CREATE VIEW vw_pex_mes_atual AS
SELECT
    s.mes_ref,
    s.data_ref AS ultima_atualizacao,
    s.total_resultado_pts,
    s.total_gestao_pts,
    s.total_engajamento_pts,
    s.total_geral_pts,
    s.risco_classificacao,
    CASE
        WHEN s.total_geral_pts >= 95 THEN 'Franquia Excelente'
        WHEN s.total_geral_pts >= 76 THEN 'Franquia Certificada'
        WHEN s.total_geral_pts >= 60 THEN 'Franquia Qualificada'
        WHEN s.total_geral_pts >= 50 THEN 'Franquia Aderente'
        WHEN s.total_geral_pts >= 36 THEN 'Franquia em Desenvolvimento'
        ELSE 'Franquia Não Aderente'
    END AS classificacao
FROM pex_snapshot s
WHERE s.mes_ref = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
ORDER BY s.data_ref DESC
LIMIT 1;

COMMIT;