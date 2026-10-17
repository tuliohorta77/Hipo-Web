-- =====================================================================
-- HIPO -- 043_repasses_contratos.sql
--
-- Modulo Contratos: o repasse que a Controller faz para a Spectre (16/10/2026).
--
-- O cliente paga a mensalidade (valor do contrato) para a Controller. A
-- Controller repassa para a Spectre uma parte dela:
--
--     repasse  = valor do contrato x percentual
--                (100% no primeiro mes -- premio de venda --, 30% depois)
--     imposto  = repasse x aliquota (14,33% hoje)
--     liquido  = repasse - imposto      <- o que entra de fato na Spectre
--
-- A soma dos liquidos do mes, menos os descontos combinados com a
-- Controller, e o valor da nota que a Spectre emite para a Controller.
--
-- NAO confundir com `contratos` (037): aquele e o documento assinado na
-- Autentique; este e o controle mensal de recebimento. Por isso as
-- tabelas tem o prefixo repasse_.
--
--   repasse_contratos     -- um por CNPJ cobrado. Ligado (opcional) a
--                            oportunidade e a conta. Parametros: modalidade
--                            (por vida ou valor fixo), percentuais, aliquota.
--   repasse_lancamentos   -- um por contrato e competencia: vidas cobradas,
--                            valor por vida ou valor fixo, e os quatro
--                            valores calculados (K, L, N e O da planilha).
--                            Os valores ficam gravados: mudar o percentual
--                            do contrato nao reescreve mes passado.
--   repasse_competencias  -- o fechamento do mes: NF emitida, recebimento.
--   repasse_descontos     -- linhas de desconto do mes (pagamento indevido,
--                            fatura em aberto...).
--
-- ADITIVA E IDEMPOTENTE. Sem BEGIN/COMMIT: quem abre a transacao e o
-- scripts/aplicar_migrations.
-- =====================================================================

CREATE TABLE IF NOT EXISTS repasse_contratos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id         UUID REFERENCES oportunidades(id) ON DELETE SET NULL,
    conta_id                UUID REFERENCES contas(id) ON DELETE SET NULL,
    -- Snapshot do CNPJ e da razao social. NULL no CNPJ = ainda nao
    -- identificado (a tela mostra "CNPJ pendente").
    cnpj                    CHAR(14),
    razao_social            VARCHAR(200) NOT NULL,
    data_venda              DATE NOT NULL,
    modalidade              VARCHAR(12) NOT NULL DEFAULT 'por_vida',
    vidas                   INTEGER,
    valor_por_vida          NUMERIC(12,2),
    valor_fixo              NUMERIC(12,2),
    percentual_repasse      NUMERIC(5,2) NOT NULL DEFAULT 30,
    percentual_primeiro_mes NUMERIC(5,2) NOT NULL DEFAULT 100,
    -- O mes que recebe o percentual do primeiro mes. NULL = ainda nao houve
    -- lancamento: o primeiro que entrar e o primeiro mes e grava a data aqui.
    primeira_competencia    DATE,
    imposto_percentual      NUMERIC(5,2) NOT NULL DEFAULT 14.33,
    status                  VARCHAR(10) NOT NULL DEFAULT 'ativo',
    encerrado_em            DATE,
    grupo                   VARCHAR(100),
    observacoes             TEXT,
    criado_por              UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_repasse_contrato_cnpj CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT ck_repasse_contrato_razao CHECK (length(btrim(razao_social)) > 0),
    CONSTRAINT ck_repasse_contrato_modalidade CHECK (
        (modalidade = 'por_vida'   AND valor_por_vida IS NOT NULL)
        OR
        (modalidade = 'valor_fixo' AND valor_fixo IS NOT NULL)
    ),
    CONSTRAINT ck_repasse_contrato_vidas CHECK (vidas IS NULL OR vidas >= 0),
    CONSTRAINT ck_repasse_contrato_valor_vida CHECK (valor_por_vida IS NULL OR valor_por_vida >= 0),
    CONSTRAINT ck_repasse_contrato_valor_fixo CHECK (valor_fixo IS NULL OR valor_fixo >= 0),
    CONSTRAINT ck_repasse_contrato_percentuais CHECK (
        percentual_repasse BETWEEN 0 AND 100
        AND percentual_primeiro_mes BETWEEN 0 AND 100
        AND imposto_percentual BETWEEN 0 AND 100
    ),
    CONSTRAINT ck_repasse_contrato_primeira CHECK (
        primeira_competencia IS NULL OR EXTRACT(DAY FROM primeira_competencia) = 1
    ),
    CONSTRAINT ck_repasse_contrato_status CHECK (
        (status = 'ativo'     AND encerrado_em IS NULL)
        OR
        (status = 'encerrado' AND encerrado_em IS NOT NULL)
    )
);

