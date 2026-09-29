-- =====================================================================
-- HIPO -- 018_metas_comerciais.sql
--
-- Metas do RPeR (Reuniao de Planejamento e Resultados): a meta de cada
-- SQUAD (SDR, EV, EC) e a meta de cada PESSOA, por mes.
--
-- POR QUE NAO REAPROVEITAR `monitor_metas`
--   `monitor_metas` e a meta da PAREDE: dez quadros da operacao inteira,
--   sem dono. O RPeR cobra por squad e por pessoa, com indicadores que o
--   Monitor nao tem (tarefas de prospeccao, contas prospectadas,
--   propostas, contas sob gestao...). Misturar as duas coisas faria a TV
--   mostrar uma meta que ninguem lancou para ela.
--
-- POR QUE A META DO SQUAD E GUARDADA, E NAO SOMADA
--   Decisao do Tulio (29/09): "nem sempre a meta do squad e a somatoria
--   da meta do time". Pessoa em ferias, rampa de quem entrou, vaga aberta
--   que o squad cobre -- a meta do squad e uma escolha, nao uma conta.
--   Por isso cada linha diz de quem ela e: `usuario_id` NULL e a meta do
--   squad; preenchido e a meta daquela pessoa DENTRO daquele squad.
--
-- `indicador` E TEXTO, NAO FK. Mesma escolha de `monitor_metas`: a lista
-- de indicadores de cada squad mora em services/rper.py, versionada com o
-- codigo que sabe calcular cada um. Uma tabela de dominio deixaria criar
-- meta para um indicador que o RPeR nao sabe medir. A API valida.
--
-- DUAS UNICIDADES PARCIAIS, e nao uma com COALESCE: o ON CONFLICT da API
-- aponta para a certa pelo predicado (usuario_id IS NULL / IS NOT NULL),
-- e o indice fica legivel para quem vier depois.
--
-- ON DELETE CASCADE na pessoa: meta de quem foi apagado nao tem a quem
-- cobrar. (Usuario que sai e desativado, nao apagado -- as metas dele e o
-- historico do RPeR ficam.)
--
-- ADITIVA E IDEMPOTENTE: uma tabela e tres indices novos. Nenhum DROP,
-- nenhum DELETE, nenhuma coluna alterada. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS metas_comerciais (
    id              BIGSERIAL PRIMARY KEY,
    squad           VARCHAR(3)    NOT NULL,
    usuario_id      UUID REFERENCES usuarios(id) ON DELETE CASCADE,
    indicador       VARCHAR(40)   NOT NULL,
    ano             SMALLINT      NOT NULL,
    mes             SMALLINT      NOT NULL,
    -- NUMERIC: NMRR e pipeline sao dinheiro, % de no-show tem decimal.
    valor           NUMERIC(14,2) NOT NULL,
    atualizado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_meta_com_squad CHECK (squad IN ('SDR', 'EV', 'EC')),
    CONSTRAINT ck_meta_com_mes   CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT ck_meta_com_ano   CHECK (ano BETWEEN 2020 AND 2100),
    -- Zero existe (indicador que este mes nao se cobra); negativo nao.
    CONSTRAINT ck_meta_com_valor CHECK (valor >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_com_squad
    ON metas_comerciais (squad, indicador, ano, mes)
    WHERE usuario_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_com_pessoa
    ON metas_comerciais (squad, usuario_id, indicador, ano, mes)
    WHERE usuario_id IS NOT NULL;

-- A consulta e sempre "as metas deste mes".
CREATE INDEX IF NOT EXISTS idx_meta_com_mes
    ON metas_comerciais (ano, mes);
