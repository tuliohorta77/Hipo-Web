-- ============================================================
-- HIPO — Migration 006: Refatoração de pex_snapshot
-- ============================================================
-- Antes: 1 linha por mês com ~50 colunas (1 par pct/pts por indicador)
-- Depois: cabeçalho + tabela filha (1 linha por indicador)
--
-- Mudanças:
--   - Renomeia pex_snapshot → pex_snapshot_legacy (preserva histórico)
--   - Cria pex_snapshot novo (só cabeçalho com totais)
--   - Cria pex_snapshot_indicadores (1 linha por indicador, com realizado/meta/pct/pts/detalhes_json)
--   - Migra dados do legacy pra estrutura nova (best-effort: pct/pts conhecidos viram linhas)
--   - Recria vw_pex_mes_atual apontando pra estrutura nova
-- ============================================================

BEGIN;

-- ─── Renomeia tabela antiga (preserva histórico) ───
DROP VIEW IF EXISTS vw_pex_mes_atual;
ALTER TABLE pex_snapshot RENAME TO pex_snapshot_legacy;

-- ─── Nova pex_snapshot (cabeçalho enxuto) ───
CREATE TABLE pex_snapshot (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_ref                    DATE NOT NULL DEFAULT CURRENT_DATE,
    mes_ref                     CHAR(7) NOT NULL,
    upload_cromie_id            UUID,
    total_resultado_pts         NUMERIC(8,2) DEFAULT 0,
    total_gestao_pts            NUMERIC(8,2) DEFAULT 0,
    total_engajamento_pts       NUMERIC(8,2) DEFAULT 0,
    total_geral_pts             NUMERIC(8,2) DEFAULT 0,
    risco_classificacao         risco_enum,                 -- VERDE/LARANJA/AMARELO/VERMELHO (cor UI)
    classificacao_oficial       VARCHAR(40),                -- 6 faixas oficiais do manual
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mes_ref, data_ref)
);

CREATE INDEX ix_pex_snapshot_mes ON pex_snapshot(mes_ref DESC);
CREATE INDEX ix_pex_snapshot_data ON pex_snapshot(data_ref DESC);

-- ─── Tabela filha: 1 linha por indicador ───
CREATE TABLE pex_snapshot_indicadores (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     UUID NOT NULL REFERENCES pex_snapshot(id) ON DELETE CASCADE,
    codigo          VARCHAR(40) NOT NULL,         -- ex: 'nmrr', 'contadores_trabalhados'
    pilar           VARCHAR(20) NOT NULL,         -- RESULTADO/GESTAO/ENGAJAMENTO
    nome            VARCHAR(80) NOT NULL,         -- humano: "NMRR", "Contadores trabalhados"
    pts_max         NUMERIC(5,2) NOT NULL,        -- peso máximo do indicador (10, 3, 2, etc.)
    realizado       NUMERIC(14,2),                -- valor absoluto realizado
    meta            NUMERIC(14,2),                -- meta numérica (cf. cluster ou universal)
    unidade         VARCHAR(20),                  -- "R$" / "%" / "qtd" / "/du" / "binário"
    pct             NUMERIC(8,2) DEFAULT 0,       -- atingimento (realizado/meta * 100)
    pts             NUMERIC(5,2) DEFAULT 0,       -- pontos calculados pela faixa
    detalhes_json   JSONB,                        -- numerador, denominador, filtros, fonte
    UNIQUE (snapshot_id, codigo)
);

CREATE INDEX ix_pex_snap_ind_snapshot ON pex_snapshot_indicadores(snapshot_id);
CREATE INDEX ix_pex_snap_ind_codigo ON pex_snapshot_indicadores(codigo);

-- ─── View principal (último snapshot do mês) ───
CREATE OR REPLACE VIEW vw_pex_mes_atual AS
SELECT
    s.id,
    s.mes_ref,
    s.data_ref AS ultima_atualizacao,
    s.total_resultado_pts,
    s.total_gestao_pts,
    s.total_engajamento_pts,
    s.total_geral_pts,
    s.risco_classificacao,
    s.classificacao_oficial AS classificacao
FROM pex_snapshot s
WHERE s.mes_ref = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
ORDER BY s.data_ref DESC
LIMIT 1;

COMMIT;
