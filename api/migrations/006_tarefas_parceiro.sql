-- =====================================================================
-- HIPO -- 006_tarefas_parceiro.sql
--
-- Tarefa presa ao PARCEIRO. Fecha a pendencia aberta na Sprint 6:
-- a tela de Parceiros era operacional (troca de EC, painel, transferencia)
-- mas nao agendava follow-up -- e follow-up e exatamente o trabalho do EC.
--
-- DECISOES QUE ESTA MIGRATION MATERIALIZA
--
-- 1) ESTENDE `tarefas`, NAO CRIA `parceiro_tarefas`.
--    Uma tabela nova duplicaria service, router, tela e a regra de situacao
--    derivada -- e duas copias da mesma regra divergem no primeiro ajuste.
--    Saida ja registrada no doc de especificacao: oportunidade_id opcional +
--    conta_id, com CHECK exigindo exatamente um.
--
-- 2) EXATAMENTE UM ALVO, nunca zero e nunca dois.
--    `num_nonnulls(oportunidade_id, conta_id) = 1`. Zero alvos seria a lista
--    de afazeres pessoal que a Sprint 5 recusou de proposito; dois alvos
--    tornaria ambiguo em qual funil a tarefa conta.
--
-- 3) O DROP NOT NULL DE oportunidade_id NAO PERDE DADO.
--    Afrouxar restricao nao apaga linha: toda tarefa existente continua com
--    a oportunidade preenchida e passa a satisfazer o CHECK novo sem
--    backfill. Por isso esta migration NAO exige export previo em CSV/ZIP --
--    a regra do doc vale para DROP de coluna ou tabela, e aqui nao ha
--    nenhum.
--
-- 4) O INDICE DO FAROL E PARCIAL E POR (conta_id, prazo).
--    O farol semanal varre as tarefas de um parceiro nas ultimas 4 semanas.
--    Parcial em conta_id IS NOT NULL porque tarefa de oportunidade -- que e
--    e vai continuar sendo a maioria -- nunca entra nessa consulta.
--
-- NAO E DESTRUTIVA: nenhum DROP de coluna ou tabela.
-- Idempotente: pode rodar duas vezes.
-- =====================================================================

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.tarefas') IS NULL THEN
        RAISE EXCEPTION 'Tabela tarefas nao existe. Rode 004_tarefas.sql antes.';
    END IF;
    IF to_regclass('public.contas') IS NULL THEN
        RAISE EXCEPTION 'Tabela contas nao existe. Rode 002_crm_core.sql antes.';
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 1. O alvo alternativo
-- ---------------------------------------------------------------------
ALTER TABLE tarefas
    ADD COLUMN IF NOT EXISTS conta_id UUID REFERENCES contas(id) ON DELETE CASCADE;

ALTER TABLE tarefas
    ALTER COLUMN oportunidade_id DROP NOT NULL;

-- ---------------------------------------------------------------------
-- 2. Exatamente um alvo
-- ---------------------------------------------------------------------
-- num_nonnulls e funcao nativa do Postgres desde a 9.6 e le melhor que a
-- forma com OR/AND negados. IS NOT VALID nao e usado de proposito: toda
-- linha existente ja satisfaz (oportunidade_id NOT NULL, conta_id NULL),
-- entao a validacao imediata nao trava nada e evita restricao meio-viva.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'tarefas'::regclass AND conname = 'ck_tarefa_alvo'
    ) THEN
        ALTER TABLE tarefas
            ADD CONSTRAINT ck_tarefa_alvo
            CHECK (num_nonnulls(oportunidade_id, conta_id) = 1);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 3. Indices
-- ---------------------------------------------------------------------
-- Aba de tarefas do parceiro: tudo daquele parceiro, na ordem do prazo.
CREATE INDEX IF NOT EXISTS idx_tarefas_conta
    ON tarefas (conta_id, prazo)
    WHERE conta_id IS NOT NULL;

-- Farol semanal: as concluidas de um parceiro numa janela de datas. O
-- verde do farol olha concluida_em (quando o contato ACONTECEU), nao prazo
-- (quando estava previsto) -- por isso o indice e por concluida_em.
CREATE INDEX IF NOT EXISTS idx_tarefas_conta_concluidas
    ON tarefas (conta_id, concluida_em)
    WHERE conta_id IS NOT NULL AND concluida_em IS NOT NULL;

COMMIT;

-- Conferencia -----------------------------------------------------------
--   \d tarefas
--   SELECT conname FROM pg_constraint WHERE conrelid = 'tarefas'::regclass;
--   -- deve recusar tarefa sem alvo e tarefa com dois alvos:
--   INSERT INTO tarefas (tipo, titulo, responsavel_id, prazo)
--        VALUES ('ligacao', 'sem alvo', <uuid>, NOW());   -- ck_tarefa_alvo
