-- =====================================================================
-- HIPO -- 041_contrato_primeiro_vencimento.sql
--
-- Vencimento do contrato (entrega 058).
--
-- Regra do Tulio (15/10/2026): o primeiro vencimento e 30 dias depois da
-- emissao do contrato; os demais caem no mesmo dia dos meses seguintes.
-- Antes era "todo dia 10" fixo.
--
--   contratos.primeiro_vencimento  -- a data do 1o vencimento (NULL nos
--                                     contratos anteriores a esta entrega)
--   contratos.dia_vencimento       -- continua: o dia dos meses seguintes
--                                     (= dia do primeiro vencimento). Passa a
--                                     aceitar 29, 30 e 31; o contrato diz que
--                                     nos meses sem o dia vence no ultimo dia.
--
-- ADITIVA. So troca a CHECK do dia (DROP CONSTRAINT, nao de tabela nem de
-- coluna). Sem BEGIN/COMMIT: quem abre a transacao e o
-- scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE contratos ADD COLUMN IF NOT EXISTS primeiro_vencimento DATE;

ALTER TABLE contratos DROP CONSTRAINT IF EXISTS ck_contrato_vencimento;
ALTER TABLE contratos ADD CONSTRAINT ck_contrato_vencimento CHECK (
    dia_vencimento BETWEEN 1 AND 31
);

ALTER TABLE contratos DROP CONSTRAINT IF EXISTS ck_contrato_primeiro_vencimento;
ALTER TABLE contratos ADD CONSTRAINT ck_contrato_primeiro_vencimento CHECK (
    primeiro_vencimento IS NULL
    OR (primeiro_vencimento > data_contrato
        AND EXTRACT(DAY FROM primeiro_vencimento) = dia_vencimento)
);
