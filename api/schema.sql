-- ============================================================
-- HIPO — Schema PostgreSQL
-- Módulos: POs + PEX (Fase 1 — fim de semana)
-- ============================================================

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE po_tipo_enum AS ENUM (
    'COMISSAO', 'INCENTIVO', 'REPASSE'
);

CREATE TYPE po_status_reconciliacao AS ENUM (
    'CONFORME', 'DIVERGENTE', 'AUSENTE', 'INESPERADO'
);

CREATE TYPE cromie_status_upload AS ENUM (
    'PROCESSADO', 'ERRO_SCHEMA', 'ERRO_PARSE'
);

CREATE TYPE pex_pilar_enum AS ENUM (
    'RESULTADO', 'GESTAO', 'ENGAJAMENTO'
);

CREATE TYPE risco_enum AS ENUM (
    'VERDE', 'AMARELO', 'LARANJA', 'VERMELHO'
);

-- ============================================================
-- MÓDULO: USUÁRIOS (base mínima para autenticação)
-- ============================================================

CREATE TABLE usuarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome            VARCHAR(150) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    senha_hash      TEXT NOT NULL,
    cargo           VARCHAR(80),   -- SDR, EC, EV, EP, ADM, GESTOR, FRANQUEADO
    ativo           BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- MÓDULO: BD ATIVADOS
-- Fonte: upload manual diário do ADM
-- ============================================================

CREATE TABLE bd_ativados_upload (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_upload     TIMESTAMPTZ DEFAULT NOW(),
    usuario_id      UUID REFERENCES usuarios(id),
    nome_arquivo    VARCHAR(200),
    total_registros INT,
    processado      BOOLEAN DEFAULT FALSE
);

CREATE TABLE bd_ativados (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id                   UUID REFERENCES bd_ativados_upload(id),
    -- Identificação
    referencia_aplicativo       VARCHAR(80) UNIQUE NOT NULL,  -- chave de join com POs
    razao_social                VARCHAR(200),
    cnpj                        VARCHAR(18),
    -- Status
    situacao                    VARCHAR(50),    -- ACTIVE, ARCHIVED, etc.
    saude_paciente              VARCHAR(50),
    -- Faturamento
    dia_faturamento             SMALLINT,
    vencimento                  SMALLINT,
    tipo_faturamento            VARCHAR(50),
    valor_mensalidade           NUMERIC(10,2),
    -- Uso do produto
    integracao_contabil         BOOLEAN DEFAULT FALSE,
    ultimo_acesso               DATE,
    -- Módulos ativos (flags)
    modulo_financeiro           BOOLEAN DEFAULT FALSE,
    modulo_nfe                  BOOLEAN DEFAULT FALSE,
    modulo_estoque              BOOLEAN DEFAULT FALSE,
    modulo_vendas               BOOLEAN DEFAULT FALSE,
    modulo_servicos             BOOLEAN DEFAULT FALSE,
    modulo_compras              BOOLEAN DEFAULT FALSE,
    -- Responsável interno
    ativado_por_email           VARCHAR(150),
    -- Contador de origem
    contador_cnpj               VARCHAR(18),
    contador_nome               VARCHAR(200),
    -- Datas
    data_ativacao               DATE,
    data_cancelamento           DATE,
    -- Colunas adicionais (as 3 últimas que foram acrescidas)
    coluna_extra_1              TEXT,
    coluna_extra_2              TEXT,
    coluna_extra_3              TEXT,
    -- Controle
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bd_ativados_ref ON bd_ativados(referencia_aplicativo);
CREATE INDEX idx_bd_ativados_situacao ON bd_ativados(situacao);
CREATE INDEX idx_bd_ativados_faturamento ON bd_ativados(dia_faturamento, vencimento);

-- ============================================================
-- MÓDULO: POs
-- ============================================================

-- Controle de uploads de PO
CREATE TABLE po_uploads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_upload     TIMESTAMPTZ DEFAULT NOW(),
    usuario_id      UUID REFERENCES usuarios(id),
    nome_arquivo    VARCHAR(200) NOT NULL,
    tipo            po_tipo_enum NOT NULL,
    tem_enabler     BOOLEAN DEFAULT FALSE,  -- TRUE quando é ComissaoV6Enabler
    semana_ref      DATE,                   -- domingo da semana de referência
    total_linhas    INT DEFAULT 0,
    processado      BOOLEAN DEFAULT FALSE,
    erro            TEXT
);

