-- ============================================================
-- HIPO — Migration 002: Valor a Receber de PO + linhas especiais
-- ============================================================
-- Aplica:
--   1. Campos de agregado em po_uploads (numero_po, valor_a_receber etc)
--   2. Campos de linha especial em po_linhas (Fundo Marketing + Subtotal)
--   3. Atualiza vw_reconciliacao_atual pra ignorar linhas especiais
--
-- Rodar na EC2:
--   psql $DATABASE_URL -f migrations/002_po_valor_a_receber.sql
-- ============================================================

BEGIN;

-- ── 1) Campos de agregado em po_uploads ──────────────────────────────
ALTER TABLE po_uploads
    ADD COLUMN IF NOT EXISTS numero_po              VARCHAR(20),
    ADD COLUMN IF NOT EXISTS soma_operacoes         NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS fundo_marketing_total  NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS valor_a_receber        NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS subtotal_planilha      NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS tem_diferenca_calculo  BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS observacao_calculo     TEXT;

CREATE INDEX IF NOT EXISTS idx_po_uploads_numero_po ON po_uploads(numero_po);

-- ── 2) Linhas especiais em po_linhas ─────────────────────────────────
-- Tipos:
--   FUNDO_MARKETING — linha "Fundo de Marketing (2,5%)" (valor negativo)
--   SUBTOTAL        — linha sem descrição com soma final (= operações + fundo)
DO $$ BEGIN
    CREATE TYPE po_tipo_linha_especial AS ENUM ('FUNDO_MARKETING', 'SUBTOTAL');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE po_linhas
    ADD COLUMN IF NOT EXISTS eh_linha_especial    BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS tipo_linha_especial  po_tipo_linha_especial,
    -- numero_po também na linha facilita agregações sem JOIN
    ADD COLUMN IF NOT EXISTS numero_po            VARCHAR(20);

-- Em linhas especiais, referencia_aplicativo é NULL — relaxa o NOT NULL
ALTER TABLE po_linhas ALTER COLUMN referencia_aplicativo DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_po_linhas_especial ON po_linhas(eh_linha_especial)
    WHERE eh_linha_especial = TRUE;

-- ── 3) View de reconciliação ignora linhas especiais ─────────────────
CREATE OR REPLACE VIEW vw_reconciliacao_atual AS
SELECT
    pl.tipo,
    pl.tem_enabler,
    pl.status_reconciliacao,
    COUNT(*) AS quantidade,
    SUM(pl.valor_liquido) AS valor_total,
    SUM(pl.divergencia_valor) AS divergencia_total
FROM po_linhas pl
JOIN po_uploads pu ON pu.id = pl.upload_id
WHERE pu.semana_ref = (
    SELECT MAX(semana_ref) FROM po_uploads WHERE processado = TRUE
)
  AND pl.eh_linha_especial = FALSE
GROUP BY pl.tipo, pl.tem_enabler, pl.status_reconciliacao;

COMMIT;
