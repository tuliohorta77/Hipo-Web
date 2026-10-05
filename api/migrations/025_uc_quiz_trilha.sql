-- =====================================================================
-- HIPO -- 025_uc_quiz_trilha.sql
--
-- Universidade Corporativa: o quiz passa a ser UM SO, no final da trilha
-- (decisao do Tulio em 05/10/2026, logo depois da 024).
--
--   * as aulas voltam a concluir pela trava de tempo
--   * o banco de perguntas continua por aula (uc_perguntas, da 024)
--   * o quiz final sorteia 10 perguntas do banco das aulas da trilha e
--     aprova com 85% (9 de 10); a trilha so conclui com aprovacao
--   * reprovou: nova tentativa em 10 minutos, com outro sorteio
--
-- UMA TABELA NOVA: uc_tentativas_trilha (cada envio do quiz final).
-- uc_tentativas (da 024, por aula) fica como historico e deixa de ser
-- escrita.
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nenhum DROP,
-- nenhum DELETE. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS uc_tentativas_trilha (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id   UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    trilha_id    UUID NOT NULL REFERENCES uc_trilhas(id) ON DELETE CASCADE,
    acertos      SMALLINT NOT NULL,
    total        SMALLINT NOT NULL,
    nota         SMALLINT NOT NULL,
    nota_minima  SMALLINT NOT NULL,
    aprovada     BOOLEAN NOT NULL,
    -- ids das perguntas sorteadas, na ordem em que apareceram.
    perguntas    JSONB NOT NULL,
    -- {pergunta_id: alternativa_id} como foi enviado.
    respostas    JSONB NOT NULL,
    -- [{numero, aula_ordem, aula_titulo}] das erradas: a tela diz qual
    -- aula rever, nunca a alternativa certa.
    erradas      JSONB NOT NULL DEFAULT '[]'::jsonb,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uc_tent_trilha_conta CHECK (total >= 1 AND acertos BETWEEN 0 AND total),
    CONSTRAINT ck_uc_tent_trilha_nota  CHECK (nota BETWEEN 0 AND 100 AND nota_minima BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_uc_tent_trilha_pessoa
    ON uc_tentativas_trilha (usuario_id, trilha_id, criado_em DESC);