-- Linhas das POs
CREATE TABLE po_linhas (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id               UUID REFERENCES po_uploads(id) NOT NULL,
    tipo                    po_tipo_enum NOT NULL,
    tem_enabler             BOOLEAN DEFAULT FALSE,
    -- Identificação (comum a todos os tipos)
    referencia_aplicativo   VARCHAR(80) NOT NULL,
    razao_social            VARCHAR(200),
    cnpj                    VARCHAR(18),
    -- Financeiro
    valor_bruto             NUMERIC(12,2),
    valor_liquido           NUMERIC(12,2),
    impostos                NUMERIC(10,2),
    fundo_marketing         NUMERIC(10,2),   -- 2,5% deduzido na Comissão
    -- Específico COMISSAO
    plano                   VARCHAR(80),
    data_ativacao           DATE,
    -- Específico ENABLER (contador vinculado)
    contador_nome           VARCHAR(200),
    contador_cnpj           VARCHAR(18),
    comissao_contador       NUMERIC(10,2),
    -- Específico INCENTIVO
    ativado_por_email       VARCHAR(150),
    premio                  NUMERIC(10,2),
    -- Específico REPASSE
    parcela_numero          SMALLINT,        -- X de X/Y
    parcela_total           SMALLINT,        -- Y de X/Y
    ep_email                VARCHAR(150),    -- "Ativado Por"
    -- Reconciliação
    status_reconciliacao    po_status_reconciliacao,
    valor_esperado          NUMERIC(12,2),
    divergencia_valor       NUMERIC(12,2),   -- valor_liquido - valor_esperado
    observacao_reconciliacao TEXT,
    -- NFS-e
    nfse_emitida            BOOLEAN DEFAULT FALSE,
    nfse_numero             VARCHAR(40),
    nfse_data               TIMESTAMPTZ,
    -- Controle
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_po_linhas_ref ON po_linhas(referencia_aplicativo);
CREATE INDEX idx_po_linhas_upload ON po_linhas(upload_id);
CREATE INDEX idx_po_linhas_status ON po_linhas(status_reconciliacao);
CREATE INDEX idx_po_linhas_tipo ON po_linhas(tipo, tem_enabler);

-- Parcelas de repasse (calendário completo por cliente)
CREATE TABLE repasse_calendario (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referencia_aplicativo   VARCHAR(80) NOT NULL,
    razao_social            VARCHAR(200),
    ep_email                VARCHAR(150),
    total_parcelas          SMALLINT NOT NULL,
    valor_parcela           NUMERIC(10,2),
    -- Situação de cada parcela
    parcela_1_recebida      BOOLEAN DEFAULT FALSE,
    parcela_1_data          DATE,
    parcela_1_upload_id     UUID REFERENCES po_uploads(id),
    parcela_2_recebida      BOOLEAN DEFAULT FALSE,
    parcela_2_data          DATE,
    parcela_2_upload_id     UUID REFERENCES po_uploads(id),
    parcela_3_recebida      BOOLEAN DEFAULT FALSE,
    parcela_3_data          DATE,
    parcela_3_upload_id     UUID REFERENCES po_uploads(id),
    parcela_4_recebida      BOOLEAN DEFAULT FALSE,
    parcela_4_data          DATE,
    parcela_4_upload_id     UUID REFERENCES po_uploads(id),
    parcela_5_recebida      BOOLEAN DEFAULT FALSE,
    parcela_5_data          DATE,
    parcela_5_upload_id     UUID REFERENCES po_uploads(id),
    parcela_6_recebida      BOOLEAN DEFAULT FALSE,
    parcela_6_data          DATE,
    parcela_6_upload_id     UUID REFERENCES po_uploads(id),
    -- Controle
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_repasse_ref ON repasse_calendario(referencia_aplicativo);

-- Projeção semanal (gerada automaticamente pelo BD Ativados)
CREATE TABLE po_projecao_semanal (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    semana_ref              DATE NOT NULL,              -- domingo da semana
    referencia_aplicativo   VARCHAR(80) NOT NULL,
    razao_social            VARCHAR(200),
    tipo                    po_tipo_enum NOT NULL,
    valor_esperado          NUMERIC(12,2),
    dia_faturamento         SMALLINT,
    gerado_em               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(semana_ref, referencia_aplicativo, tipo)
);

CREATE INDEX idx_projecao_semana ON po_projecao_semanal(semana_ref);

-- ============================================================
-- MÓDULO: CROmie — Uploads e Auditoria de Schema
-- ============================================================

CREATE TABLE cromie_uploads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_upload     TIMESTAMPTZ DEFAULT NOW(),
    usuario_id      UUID REFERENCES usuarios(id),
    nome_arquivo    VARCHAR(200),
    status          cromie_status_upload DEFAULT 'PROCESSADO',
    -- Auditoria de schema (detecta mudanças de colunas)
    colunas_cliente_final       TEXT[],   -- colunas detectadas na aba
    colunas_tarefa_cliente      TEXT[],
    colunas_contador            TEXT[],
    colunas_tarefa_contador     TEXT[],
    -- Contagem de registros
    total_cliente_final         INT,
    total_tarefa_cliente        INT,
    total_contador              INT,
    total_tarefa_contador       INT,
    -- Alerta de mudança de schema
    schema_alterado             BOOLEAN DEFAULT FALSE,
    colunas_novas               TEXT[],   -- colunas que apareceram
    colunas_removidas           TEXT[],   -- colunas que sumiram
    erro                        TEXT
);

-- ============================================================
-- MÓDULO: CROmie — Dados das 4 abas
-- ============================================================

-- Aba: Cliente Final (leads/oportunidades)
CREATE TABLE cromie_cliente_final (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id                   UUID REFERENCES cromie_uploads(id),
    -- Identificação
    op_id                       VARCHAR(80),   -- ID da oportunidade no CROmie
    empresa                     VARCHAR(200),
    cnpj                        VARCHAR(18),
    responsavel                 VARCHAR(150),
    -- Pipeline
    fase                        VARCHAR(80),   -- Suspect, Cadência, Qualificação, etc.
    temperatura                 VARCHAR(50),
    origem                      VARCHAR(50),   -- INBOUND, OUTBOUND, INDICACAO
    -- Flags de compliance (já vêm prontos na extração)
    tarefa_futura               BOOLEAN DEFAULT FALSE,
    temperatura_preenchida      BOOLEAN DEFAULT FALSE,
    previsao_preenchida         BOOLEAN DEFAULT FALSE,
    ticket_preenchido           BOOLEAN DEFAULT FALSE,
    demo_realizada              BOOLEAN DEFAULT FALSE,
    -- Valores
    ticket                      NUMERIC(10,2),
    previsao_fechamento         DATE,
    -- Responsável
    usuario_responsavel         VARCHAR(150),
    -- Contador de origem
    contador_cnpj               VARCHAR(18),
    contador_nome               VARCHAR(200),
    -- Datas
    data_criacao                DATE,
    data_ganho                  DATE,
    data_perda                  DATE,
    motivo_perda                TEXT,
    -- Controle
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cf_upload ON cromie_cliente_final(upload_id);
CREATE INDEX idx_cf_fase ON cromie_cliente_final(fase);
CREATE INDEX idx_cf_usuario ON cromie_cliente_final(usuario_responsavel);
CREATE INDEX idx_cf_data_criacao ON cromie_cliente_final(data_criacao);

-- Aba: Tarefa Cliente
CREATE TABLE cromie_tarefa_cliente (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id           UUID REFERENCES cromie_uploads(id),
    op_id               VARCHAR(80),
    empresa             VARCHAR(200),
    tipo_tarefa         VARCHAR(80),    -- Reunião, Registro, etc.
    finalidade          VARCHAR(80),    -- Online, Presencial, Apresentação, etc.
    resultado           VARCHAR(80),    -- Sucesso, Realizado, Efetuado, etc.
    canal               VARCHAR(50),
    usuario_responsavel VARCHAR(150),
    data_tarefa         DATE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tc_upload ON cromie_tarefa_cliente(upload_id);
CREATE INDEX idx_tc_usuario ON cromie_tarefa_cliente(usuario_responsavel);
CREATE INDEX idx_tc_data ON cromie_tarefa_cliente(data_tarefa);
CREATE INDEX idx_tc_tipo_resultado ON cromie_tarefa_cliente(tipo_tarefa, resultado, finalidade);

-- Aba: Contador
CREATE TABLE cromie_contador (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id           UUID REFERENCES cromie_uploads(id),
    cnpj                VARCHAR(18),
    razao_social        VARCHAR(200),
    responsavel         VARCHAR(150),
    status_parceria     VARCHAR(80),
    temperatura         VARCHAR(50),
    dias_parado         INT,
    possui_tarefa       BOOLEAN DEFAULT FALSE,
    status_tarefa       VARCHAR(80),
    sow_preenchido      BOOLEAN DEFAULT FALSE,
    usuario_responsavel VARCHAR(150),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cnt_upload ON cromie_contador(upload_id);
CREATE INDEX idx_cnt_usuario ON cromie_contador(usuario_responsavel);
CREATE INDEX idx_cnt_sow ON cromie_contador(sow_preenchido);

-- Aba: Tarefa Contador
CREATE TABLE cromie_tarefa_contador (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id           UUID REFERENCES cromie_uploads(id),
    contador_cnpj       VARCHAR(18),
    contador_nome       VARCHAR(200),
    tipo_tarefa         VARCHAR(80),
    finalidade          VARCHAR(80),
    resultado           VARCHAR(80),
    canal               VARCHAR(50),
    usuario_responsavel VARCHAR(150),
    data_tarefa         DATE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tco_upload ON cromie_tarefa_contador(upload_id);
CREATE INDEX idx_tco_usuario ON cromie_tarefa_contador(usuario_responsavel);
CREATE INDEX idx_tco_data ON cromie_tarefa_contador(data_tarefa);

-- ============================================================
-- MÓDULO: PEX — Snapshots de Indicadores
-- ============================================================

-- Configuração dos indicadores (alimentada manualmente ou por setup)
CREATE TABLE pex_indicadores_config (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(50) UNIQUE NOT NULL,  -- ex: 'NMRR', 'REUNIOES_EC_DU'
    nome            VARCHAR(150) NOT NULL,
    pilar           pex_pilar_enum NOT NULL,
    pontos_max      NUMERIC(5,2) NOT NULL,
    meta_valor      NUMERIC(10,4),
    meta_descricao  VARCHAR(200),
    fonte           VARCHAR(200),  -- de onde vem o dado
    ativo           BOOLEAN DEFAULT TRUE
);

-- Snapshot diário dos indicadores calculados
CREATE TABLE pex_snapshot (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_ref        DATE NOT NULL,
    mes_ref         CHAR(7) NOT NULL,  -- formato YYYY-MM
    upload_cromie_id UUID REFERENCES cromie_uploads(id),
    -- Pilar Resultado (calculados pelo CROmie)
    nmrr_realizado              NUMERIC(12,2),
    nmrr_meta                   NUMERIC(12,2),
    nmrr_pct                    NUMERIC(5,2),
    nmrr_pts                    NUMERIC(4,2),
    reunioes_ec_du_realizado    NUMERIC(5,2),
    reunioes_ec_du_pts          NUMERIC(4,2),
    contadores_trabalhados_pct  NUMERIC(5,2),
    contadores_trabalhados_pts  NUMERIC(4,2),
    contadores_indicando_pct    NUMERIC(5,2),
    contadores_indicando_pts    NUMERIC(4,2),
    contadores_ativando_pct     NUMERIC(5,2),
    contadores_ativando_pts     NUMERIC(4,2),
    conversao_total_pct         NUMERIC(5,2),
    conversao_total_pts         NUMERIC(4,2),
    conversao_m0_pct            NUMERIC(5,2),
    conversao_m0_pts            NUMERIC(4,2),
    conversao_inbound_pct       NUMERIC(5,2),
    conversao_inbound_pts       NUMERIC(4,2),
    demo_du_realizado           NUMERIC(5,2),
    demo_du_pts                 NUMERIC(4,2),
    demos_outbound_pct          NUMERIC(5,2),
    demos_outbound_pts          NUMERIC(4,2),
    sow_pct                     NUMERIC(5,2),
    sow_pts                     NUMERIC(4,2),
    mapeamento_carteira_pct     NUMERIC(5,2),
    mapeamento_carteira_pts     NUMERIC(4,2),
    reuniao_contador_inbound_pct NUMERIC(5,2),
    reuniao_contador_inbound_pts NUMERIC(4,2),
    integracao_contabil_pct     NUMERIC(5,2),
    integracao_contabil_pts     NUMERIC(4,2),
    -- Calculados pelo BD Ativados + POs
    early_churn_pct             NUMERIC(5,2),
    early_churn_pts             NUMERIC(4,2),
    crescimento_40_pct          NUMERIC(5,2),
    crescimento_40_pts          NUMERIC(4,2),
    -- Lançamento manual EV
    utilizacao_desconto_pct     NUMERIC(5,2),
    utilizacao_desconto_pts     NUMERIC(4,2),
    -- Totais
    total_resultado_pts         NUMERIC(5,2),
    total_gestao_pts            NUMERIC(5,2),
    total_engajamento_pts       NUMERIC(5,2),
    total_geral_pts             NUMERIC(5,2),
    risco_classificacao         risco_enum,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(data_ref)
);

CREATE INDEX idx_pex_mes ON pex_snapshot(mes_ref);

-- Gaps de compliance por usuário (double-check CROmie)
CREATE TABLE pex_compliance_gaps (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID REFERENCES pex_snapshot(id),
    data_ref            DATE NOT NULL,
    usuario_responsavel VARCHAR(150) NOT NULL,
    -- Gaps identificados
    leads_sem_tarefa_futura     INT DEFAULT 0,
    leads_sem_temperatura       INT DEFAULT 0,
    leads_sem_previsao          INT DEFAULT 0,
    leads_sem_ticket            INT DEFAULT 0,
    contadores_sem_tarefa_mes   INT DEFAULT 0,
    inbound_sem_reuniao_5du     INT DEFAULT 0,
    -- Pontos em risco por usuário
    pontos_em_risco             NUMERIC(4,2),
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gaps_usuario ON pex_compliance_gaps(usuario_responsavel, data_ref);

-- Configuração de metas mensais (ADM preenche no início de cada mês)
CREATE TABLE pex_metas_mensais (
    id              SERIAL PRIMARY KEY,
    mes_ref         CHAR(7) NOT NULL,  -- YYYY-MM
    nmrr_meta       NUMERIC(12,2),
    demos_outbound_meta INT,
    big3_descricao  TEXT,
    dias_uteis      SMALLINT,
    ecs_ativos_m3   SMALLINT,          -- ECs com 3+ meses de rampagem
    evs_ativos      SMALLINT,
    carteira_total_contadores INT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mes_ref)
);

-- ============================================================
-- VIEWS ESTRATÉGICAS
-- ============================================================

-- View: Resumo PEX do mês atual
CREATE OR REPLACE VIEW vw_pex_mes_atual AS
SELECT
    s.mes_ref,
    s.data_ref AS ultima_atualizacao,
    s.total_resultado_pts,
    s.total_gestao_pts,
    s.total_engajamento_pts,
    s.total_geral_pts,
    s.risco_classificacao,
    CASE
        WHEN s.total_geral_pts >= 95 THEN 'Franquia Excelente'
        WHEN s.total_geral_pts >= 76 THEN 'Franquia Certificada'
        WHEN s.total_geral_pts >= 60 THEN 'Franquia Qualificada'
        WHEN s.total_geral_pts >= 50 THEN 'Franquia Aderente'
        WHEN s.total_geral_pts >= 36 THEN 'Franquia em Desenvolvimento'
        ELSE 'Franquia Não Aderente'
    END AS classificacao
FROM pex_snapshot s
WHERE s.mes_ref = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
ORDER BY s.data_ref DESC
LIMIT 1;

-- View: Reconciliação semanal mais recente
CREATE OR REPLACE VIEW vw_reconciliacao_atual AS
SELECT
    pl.tipo,
    pl.tem_enabler,
    pl.status_reconciliacao,
    COUNT(*) AS quantidade,
    SUM(pl.valor_liquido) AS valor_total,
    SUM(pl.divergencia_valor) AS divergencia_total
FROM po_linhas pl
JOIN po_uploads pu ON pu.id = pl.upload_id
WHERE pu.semana_ref = (
    SELECT MAX(semana_ref) FROM po_uploads WHERE processado = TRUE
)
GROUP BY pl.tipo, pl.tem_enabler, pl.status_reconciliacao;

-- View: Clientes ausentes na última semana
CREATE OR REPLACE VIEW vw_po_ausentes AS
SELECT
    p.semana_ref,
    p.referencia_aplicativo,
    p.razao_social,
    p.tipo,
    p.valor_esperado,
    ba.situacao,
    ba.saude_paciente,
    ba.contador_nome
FROM po_projecao_semanal p
LEFT JOIN po_linhas pl ON pl.referencia_aplicativo = p.referencia_aplicativo
    AND pl.upload_id IN (
        SELECT id FROM po_uploads WHERE semana_ref = p.semana_ref
    )
JOIN bd_ativados ba ON ba.referencia_aplicativo = p.referencia_aplicativo
WHERE p.semana_ref = (SELECT MAX(semana_ref) FROM po_projecao_semanal)
  AND pl.id IS NULL;

-- View: Compliance por usuário (hoje)
CREATE OR REPLACE VIEW vw_compliance_usuarios AS
SELECT
    g.usuario_responsavel,
    g.leads_sem_tarefa_futura,
    g.leads_sem_temperatura,
    g.leads_sem_previsao,
    g.leads_sem_ticket,
    g.contadores_sem_tarefa_mes,
    g.inbound_sem_reuniao_5du,
    g.pontos_em_risco
FROM pex_compliance_gaps g
WHERE g.data_ref = CURRENT_DATE
ORDER BY g.pontos_em_risco DESC;

-- ============================================================
-- DADOS INICIAIS
-- ============================================================

-- Configuração dos indicadores PEX
INSERT INTO pex_indicadores_config
    (codigo, nome, pilar, pontos_max, meta_valor, meta_descricao, fonte)
VALUES
    -- Pilar Resultado
    ('NMRR',                    'NMRR',                                 'RESULTADO', 10,   1.00,  '100% do NMRR projetado',          'CROmie — Cliente Final'),
    ('REUNIOES_EC_DU',          'Reuniões por EC/dia útil',             'RESULTADO',  3,   4.00,  '4 reuniões/EC/DU',                'CROmie — Tarefa Contador'),
    ('CONTADORES_TRABALHADOS',  'Contadores Trabalhados',               'RESULTADO',  2,   0.90,  '90% da carteira',                 'CROmie — Tarefa Contador'),
    ('CONTADORES_INDICANDO',    'Contadores Indicando',                 'RESULTADO',  3,   0.25,  '25% da carteira',                 'CROmie — Cliente Final'),
    ('CONTADORES_ATIVANDO',     'Contadores Ativando',                  'RESULTADO',  4,   0.08,  '8% da carteira',                  'BD Ativados'),
    ('CONVERSAO_TOTAL',         'Conversão Total de Leads',             'RESULTADO',  4,   0.35,  '35% de conversão',                'CROmie — Cliente Final'),
    ('CONVERSAO_M0',            'Conversão de Leads no M0',             'RESULTADO',  3,   0.20,  '20% no mesmo mês',                'CROmie — Cliente Final'),
    ('CONVERSAO_INBOUND',       'Conversão Total de Leads Inbound',     'RESULTADO',  2,   0.45,  '45% dos inbounds',                'CROmie — Cliente Final'),
    ('DEMO_DU',                 'Apresentação (demo) por dia útil',     'RESULTADO',  4,   4.00,  '4 demos/EV/DU',                   'CROmie — Tarefa Cliente'),
    ('DEMOS_OUTBOUND',          'Número de demos Outbound',             'RESULTADO',  3,   1.00,  '100% da meta mensal',             'CROmie — Tarefa Cliente'),
    ('SOW',                     'Share of Wallet',                      'RESULTADO',  3,   0.05,  '5% dos clientes mapeados',        'CROmie — Contador'),
    ('MAPEAMENTO_CARTEIRA',     'Mapeamento de Carteira',               'RESULTADO',  2,   0.60,  '60% com SOW preenchido',          'CROmie — Contador'),
    ('REUNIAO_CONTADOR_INBOUND','Reunião c/ Contador dos Leads Inbound','RESULTADO',  4,   0.80,  '80% em até 5DU',                  'CROmie — Tarefa Contador'),
    ('INTEGRACAO_CONTABIL',     'Integração Contábil',                  'RESULTADO',  3,   1.00,  '8 chamados/mês (cluster Platina)','CROmie — Tarefa Contador'),
    ('EARLY_CHURN',             'Early Churn',                          'RESULTADO',  3,   0.057, '<= 5,7%',                         'BD Ativados + POs'),
    ('CRESCIMENTO_40',          'Crescimento de 40%',                   'RESULTADO',  5,   0.40,  '40% YoY ARR',                     'POs históricas'),
    ('UTILIZACAO_DESCONTO',     'Utilização de Cupom de Desconto',      'RESULTADO',  2,   0.15,  '<= 15% do NMRR potencial',        'Lançamento manual EV'),
    -- Pilar Gestão
    ('REMUNERACAO_VARIAVEL',    'Aderência ao Modelo de Remuneração Variável', 'GESTAO', 2, NULL, 'Sim/Não', 'Lançamento ADM'),
    ('USO_CROMIE',              'Utilização correta do CROmie',         'GESTAO',     2,   1.00,  '100%',                            'Double-check automático'),
    ('GESTAO_QUARTIS',          'Adesão à Gestão dos Quartis',          'GESTAO',     4,   0.80,  '80% Q1/Q2',                       'Módulo RH + benchmark Omie'),
    ('HEADCOUNT',               'Adesão ao Headcount Recomendado',      'GESTAO',     3,   1.00,  '100%',                            'Módulo RH'),
    ('POLITICA_CONTRATACAO',    'Política de Contratação e Remuneração','GESTAO',     3,   1.00,  '100%',                            'Módulo RH'),
    ('TRILHAS_UC',              'Conclusão das Trilhas Obrigatórias UC', 'GESTAO',    2,   1.00,  '100%',                            'Lançamento ADM'),
    ('TURNOVER',                'Turnover Voluntário',                  'GESTAO',     4,   0.00,  '0%',                              'Módulo RH'),
    -- Pilar Engajamento
    ('PARTICIPACAO_TREINAMENTOS','Participação em Treinamentos/Reuniões','ENGAJAMENTO',4,  0.90,  '90%',                             'Módulo Marketing'),
    ('LEITURA_YUNGAS',          'Leitura dos Informes na Yungas',       'ENGAJAMENTO',3,  1.00,  '100%',                            'Lançamento ADM'),
    ('VERBA_COOPERADA',         'Utilização Verba Cooperada',           'ENGAJAMENTO',2,  NULL,  'Pro rata semestral',              'Módulo Marketing'),
    ('MIDIAS_SOCIAIS',          'Mídias Sociais — Instagram',           'ENGAJAMENTO',2,  NULL,  'Sim/Não',                         'Lançamento ADM'),
    ('BIG3',                    'BIG 3 — Ações Mensais',                'ENGAJAMENTO',6,  3.00,  '3 ações atingidas',               'Módulo Marketing'),
    ('REALIZACAO_EVENTOS',      'Realização de Eventos',                'ENGAJAMENTO',3,  1.00,  'Meta por cluster (Platina: 5/mês)','Módulo Marketing');
