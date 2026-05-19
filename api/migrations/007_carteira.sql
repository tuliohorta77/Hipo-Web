-- ============================================================
-- HIPO — Migration 007: Módulo Carteira (Hunter / Farmer / Outros)
--
-- Suporta gestão de carteira de prospecção (Hunter) e relacionamento
-- com contadores parceiros (Farmer). Os dados vêm de dois uploads
-- diários (carteira + tarefas) e são reagrupados por
-- ID Grupo de Empresas filtrando Tipo Cnae = 'CNAE Contábil'.
--
-- Snapshot: cada upload SUBSTITUI o anterior (mesmo padrão do BD Ativados).
-- ============================================================

-- ── ENUMS ─────────────────────────────────────────────────────

CREATE TYPE carteira_funcao_enum AS ENUM (
    'EC_HUNTER',
    'EC_FARMER',
    'OUTROS'
);

CREATE TYPE tarefa_situacao_enum AS ENUM (
    'EM_DIA',
    'FUTURA',
    'ATRASADA',
    'DESCONHECIDA'
);

-- ── COLABORADORES ─────────────────────────────────────────────
-- Lista mestre extraída da carteira. A função é configurada
-- manualmente pelo ADM no modal de configuração (não vem da planilha).

CREATE TABLE carteira_colaborador (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome            VARCHAR(150) UNIQUE NOT NULL,
    funcao          carteira_funcao_enum NOT NULL DEFAULT 'OUTROS',
    funcao_origem   VARCHAR(120),  -- texto bruto da coluna "Função" (referência)
    ativo           BOOLEAN DEFAULT TRUE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_colaborador_funcao ON carteira_colaborador(funcao);

-- ── UPLOADS ───────────────────────────────────────────────────

CREATE TABLE carteira_upload (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo            VARCHAR(20) NOT NULL,  -- 'CARTEIRA' ou 'TAREFAS'
    data_upload     TIMESTAMPTZ DEFAULT NOW(),
    usuario_id      UUID REFERENCES usuarios(id),
    nome_arquivo    VARCHAR(200),
    total_linhas    INT,
    total_validos   INT,
    processado      BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_carteira_upload_tipo_data ON carteira_upload(tipo, data_upload DESC);

-- ── CNPJS DA CARTEIRA ─────────────────────────────────────────
-- Cada linha = um CNPJ filtrado por Tipo Cnae = 'CNAE Contábil'.
-- A tabela é truncada a cada upload (snapshot).

CREATE TABLE carteira_cnpj (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id           UUID REFERENCES carteira_upload(id) ON DELETE CASCADE,
    id_grupo            VARCHAR(50) NOT NULL,
    nome_grupo          VARCHAR(255),
    cnpj_contador       VARCHAR(20),
    contabilidade       VARCHAR(255),
    bairro              VARCHAR(120),
    cidade_uf           VARCHAR(120),
    parceria            VARCHAR(40),               -- 'Parceiro' / 'Não Parceiro'
    data_parceria       DATE,
    tipo_cnae           VARCHAR(40),
    colaborador_nome    VARCHAR(150),
    funcao_origem       VARCHAR(120),
    porte_faturamento   VARCHAR(60),
    score_rfm           VARCHAR(60),
    apps_ativos         INT,
    mrr_ativo           NUMERIC(12,2),
    leads_no_mes        INT,
    status_rf           VARCHAR(60)
);

CREATE INDEX idx_carteira_cnpj_grupo ON carteira_cnpj(id_grupo);
CREATE INDEX idx_carteira_cnpj_colaborador ON carteira_cnpj(colaborador_nome);

-- ── TAREFAS ──────────────────────────────────────────────────
-- Tabela truncada a cada upload de tarefas.

CREATE TABLE carteira_tarefa (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id           UUID REFERENCES carteira_upload(id) ON DELETE CASCADE,
    tarefa_id_origem    VARCHAR(60),
    cnpj_contador       VARCHAR(20),
    contabilidade       VARCHAR(255),
    executivo_nome      VARCHAR(150),
    situacao            tarefa_situacao_enum NOT NULL DEFAULT 'DESCONHECIDA',
    status              VARCHAR(40),
    tarefa_canal        VARCHAR(60),
    tipo_tarefa         VARCHAR(80),
    resultado           VARCHAR(80),
    data_criacao        TIMESTAMPTZ,
    data_agendamento    TIMESTAMPTZ,
    -- Data efetiva usada para checagem da meta semanal/mensal:
    -- Data Agendamento se existir; senão Data Criação.
    data_efetiva        TIMESTAMPTZ
);

CREATE INDEX idx_carteira_tarefa_cnpj      ON carteira_tarefa(cnpj_contador);
CREATE INDEX idx_carteira_tarefa_executivo ON carteira_tarefa(executivo_nome);
CREATE INDEX idx_carteira_tarefa_data_ef   ON carteira_tarefa(data_efetiva);
CREATE INDEX idx_carteira_tarefa_canal     ON carteira_tarefa(tarefa_canal);
