-- ============================================================
-- Migration 004 — BD Ativados: cálculo de MRR no upload
-- ============================================================
-- Idempotente. Pode rodar múltiplas vezes sem quebrar.
--
-- Adiciona:
--   bd_ativados_upload: data_emissao, linhas_ativas, mrr_bruto,
--                       repasse_franqueado, liquido_pos_mkt
--   bd_ativados:        tipo, valor_mensal_informado, mrr_bruto
--
-- Cria view: vw_bd_ativados_atual

BEGIN;

-- bd_ativados_upload
ALTER TABLE bd_ativados_upload
    ADD COLUMN IF NOT EXISTS data_emissao        VARCHAR(40),
    ADD COLUMN IF NOT EXISTS linhas_ativas       INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mrr_bruto           NUMERIC(14,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS repasse_franqueado  NUMERIC(14,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS liquido_pos_mkt     NUMERIC(14,2) DEFAULT 0;

-- bd_ativados
ALTER TABLE bd_ativados
    ADD COLUMN IF NOT EXISTS tipo                   VARCHAR(80),
    ADD COLUMN IF NOT EXISTS valor_mensal_informado NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS mrr_bruto              NUMERIC(14,2) DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_bd_ativados_tipo ON bd_ativados(tipo);

-- View: snapshot atual (último upload processado)
CREATE OR REPLACE VIEW vw_bd_ativados_atual AS
SELECT
    bu.id, bu.data_upload, bu.data_emissao, bu.nome_arquivo,
    bu.total_registros, bu.linhas_ativas,
    bu.mrr_bruto, bu.repasse_franqueado, bu.liquido_pos_mkt
FROM bd_ativados_upload bu
WHERE bu.processado = TRUE
ORDER BY bu.data_upload DESC
LIMIT 1;

COMMIT;
