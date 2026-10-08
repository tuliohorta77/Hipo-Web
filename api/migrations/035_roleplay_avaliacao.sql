-- =====================================================================
-- HIPO -- 035_roleplay_avaliacao.sql
--
-- Carreira · Roleplay com IA (RP-2): a nota do treino contra o Roteiro de
-- Vendas. Mesma regua do scorecard das reunioes reais (10 itens de 0 a 2,
-- trecho literal obrigatorio), em tabelas PROPRIAS: o roleplay nao pode
-- vazar para o Monitor nem para o SCORECARD do mes (reuniao_avaliacoes).
--
-- Bloco de 15 min conta so os itens do bloco (itens_foco), e nota_total e
-- reescalada para 0..20. A gestao ajusta item a item (nota_gestor) e
-- valida com selo; vale COALESCE(nota_gestor, nota_ia).
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nao exige export.
-- =====================================================================

CREATE TABLE IF NOT EXISTS roleplay_avaliacoes (
    sessao_id        UUID PRIMARY KEY REFERENCES roleplay_sessoes(id) ON DELETE CASCADE,
    -- aguardando | pronta | erro | sem_conteudo
    status           VARCHAR(14) NOT NULL DEFAULT 'aguardando',
    versao_roteiro   VARCHAR(20) NOT NULL,
    itens_foco       SMALLINT[] NOT NULL,
    -- 0..20, reescalada a partir dos itens do foco. Recalculada a cada
    -- escrita de item (routers/roleplay.py e o unico que escreve).
    nota_total       NUMERIC(4,1),
    resumo           TEXT,
    foco_proxima     TEXT,
    pontos_fortes    JSONB NOT NULL DEFAULT '[]'::jsonb,
    pontos_melhorar  JSONB NOT NULL DEFAULT '[]'::jsonb,
    modelo           VARCHAR(60),
    erro             TEXT,
    tentativas       SMALLINT NOT NULL DEFAULT 0,
    iniciada_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    gerada_em        TIMESTAMPTZ,
    validada_em      TIMESTAMPTZ,
    validada_por     UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT ck_rp_aval_status CHECK (status IN ('aguardando', 'pronta', 'erro', 'sem_conteudo')),
    CONSTRAINT ck_rp_aval_nota CHECK (nota_total IS NULL OR nota_total BETWEEN 0 AND 20)
);

CREATE TABLE IF NOT EXISTS roleplay_avaliacao_itens (
    sessao_id      UUID NOT NULL REFERENCES roleplay_avaliacoes(sessao_id) ON DELETE CASCADE,
    item           SMALLINT NOT NULL,
    nota_ia        SMALLINT,
    nota_gestor    SMALLINT,
    evidencia      TEXT,
    justificativa  TEXT,
    sugestao       TEXT,
    -- Motivo quando a nota da IA foi descartada (trecho nao encontrado).
    descartado     TEXT,
    ajustada_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    ajustada_em    TIMESTAMPTZ,
    PRIMARY KEY (sessao_id, item),
    CONSTRAINT ck_rp_item CHECK (item BETWEEN 1 AND 10),
    CONSTRAINT ck_rp_item_nota_ia CHECK (nota_ia IS NULL OR nota_ia BETWEEN 0 AND 2),
    CONSTRAINT ck_rp_item_nota_gestor CHECK (nota_gestor IS NULL OR nota_gestor BETWEEN 0 AND 2)
);
