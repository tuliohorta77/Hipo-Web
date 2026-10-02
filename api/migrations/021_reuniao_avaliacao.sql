-- =====================================================================
-- HIPO -- 021_reuniao_avaliacao.sql
--
-- O scorecard da reuniao contra o Roteiro de Vendas.
--
-- O FLUXO
--   1. A transcricao do Meet chega (016) pelo hipo-transcricoes.timer.
--   2. Na MESMA passada do timer, a reuniao de oportunidade com
--      transcricao pronta e avaliada pela IA contra o roteiro da casa
--      (services/roteiro_scorecard.py): 10 itens de 0 a 2, cada um com o
--      trecho literal da conversa, mais o resumo do coach.
--   3. A nota vale assim que sai: entra no quadro SCORECARD do Monitor e
--      na coluna Nota do detalhe do APRE. A gestao pode trocar a nota de
--      qualquer item (`nota_gestor`), e ai vale a dela. Validar e um selo
--      (`validada_em`), nao um portao.
--
-- POR QUE `nota_total` E GUARDADA
--   O Monitor le a media do mes de minuto em minuto. A soma dos itens com
--   COALESCE(nota_gestor, nota_ia) e recalculada pelo servico a cada
--   escrita (services/coleta_avaliacao.py e o unico que escreve aqui); o
--   painel so le o numero.
--
-- STATUS
--   aguardando -- a chamada a IA esta em andamento (ou caiu no meio:
--                 depois de 10 minutos o timer tenta de novo)
--   pronta     -- itens gravados, `nota_total` preenchida
--   erro       -- a IA falhou; `erro` diz por que. O timer tenta ate 3
--                 vezes; o botao "Avaliar de novo" sempre pode.
--
-- NAO E DESTRUTIVA: duas tabelas novas. Nenhum DROP, nenhum DELETE,
-- idempotente. Nao exige o export previo em CSV.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS reuniao_avaliacoes (
    reuniao_id         UUID PRIMARY KEY REFERENCES reunioes(id) ON DELETE CASCADE,
    -- A versao do roteiro usada. Roteiro novo nao reescreve avaliacao
    -- antiga: a nota de setembro foi dada contra o roteiro de setembro.
    versao_roteiro     VARCHAR(20) NOT NULL,
    status             VARCHAR(12) NOT NULL DEFAULT 'aguardando',
    -- Soma dos 10 itens, COALESCE(nota_gestor, nota_ia), item sem nota
    -- contando zero. NULL enquanto nao esta pronta.
    nota_total         SMALLINT,
    -- Quem foi avaliado: o responsavel pela reuniao no momento da
    -- avaliacao. SET NULL: a nota fica, mesmo sem o usuario.
    vendedor_id        UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    -- Percentual das palavras ditas pelo vendedor. Contado das falas, nao
    -- pela IA. NULL = vendedor nao identificado entre os participantes.
    fala_vendedor_pct  NUMERIC(5,1),

    -- O resumo do coach.
    resumo             TEXT,
    foco_proxima       TEXT,
    -- [{texto, evidencia}] e [{texto, evidencia, como_fazer}], ate 2 cada.
    pontos_fortes      JSONB NOT NULL DEFAULT '[]'::jsonb,
    pontos_melhorar    JSONB NOT NULL DEFAULT '[]'::jsonb,

    modelo             VARCHAR(64),
    erro               TEXT,
    tentativas         INTEGER NOT NULL DEFAULT 0,
    gerada_em          TIMESTAMPTZ,
    gerada_por         UUID REFERENCES usuarios(id) ON DELETE SET NULL,

    validada_por       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    validada_em        TIMESTAMPTZ,

    criado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_avaliacao_status
        CHECK (status IN ('aguardando', 'pronta', 'erro')),
    CONSTRAINT ck_avaliacao_pronta_tem_nota
        CHECK (status <> 'pronta' OR (nota_total IS NOT NULL AND gerada_em IS NOT NULL)),
    CONSTRAINT ck_avaliacao_nota_total
        CHECK (nota_total IS NULL OR nota_total BETWEEN 0 AND 20),
    CONSTRAINT ck_avaliacao_fala
        CHECK (fala_vendedor_pct IS NULL OR fala_vendedor_pct BETWEEN 0 AND 100),
    -- So se valida o que esta pronto.
    CONSTRAINT ck_avaliacao_validada
        CHECK (validada_em IS NULL OR status = 'pronta')
);

CREATE INDEX IF NOT EXISTS idx_reuniao_avaliacoes_status
    ON reuniao_avaliacoes (status, atualizado_em);

CREATE TABLE IF NOT EXISTS reuniao_avaliacao_itens (
    reuniao_id     UUID NOT NULL REFERENCES reuniao_avaliacoes(reuniao_id) ON DELETE CASCADE,
    item           SMALLINT NOT NULL,
    -- NULL = a IA deu nota sem trecho que conferisse; ver `descartado`.
    nota_ia        SMALLINT,
    -- A nota da gestao. Quando existe, e ela que vale.
    nota_gestor    SMALLINT,
    evidencia      TEXT,
    justificativa  TEXT,
    sugestao       TEXT,
    descartado     TEXT,
    ajustada_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    ajustada_em    TIMESTAMPTZ,

    PRIMARY KEY (reuniao_id, item),
    CONSTRAINT ck_avaliacao_item CHECK (item BETWEEN 1 AND 10),
    CONSTRAINT ck_avaliacao_nota_ia CHECK (nota_ia IS NULL OR nota_ia BETWEEN 0 AND 2),
    CONSTRAINT ck_avaliacao_nota_gestor CHECK (nota_gestor IS NULL OR nota_gestor BETWEEN 0 AND 2),
    CONSTRAINT ck_avaliacao_ajuste CHECK (
        (nota_gestor IS NULL AND ajustada_em IS NULL)
        OR (nota_gestor IS NOT NULL AND ajustada_em IS NOT NULL)
    )
);

COMMIT;
