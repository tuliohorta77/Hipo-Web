-- =============================================================================
-- HIPO v1.4.0 - Etapa 1: fundacao do modulo Painel Gerencial (CORRIGIDA)
-- =============================================================================
-- Idempotente: usa CREATE TABLE IF NOT EXISTS em todas as tabelas. Roda
-- limpo mesmo apos a tentativa parcial anterior (painel_kpi_config e
-- painel_snapshot ja foram criadas; este script cria as 2 que faltaram).
--
-- Cria:
--   - painel_kpi_config  (catalogo de KPIs, 10 linhas via seed)
--   - painel_meta_mensal (meta por KPI por mes, input do Gerente/Franqueado)
--   - painel_snapshot    (ultimo valor de cada KPI vindo da bridge ou HIPO)
--   - dia_nao_util       (feriados, pontos facultativos, dias descontados)
--
-- Correcoes em relacao a versao anterior:
--   - REFERENCES usuarios (plural) em vez de usuario
--   - Tipo UUID em criado_por_usuario_id (era INTEGER) para casar com usuarios.id
-- =============================================================================

CREATE TABLE IF NOT EXISTS painel_kpi_config (
    codigo              TEXT PRIMARY KEY,
    nome                TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN ('cumulativo', 'media', 'taxa_invertida')),
    polaridade          TEXT NOT NULL CHECK (polaridade IN ('maior', 'menor')),
    ordem               INTEGER NOT NULL,
    icone               TEXT NOT NULL,
    cor_hex             TEXT NOT NULL,
    fonte               TEXT NOT NULL CHECK (fonte IN ('bridge', 'hipo')),
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_painel_kpi_config_ordem
    ON painel_kpi_config (ordem)
    WHERE ativo = TRUE;


CREATE TABLE IF NOT EXISTS painel_meta_mensal (
    id                      SERIAL PRIMARY KEY,
    kpi_codigo              TEXT NOT NULL REFERENCES painel_kpi_config (codigo) ON DELETE CASCADE,
    mes_competencia         DATE NOT NULL,
    meta_valor              NUMERIC(18, 4) NOT NULL,
    criado_por_usuario_id   UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT painel_meta_mensal_unica UNIQUE (kpi_codigo, mes_competencia),
    CONSTRAINT painel_meta_competencia_primeiro_dia CHECK (EXTRACT(DAY FROM mes_competencia) = 1)
);

CREATE INDEX IF NOT EXISTS idx_painel_meta_mensal_competencia
    ON painel_meta_mensal (mes_competencia);


CREATE TABLE IF NOT EXISTS painel_snapshot (
    kpi_codigo      TEXT PRIMARY KEY REFERENCES painel_kpi_config (codigo) ON DELETE CASCADE,
    valor           NUMERIC(18, 4) NOT NULL,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS dia_nao_util (
    id                      SERIAL PRIMARY KEY,
    data                    DATE NOT NULL UNIQUE,
    motivo                  TEXT NOT NULL,
    criado_por_usuario_id   UUID REFERENCES usuarios (id) ON DELETE SET NULL,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dia_nao_util_ano
    ON dia_nao_util (EXTRACT(YEAR FROM data));
