-- =====================================================================
-- HIPO -- 027_pdi.sql
--
-- Carreira · PDI (plano de desenvolvimento individual), modelo misto:
-- o HIPO sugere (Desempenho e Universidade), a gestao confirma, ajusta,
-- descarta ou cria, e o colaborador marca como feita.
--
-- UMA TABELA: pdi_acoes. Sugestao NAO e gravada (e recalculada a cada
-- abertura); vira linha quando a gestao confirma (aberta) ou descarta
-- (descartada). A chave_origem impede que a mesma sugestao volte.
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nenhum DROP,
-- nenhum DELETE. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS pdi_acoes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id      UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    -- desempenho | uc | gestao (criada do zero pela gestao)
    origem          VARCHAR(12) NOT NULL,
    -- 'desempenho:2026-10:nmrr', 'uc:trilha:<id>', 'uc:quiz:<id>'; NULL
    -- para acao criada do zero.
    chave_origem    VARCHAR(120),
    objetivo        VARCHAR(200) NOT NULL,
    o_que_fazer     TEXT NOT NULL,
    trilha_id       UUID REFERENCES uc_trilhas(id) ON DELETE SET NULL,
    prazo           DATE NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'aberta',
    criada_por      UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    concluida_em    TIMESTAMPTZ,
    -- NULL com concluida_em = concluida sozinha (trilha da acao concluida).
    concluida_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    nota_conclusao  TEXT,
    CONSTRAINT ck_pdi_origem CHECK (origem IN ('desempenho', 'uc', 'gestao')),
    CONSTRAINT ck_pdi_status CHECK (status IN ('aberta', 'concluida', 'cancelada', 'descartada')),
    CONSTRAINT ck_pdi_objetivo CHECK (length(btrim(objetivo)) > 0),
    CONSTRAINT ck_pdi_conclusao CHECK ((status = 'concluida') = (concluida_em IS NOT NULL)),
    CONSTRAINT uq_pdi_chave UNIQUE (usuario_id, chave_origem)
);

CREATE INDEX IF NOT EXISTS idx_pdi_pessoa ON pdi_acoes (usuario_id, status, prazo);
