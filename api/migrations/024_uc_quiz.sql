-- =====================================================================
-- HIPO -- 024_uc_quiz.sql
--
-- Universidade Corporativa: quiz depois da aula (UC-2, sem gamificacao).
--
-- Hoje a aula conclui pela trava de tempo minimo, que garante presenca,
-- nao entendimento. Com quiz, a aula so conclui com aprovacao:
--   * 7 perguntas, uma correta por pergunta, 3 a 5 alternativas
--   * aprovacao com 85% (6 de 7); nota guardada em uc_aulas.nota_minima
--   * o quiz so abre depois do tempo minimo da aula (as duas travas)
--   * reprovou: nova tentativa depois de 10 minutos; a tela mostra quais
--     perguntas errou, nunca a alternativa certa
-- Aula sem pergunta continua concluindo pelo botao "Conclui".
--
-- TRES TABELAS
--   uc_perguntas     -- perguntas da aula (sem versao: o quiz e da aula)
--   uc_alternativas  -- alternativas; no maximo uma correta (indice parcial)
--   uc_tentativas    -- cada envio, com nota e o que errou, por versao
--
-- NAO E DESTRUTIVA: tres CREATE TABLE IF NOT EXISTS, um DEFAULT novo e um
-- UPDATE de nota_minima 70 -> 85 (valor nunca usado: nao havia quiz).
-- Nenhum DROP, nenhum DELETE. Idempotente. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS uc_perguntas (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aula_id    UUID NOT NULL REFERENCES uc_aulas(id) ON DELETE CASCADE,
    ordem      SMALLINT NOT NULL,
    enunciado  TEXT NOT NULL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uc_pergunta_ordem UNIQUE (aula_id, ordem) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_uc_pergunta_ordem CHECK (ordem >= 1),
    CONSTRAINT ck_uc_pergunta_enunciado CHECK (length(btrim(enunciado)) BETWEEN 1 AND 300)
);

CREATE TABLE IF NOT EXISTS uc_alternativas (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pergunta_id  UUID NOT NULL REFERENCES uc_perguntas(id) ON DELETE CASCADE,
    ordem        SMALLINT NOT NULL,
    texto        TEXT NOT NULL,
    correta      BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_uc_alternativa_ordem UNIQUE (pergunta_id, ordem) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_uc_alternativa_ordem CHECK (ordem >= 1),
    CONSTRAINT ck_uc_alternativa_texto CHECK (length(btrim(texto)) BETWEEN 1 AND 200)
);

-- No maximo uma correta por pergunta; "pelo menos uma" e regra do servico.
CREATE UNIQUE INDEX IF NOT EXISTS uq_uc_alternativa_correta
    ON uc_alternativas (pergunta_id) WHERE correta;

CREATE TABLE IF NOT EXISTS uc_tentativas (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id   UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    aula_id      UUID NOT NULL REFERENCES uc_aulas(id) ON DELETE CASCADE,
    aula_versao  SMALLINT NOT NULL,
    acertos      SMALLINT NOT NULL,
    total        SMALLINT NOT NULL,
    nota         SMALLINT NOT NULL,
    nota_minima  SMALLINT NOT NULL,
    aprovada     BOOLEAN NOT NULL,
    -- {pergunta_id: alternativa_id} como foi enviado.
    respostas    JSONB NOT NULL,
    -- ids das perguntas erradas, na ordem do quiz (a tela marca sem
    -- revelar a alternativa certa).
    erradas      JSONB NOT NULL DEFAULT '[]'::jsonb,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uc_tentativa_conta CHECK (total >= 1 AND acertos BETWEEN 0 AND total),
    CONSTRAINT ck_uc_tentativa_nota  CHECK (nota BETWEEN 0 AND 100 AND nota_minima BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_uc_tentativas_pessoa
    ON uc_tentativas (usuario_id, aula_id, aula_versao, criado_em DESC);

-- Corte do quiz: 85% (6 de 7). O default 70 da 020 nunca foi usado.
ALTER TABLE uc_aulas ALTER COLUMN nota_minima SET DEFAULT 85;
UPDATE uc_aulas SET nota_minima = 85 WHERE nota_minima = 70;
