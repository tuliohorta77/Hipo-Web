-- =====================================================================
-- HIPO -- 034_roleplay.sql
--
-- Carreira · Roleplay com IA (RP-1). O executivo treina por voz com uma
-- IA (Gemini Live) no papel do cliente; a conversa vai direto do
-- navegador para o Google e o HIPO guarda a sessao: quem, qual cenario,
-- quanto durou, a gravacao (S3), a transcricao, os tokens e o custo.
--
-- DUAS TABELAS:
--   roleplay_sessoes         uma linha por treino.
--   roleplay_consentimentos  ciencia da gravacao de voz (LGPD), por pessoa
--                            e versao do termo.
--
-- Os CENARIOS (personas) moram no codigo (services/roleplay_cenarios.py),
-- como o conteudo da UC: a sessao guarda o id e a versao do cenario. A
-- AVALIACAO (nota) entra na RP-2, em tabela propria.
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nenhum DROP,
-- nenhum DELETE. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS roleplay_sessoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id          UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    cenario_id          VARCHAR(60) NOT NULL,
    cenario_versao      SMALLINT NOT NULL,
    -- false para sessao da gestao: treina, mas fica fora das medias.
    conta_media         BOOLEAN NOT NULL DEFAULT TRUE,
    -- iniciada | encerrada | abandonada (RP-2 acrescenta a avaliacao).
    status              VARCHAR(12) NOT NULL DEFAULT 'iniciada',
    iniciada_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    encerrada_em        TIMESTAMPTZ,
    duracao_s           INTEGER,
    modelo_voz          VARCHAR(80) NOT NULL,
    -- Quantos tokens efemeros o Google emitiu para esta sessao (1 no inicio
    -- + 1 por reconexao). Trava a reconexao em loop.
    tokens_emitidos     SMALLINT NOT NULL DEFAULT 1,
    reconexoes          SMALLINT,
    latencia_media_ms   INTEGER,
    -- roleplay/<usuario_id>/<sessao_id>.webm no bucket dos anexos.
    audio_s3_chave      TEXT,
    audio_bytes         INTEGER,
    -- [{quem: "executivo"|"cliente", texto, t_ms}]
    transcricao         JSONB,
    fala_executivo_pct  SMALLINT,
    -- usageMetadata somado: {audio_in, texto_in, audio_out, texto_out, total}
    tokens              JSONB,
    custo_estimado_usd  NUMERIC(8,4),
    -- encerrou | tempo | queda | saldo
    motivo_fim          VARCHAR(12),
    CONSTRAINT ck_roleplay_status CHECK (status IN ('iniciada', 'encerrada', 'abandonada')),
    CONSTRAINT ck_roleplay_motivo CHECK (
        motivo_fim IS NULL OR motivo_fim IN ('encerrou', 'tempo', 'queda', 'saldo')),
    CONSTRAINT ck_roleplay_encerrada CHECK ((status = 'encerrada') = (encerrada_em IS NOT NULL)),
    CONSTRAINT ck_roleplay_fala CHECK (fala_executivo_pct IS NULL OR fala_executivo_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_roleplay_custo CHECK (custo_estimado_usd IS NULL OR custo_estimado_usd >= 0)
);

CREATE INDEX IF NOT EXISTS idx_roleplay_pessoa ON roleplay_sessoes (usuario_id, iniciada_em DESC);
-- Orcamento do mes: soma do custo de todas as sessoes do periodo.
CREATE INDEX IF NOT EXISTS idx_roleplay_iniciada ON roleplay_sessoes (iniciada_em);

CREATE TABLE IF NOT EXISTS roleplay_consentimentos (
    usuario_id    UUID PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    versao_termo  VARCHAR(20) NOT NULL,
    aceito_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
