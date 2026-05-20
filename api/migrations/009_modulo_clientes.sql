-- ============================================================
-- HIPO -- Migration 009: Módulo Clientes (Oportunidades + Tarefas)
--
-- Suporta gestão da base de leads/oportunidades comerciais e
-- das tarefas associadas a cada oportunidade.
--
-- Os dados vêm de dois uploads independentes (XLSX) e são SNAPSHOTS
-- (cada upload SUBSTITUI a base anterior — mesmo padrão da Carteira
-- e do BD Ativados).
--
-- Relacionamento:
--   cliente_oportunidade (OP ID)
--     └── cliente_tarefa  (OP ID FK lógica, não enforçada porque os
--                          uploads são independentes)
--
-- Vinculação com contadores:
--   cliente_oportunidade.cnpj_contador → carteira_cnpj.cnpj_contador
--
-- Idempotente: usa IF NOT EXISTS.
-- ============================================================

-- ── UPLOADS ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cliente_upload (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo            VARCHAR(20) NOT NULL,  -- 'OPORTUNIDADES' | 'TAREFAS'
    data_upload     TIMESTAMPTZ DEFAULT NOW(),
    usuario_id      UUID REFERENCES usuarios(id),
    nome_arquivo    VARCHAR(200),
    total_linhas    INT,
    total_validos   INT,
    processado      BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_cliente_upload_tipo_data
    ON cliente_upload(tipo, data_upload DESC);

-- ── OPORTUNIDADES (LEADS) ─────────────────────────────────────
-- Cada linha = uma oportunidade comercial. Tabela truncada a cada
-- upload de OPORTUNIDADES.

CREATE TABLE IF NOT EXISTS cliente_oportunidade (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id               UUID REFERENCES cliente_upload(id) ON DELETE CASCADE,

    -- Identificação
    op_id                   BIGINT,                     -- OP ID (chave de origem)
    cnpj                    VARCHAR(20),
    razao_social            VARCHAR(200),

    -- Datas
    data_criacao            TIMESTAMPTZ,
    data_agendamento        VARCHAR(20),                -- vem como string na planilha (formato variado)
    data_atualizacao        TIMESTAMPTZ,
    ult_prox_tarefa         TIMESTAMPTZ,

    -- Funil
    origem_crm              VARCHAR(80),
    origem_macro            VARCHAR(20),                -- 'Inbound' | 'Outbound'
    status                  VARCHAR(20),                -- 'Em andamento' | 'Perdido' | 'Cancelado' | 'Conquistado'
    fase                    VARCHAR(40),                -- '01. Suspect' | '02. Cadência' | ...
    motivo_perda            VARCHAR(80),
    temperatura             NUMERIC(8,2),

    -- Valores
    proposta_nmrr           NUMERIC(12,2),
    proposta_pack           NUMERIC(12,2),
    previsao_valor          NUMERIC(12,2),
    previsao_data           TIMESTAMPTZ,

    -- Classificação do cliente
    cnae                    BIGINT,
    cnae_bim                VARCHAR(10),
    secao                   VARCHAR(80),
    setor                   VARCHAR(40),
    faixa_faturamento       VARCHAR(40),

    -- Datas de fase
    fase_suspect            TIMESTAMPTZ,
    fase_cadencia           TIMESTAMPTZ,
    fase_qualificacao       TIMESTAMPTZ,
    fase_apresentacao       TIMESTAMPTZ,
    fase_proposta           TIMESTAMPTZ,
    fase_conquistado        TIMESTAMPTZ,

    -- Unidade / atribuições
    unidade                 VARCHAR(60),
    cnpj_contador           VARCHAR(20),
    razao_contador          VARCHAR(200),
    executivo_contas        VARCHAR(80),
    sdr_fr                  VARCHAR(60),
    sdr_gd                  VARCHAR(60),
    executivo_vendas        VARCHAR(60),
    executivo_vendas_gd     VARCHAR(60),

    -- Produto/treinamento
    tipo_produto            VARCHAR(40),
    tipo_treinamento        VARCHAR(40),

    -- Telemetria
    ultima_demo_realizada   TIMESTAMPTZ,
    ultima_tarefa_tipo      VARCHAR(60),
    ultima_tarefa_dias      INT,
    dias_parado             INT,

    -- Flags (Sim/Não)
    previsao_preenchido     VARCHAR(10),
    ticket_preenchido       VARCHAR(10),
    lead_trabalhado         VARCHAR(10),
    lead_agendado           VARCHAR(10),
    tarefa_futura           INT,
    demo_agendada           VARCHAR(10),
    demo_realizada          VARCHAR(10)
);

CREATE INDEX IF NOT EXISTS idx_op_id              ON cliente_oportunidade(op_id);
CREATE INDEX IF NOT EXISTS idx_op_cnpj_contador   ON cliente_oportunidade(cnpj_contador);
CREATE INDEX IF NOT EXISTS idx_op_status          ON cliente_oportunidade(status);
CREATE INDEX IF NOT EXISTS idx_op_fase            ON cliente_oportunidade(fase);
CREATE INDEX IF NOT EXISTS idx_op_cnpj            ON cliente_oportunidade(cnpj);

-- ── TAREFAS DE CLIENTES ───────────────────────────────────────
-- Tabela truncada a cada upload de TAREFAS.

CREATE TABLE IF NOT EXISTS cliente_tarefa (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id               UUID REFERENCES cliente_upload(id) ON DELETE CASCADE,

    -- Identificação
    tarefa_id               BIGINT,                     -- Tarefa ID (origem)
    op_id                   BIGINT,                     -- FK lógica → cliente_oportunidade.op_id
    cnpj                    VARCHAR(20),
    razao_social            VARCHAR(200),

    -- Datas
    data_criacao            TIMESTAMPTZ,
    data_atualizacao        TIMESTAMPTZ,
    data_agendamento        TIMESTAMPTZ,

    -- Estado da oportunidade no momento
    fase_lead               VARCHAR(40),

    -- Tarefa em si
    status                  VARCHAR(20),                -- 'concluída' | 'pendente' | ...
    finalidade              VARCHAR(60),
    resultado               VARCHAR(60),
    origem_lead             VARCHAR(20),
    usuario_atribuido       VARCHAR(80),
    usuario_criador         VARCHAR(80),
    canal                   VARCHAR(20),                -- 'Telefone' | 'WhatsApp' | ...
    situacao_tarefa         VARCHAR(20),                -- 'Em dia' | 'Atrasada' | ...
    unidade                 VARCHAR(60)
);

CREATE INDEX IF NOT EXISTS idx_tarefa_op_id       ON cliente_tarefa(op_id);
CREATE INDEX IF NOT EXISTS idx_tarefa_cnpj        ON cliente_tarefa(cnpj);
CREATE INDEX IF NOT EXISTS idx_tarefa_status      ON cliente_tarefa(status);
CREATE INDEX IF NOT EXISTS idx_tarefa_situacao    ON cliente_tarefa(situacao_tarefa);
CREATE INDEX IF NOT EXISTS idx_tarefa_data_agend  ON cliente_tarefa(data_agendamento);