-- Um CNPJ nao tem dois contratos ativos: o segundo seria a mesma cobranca
-- lancada duas vezes no mes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_repasse_contrato_cnpj_ativo
    ON repasse_contratos (cnpj) WHERE status = 'ativo' AND cnpj IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_repasse_contratos_oportunidade
    ON repasse_contratos (oportunidade_id) WHERE oportunidade_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_repasse_contratos_conta
    ON repasse_contratos (conta_id) WHERE conta_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS repasse_lancamentos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id         UUID NOT NULL REFERENCES repasse_contratos(id) ON DELETE CASCADE,
    competencia         DATE NOT NULL,
    vidas               INTEGER NOT NULL DEFAULT 0,
    -- Preenchido quando a cobranca do mes foi por vida; NULL = valor fixo.
    valor_por_vida      NUMERIC(12,2),
    valor_contrato      NUMERIC(12,2) NOT NULL,   -- K: o que o cliente paga
    percentual_repasse  NUMERIC(5,2)  NOT NULL,
    valor_repasse       NUMERIC(12,2) NOT NULL,   -- L: devido a Spectre
    imposto_percentual  NUMERIC(5,2)  NOT NULL,
    valor_imposto       NUMERIC(12,2) NOT NULL,   -- N
    valor_liquido       NUMERIC(12,2) NOT NULL,   -- O: o que entra na Spectre
    primeiro_mes        BOOLEAN NOT NULL DEFAULT FALSE,
    -- O cliente pagou a Controller (coluna PAGO da planilha).
    pago                BOOLEAN NOT NULL DEFAULT FALSE,
    observacoes         TEXT,
    lancado_por         UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    lancado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_por      UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_repasse_lancamento UNIQUE (contrato_id, competencia),
    CONSTRAINT ck_repasse_lanc_competencia CHECK (EXTRACT(DAY FROM competencia) = 1),
    CONSTRAINT ck_repasse_lanc_vidas CHECK (vidas >= 0),
    CONSTRAINT ck_repasse_lanc_valores CHECK (
        (valor_por_vida IS NULL OR valor_por_vida >= 0)
        AND valor_contrato >= 0
        AND valor_repasse >= 0
        AND valor_imposto >= 0
        AND percentual_repasse BETWEEN 0 AND 100
        AND imposto_percentual BETWEEN 0 AND 100
    ),
    CONSTRAINT ck_repasse_lanc_liquido CHECK (valor_liquido = valor_repasse - valor_imposto)
);

CREATE INDEX IF NOT EXISTS idx_repasse_lancamentos_competencia
    ON repasse_lancamentos (competencia);


CREATE TABLE IF NOT EXISTS repasse_competencias (
    competencia     DATE PRIMARY KEY,
    nf_numero       VARCHAR(40),
    nf_emitida_em   DATE,
    recebido_em     DATE,
    observacoes     TEXT,
    atualizado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_repasse_comp_dia CHECK (EXTRACT(DAY FROM competencia) = 1)
);


CREATE TABLE IF NOT EXISTS repasse_descontos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competencia  DATE NOT NULL REFERENCES repasse_competencias(competencia) ON DELETE CASCADE,
    descricao    VARCHAR(200) NOT NULL,
    valor        NUMERIC(12,2) NOT NULL,
    criado_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_repasse_desconto_valor CHECK (valor > 0),
    CONSTRAINT ck_repasse_desconto_descricao CHECK (length(btrim(descricao)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_repasse_descontos_competencia
    ON repasse_descontos (competencia);
