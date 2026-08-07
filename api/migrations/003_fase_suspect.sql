-- =====================================================================
-- HIPO -- 003_fase_suspect.sql
--
-- Acrescenta 'suspect' como primeira fase do funil.
--
--   suspect -> lead -> qualificacao -> apresentacao -> negociacao -> finalizado
--
-- 'suspect' e a boca do funil: empresa que entrou na base mas que ninguem
-- ainda tocou. Vira 'lead' quando existe contato e interesse demonstrado.
--
-- NAO E DESTRUTIVA. Nenhum DROP de tabela, coluna ou dado -- so relaxa dois
-- CHECKs para aceitar um valor a mais e troca o DEFAULT da coluna. Por isso
-- nao exige o export previo em CSV/ZIP que a regra do projeto pede antes de
-- migration destrutiva.
--
-- Idempotente: DROP CONSTRAINT IF EXISTS antes de cada ADD, entao rodar duas
-- vezes deixa o banco no mesmo estado.
--
-- Aplicar em producao DEPOIS do deploy do codigo nao serve: o backend novo
-- passa a mandar fase='suspect' e o CHECK antigo recusaria com 23514. Ordem
-- correta: migration primeiro, deploy depois.
-- =====================================================================

BEGIN;

-- Guarda de sanidade: se a tabela nao existir, esta e a migration errada
-- para este banco.
DO $$
BEGIN
    IF to_regclass('public.oportunidades') IS NULL THEN
        RAISE EXCEPTION 'Tabela oportunidades nao existe. Rode 002_crm_core.sql antes.';
    END IF;
END $$;

-- 1) Fase valida --------------------------------------------------------
ALTER TABLE oportunidades DROP CONSTRAINT IF EXISTS ck_opp_fase;
ALTER TABLE oportunidades ADD CONSTRAINT ck_opp_fase CHECK (
    fase IN ('suspect', 'lead', 'qualificacao', 'apresentacao',
             'negociacao', 'finalizado')
);

-- 2) Fase de desfecho ---------------------------------------------------
-- fase_desfecho guarda de qual fase aberta a oportunidade saiu ao ser
-- finalizada. Com 'suspect' no funil, da para perder ainda na boca dele --
-- lead do finder que nunca atendeu, por exemplo -- e isso precisa ser
-- registravel.
ALTER TABLE oportunidades DROP CONSTRAINT IF EXISTS ck_opp_fase_desfecho;
ALTER TABLE oportunidades ADD CONSTRAINT ck_opp_fase_desfecho CHECK (
    (fase = 'finalizado' AND fase_desfecho IN (
        'suspect', 'lead', 'qualificacao', 'apresentacao', 'negociacao'))
    OR
    (fase <> 'finalizado' AND fase_desfecho IS NULL)
);

-- 3) DEFAULT da coluna --------------------------------------------------
-- A API sempre manda a fase explicita, entao o DEFAULT so vale para INSERT
-- manual em psql. Ainda assim deve apontar para a boca do funil.
ALTER TABLE oportunidades ALTER COLUMN fase SET DEFAULT 'suspect';

COMMIT;

-- Conferencia -----------------------------------------------------------
-- Deve listar as duas constraints com 'suspect' no texto.
--
--   SELECT conname, pg_get_constraintdef(oid)
--     FROM pg_constraint
--    WHERE conrelid = 'oportunidades'::regclass
--      AND conname IN ('ck_opp_fase', 'ck_opp_fase_desfecho');
