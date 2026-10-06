-- =====================================================================
-- HIPO -- 029_confirmacao_vespera.sql
--
-- Tarefa automatica de confirmacao da vespera.
--
--   Reuniao marcada numa oportunidade com pelo menos dois dias uteis de
--   antecedencia abre, sozinha, uma tarefa de WhatsApp para quem agendou
--   (reunioes.agendado_por) no dia util anterior, 09:00. A tarefa segue a
--   reuniao: remarcou, ela muda de dia; cancelou ou teve desfecho, ela e
--   cancelada.
--
--   tarefas.confirmacao_de aponta para a tarefa da reuniao. E o que deixa
--   a agenda achar a confirmacao para move-la, e o que tira a confirmacao
--   da conta de "proximo passo" da oportunidade (contar_outras_abertas):
--   ela nao e passo do funil, e contada faria o desfecho da reuniao deixar
--   de exigir a proxima tarefa.
--
-- ADITIVA E IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, constraint dentro de
-- DO com checagem, CREATE INDEX IF NOT EXISTS. Nenhum DROP, DELETE ou
-- UPDATE em dado existente. Nao exige export previo.
-- =====================================================================

BEGIN;

ALTER TABLE tarefas
    ADD COLUMN IF NOT EXISTS confirmacao_de UUID
    REFERENCES tarefas(id) ON DELETE CASCADE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_tarefa_confirmacao'
    ) THEN
        ALTER TABLE tarefas ADD CONSTRAINT ck_tarefa_confirmacao CHECK (
            confirmacao_de IS NULL OR confirmacao_de <> id
        );
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tarefas_confirmacao_aberta
    ON tarefas (confirmacao_de)
    WHERE confirmacao_de IS NOT NULL
      AND concluida_em IS NULL AND cancelada_em IS NULL;

COMMIT;
