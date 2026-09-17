-- ============================================================================
-- 013_monitor_metas.sql — as metas mensais do Monitor
-- ============================================================================
-- Aditiva e idempotente. Nenhum DROP, nenhum backfill: sem meta gravada o
-- painel mostra o resultado e o quadro sem carinha, que e o estado correto
-- de "ninguem definiu a meta ainda".
--
-- POR QUE UMA LINHA POR MES, E NAO UMA META FIXA POR INDICADOR
-- A meta muda de mes para mes (ferias, mes curto, campanha) e o painel de
-- setembro tem que continuar comparado com a meta DE SETEMBRO depois de
-- outubro comecar. Meta unica seria reescrita e apagaria o passado.
--
-- `indicador` e texto e nao FK para tabela de dominio: a lista de
-- indicadores mora em services/monitor.py, versionada com o codigo que sabe
-- calcular cada um. Uma tabela de dominio deixaria criar meta para um
-- indicador que o painel nao sabe medir.
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitor_metas (
    indicador        VARCHAR(40)  NOT NULL,
    ano              SMALLINT     NOT NULL,
    mes              SMALLINT     NOT NULL,
    -- NUMERIC e nao INTEGER: NMRR e ticket medio sao dinheiro, e % de
    -- no-show tem casa decimal.
    valor            NUMERIC(14,2) NOT NULL,
    atualizado_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (indicador, ano, mes),
    CONSTRAINT ck_monitor_meta_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT ck_monitor_meta_ano CHECK (ano BETWEEN 2020 AND 2100),
    -- Meta negativa nao existe; zero existe (indicador que este mes nao se
    -- cobra) e por isso nao e proibido.
    CONSTRAINT ck_monitor_meta_valor CHECK (valor >= 0)
);

-- A consulta do painel e sempre "as metas deste mes".
CREATE INDEX IF NOT EXISTS idx_monitor_metas_mes
    ON monitor_metas (ano, mes);
