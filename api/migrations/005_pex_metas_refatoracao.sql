-- ============================================================
-- HIPO — Migration 005: Refatoração de pex_metas_mensais
--   - Cria pex_metas_cabecalho (1 linha por mês, dados globais)
--   - Cria pex_metas_indicadores (1 linha por mês × indicador)
--   - Cria pex_metas_big3 (1 linha por mês × ação Big3)
--   - Migra dados existentes da tabela antiga
--   - PRESERVA pex_metas_mensais como view de compatibilidade pro pex_calc.py
-- ============================================================

BEGIN;

-- ─── Cabeçalho do mês (configuração global) ───
CREATE TABLE IF NOT EXISTS pex_metas_cabecalho (
    id              SERIAL PRIMARY KEY,
    mes_ref         CHAR(7) NOT NULL UNIQUE,  -- YYYY-MM
    cluster_unidade VARCHAR(30) NOT NULL DEFAULT 'BASE',
        -- INCUBADORA, AVANCA_PLUS, BASE, OURO, PLATINA, PRIME, BLACK
    dias_uteis      SMALLINT NOT NULL DEFAULT 22,
    ecs_ativos_m3   SMALLINT NOT NULL DEFAULT 0,  -- Executivos comerciais ≥3 meses
    evs_ativos      SMALLINT NOT NULL DEFAULT 0,  -- Especialistas de venda
    carteira_total_contadores INT NOT NULL DEFAULT 0,
    apps_ativos     INT NOT NULL DEFAULT 0,       -- denominador do SoW
    headcount_recomendado SMALLINT,                -- meta de headcount por cluster
    criado_por      UUID REFERENCES usuarios(id),
    criado_em       TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pex_metas_cab_mes ON pex_metas_cabecalho(mes_ref DESC);

-- ─── Meta numérica por indicador (1 linha por mês × indicador) ───
CREATE TABLE IF NOT EXISTS pex_metas_indicadores (
    id              SERIAL PRIMARY KEY,
    cabecalho_id    INT NOT NULL REFERENCES pex_metas_cabecalho(id) ON DELETE CASCADE,
    codigo          VARCHAR(40) NOT NULL,
        -- nmrr, demos_outbound, integracao_contabil, eventos, big3, etc.
    meta_valor      NUMERIC(14,2),
    UNIQUE (cabecalho_id, codigo)
);

CREATE INDEX IF NOT EXISTS ix_pex_metas_ind_codigo ON pex_metas_indicadores(codigo);

-- ─── Big3: 3 ações por mês com descrição + atingimento ───
CREATE TABLE IF NOT EXISTS pex_metas_big3 (
    id              SERIAL PRIMARY KEY,
    cabecalho_id    INT NOT NULL REFERENCES pex_metas_cabecalho(id) ON DELETE CASCADE,
    ordem           SMALLINT NOT NULL CHECK (ordem BETWEEN 1 AND 3),
    descricao       TEXT,
    atingiu         BOOLEAN DEFAULT FALSE,
    UNIQUE (cabecalho_id, ordem)
);

-- ─── Migrar dados existentes da pex_metas_mensais antiga ───
DO $$
DECLARE
    rec RECORD;
    cab_id INT;
BEGIN
    -- Copia cada linha existente pro novo modelo
    FOR rec IN SELECT * FROM pex_metas_mensais LOOP
        -- Cabeçalho
        INSERT INTO pex_metas_cabecalho (
            mes_ref, dias_uteis, ecs_ativos_m3, evs_ativos,
            carteira_total_contadores
        ) VALUES (
            rec.mes_ref,
            COALESCE(rec.dias_uteis, 22),
            COALESCE(rec.ecs_ativos_m3, 0),
            COALESCE(rec.evs_ativos, 0),
            COALESCE(rec.carteira_total_contadores, 0)
        )
        ON CONFLICT (mes_ref) DO UPDATE SET
            dias_uteis = EXCLUDED.dias_uteis,
            ecs_ativos_m3 = EXCLUDED.ecs_ativos_m3,
            evs_ativos = EXCLUDED.evs_ativos,
            carteira_total_contadores = EXCLUDED.carteira_total_contadores
        RETURNING id INTO cab_id;

        -- Metas numéricas que existiam (NMRR, Demos)
        IF rec.nmrr_meta IS NOT NULL THEN
            INSERT INTO pex_metas_indicadores (cabecalho_id, codigo, meta_valor)
            VALUES (cab_id, 'nmrr', rec.nmrr_meta)
            ON CONFLICT (cabecalho_id, codigo) DO UPDATE SET meta_valor = EXCLUDED.meta_valor;
        END IF;

        IF rec.demos_outbound_meta IS NOT NULL THEN
            INSERT INTO pex_metas_indicadores (cabecalho_id, codigo, meta_valor)
            VALUES (cab_id, 'demos_outbound', rec.demos_outbound_meta)
            ON CONFLICT (cabecalho_id, codigo) DO UPDATE SET meta_valor = EXCLUDED.meta_valor;
        END IF;

        -- Big3 antigo era texto único: deixamos como ação 1, ordem 2 e 3 vazias
        IF rec.big3_descricao IS NOT NULL AND TRIM(rec.big3_descricao) <> '' THEN
            INSERT INTO pex_metas_big3 (cabecalho_id, ordem, descricao)
            VALUES (cab_id, 1, rec.big3_descricao)
            ON CONFLICT (cabecalho_id, ordem) DO UPDATE SET descricao = EXCLUDED.descricao;
        END IF;
    END LOOP;
END $$;

-- ─── Recriar pex_metas_mensais como VIEW de compatibilidade ───
-- Assim o pex_calc.py continua lendo do mesmo nome até a gente refatorar.
DROP TABLE IF EXISTS pex_metas_mensais CASCADE;

CREATE VIEW pex_metas_mensais AS
SELECT
    cab.id,
    cab.mes_ref,
    (SELECT meta_valor FROM pex_metas_indicadores
        WHERE cabecalho_id = cab.id AND codigo = 'nmrr') AS nmrr_meta,
    (SELECT meta_valor::INT FROM pex_metas_indicadores
        WHERE cabecalho_id = cab.id AND codigo = 'demos_outbound') AS demos_outbound_meta,
    (SELECT descricao FROM pex_metas_big3
        WHERE cabecalho_id = cab.id AND ordem = 1) AS big3_descricao,
    cab.dias_uteis,
    cab.ecs_ativos_m3,
    cab.evs_ativos,
    cab.carteira_total_contadores,
    cab.criado_em AS created_at
FROM pex_metas_cabecalho cab;

COMMIT;
