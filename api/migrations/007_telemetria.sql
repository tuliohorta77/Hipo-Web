-- =====================================================================
-- HIPO -- 007_telemetria.sql
--
-- Telemetria de uso + fechamento diario.
--
-- POR QUE UMA TABELA DE REQUESTS E NAO SO EVENTOS DE NEGOCIO
--   A trilha que ja existe (oportunidade_eventos, parceiro_eventos,
--   tarefas) responde "o que mudou". Ela nao responde "quem abriu o
--   sistema e nao fez nada", que e exatamente o sintoma que antecede o
--   abandono de uma ferramenta interna. Uso_eventos responde adocao;
--   as trilhas respondem resultado. O relatorio do dia precisa dos dois.
--
-- O QUE NAO ENTRA AQUI, DE PROPOSITO
--   Corpo de request, querystring e headers. Uma busca por CNPJ ou por
--   nome de cliente vira dado pessoal no log e o log nao tem o mesmo
--   cuidado de acesso que a tabela de origem. Guardamos o TEMPLATE da
--   rota (/crm/contas/{conta_id}), nunca o path com o id preenchido.
--
-- CARGO DESNORMALIZADO
--   'cargo' e copiado no momento do uso. Quando alguem muda de cargo, o
--   historico continua contando certo: o que a pessoa fez como SDR nao
--   vira retroativamente acao de EC.
--
-- RETENCAO
--   A tabela cresce por request, nao por negocio. O fechamento diario
--   apaga o que passou de TELEMETRIA_RETENCAO_DIAS (padrao 90). Sem
--   isso, um ano de operacao deixa dezenas de milhoes de linhas para
--   responder perguntas que ninguem faz sobre marco do ano passado.
--
-- NAO E DESTRUTIVA: so cria. Idempotente: pode rodar duas vezes.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. uso_eventos -- uma linha por request autenticada
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS uso_eventos (
    id           BIGSERIAL PRIMARY KEY,
    usuario_id   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    cargo        VARCHAR(80),
    metodo       VARCHAR(10)  NOT NULL,
    rota         VARCHAR(200) NOT NULL,
    modulo       VARCHAR(40),
    status       SMALLINT     NOT NULL,
    duracao_ms   INTEGER      NOT NULL,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uso_status    CHECK (status BETWEEN 100 AND 599),
    CONSTRAINT ck_uso_duracao   CHECK (duracao_ms >= 0)
);

-- O relatorio sempre recorta por dia; e o indice que sustenta todas as
-- agregacoes e tambem o DELETE da retencao.
CREATE INDEX IF NOT EXISTS idx_uso_eventos_criado
    ON uso_eventos (criado_em DESC);

-- "o que a pessoa X fez hoje" -- a secao por colaborador do relatorio.
CREATE INDEX IF NOT EXISTS idx_uso_eventos_usuario
    ON uso_eventos (usuario_id, criado_em DESC)
    WHERE usuario_id IS NOT NULL;

-- "quais telas sao usadas" e "onde da erro".
CREATE INDEX IF NOT EXISTS idx_uso_eventos_rota
    ON uso_eventos (rota, criado_em DESC);

COMMENT ON TABLE uso_eventos IS
    'Uma linha por request autenticada. Rota e o template, nunca o path com ids.';


-- ---------------------------------------------------------------------
-- 2. relatorios_diarios -- o fechamento de cada dia
-- ---------------------------------------------------------------------
-- Uma linha por dia, com as metricas congeladas em JSONB. Guardar o
-- numero fechado (e nao so recalcular na hora) e o que permite comparar
-- ontem com hoje depois que a retencao ja apagou os eventos brutos.
--
-- 'narrativa' e o texto gerado pela IA. Fica NULL quando a chave nao
-- esta configurada ou quando a chamada falhou -- o relatorio sai assim
-- mesmo, so com os numeros. A IA e enfeite util, nao dependencia.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS relatorios_diarios (
    dia               DATE PRIMARY KEY,
    metricas          JSONB       NOT NULL,
    narrativa         TEXT,
    narrativa_modelo  VARCHAR(60),
    destinatarios     TEXT[],
    enviado_em        TIMESTAMPTZ,
    erro              TEXT,
    gerado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relatorios_diarios_dia
    ON relatorios_diarios (dia DESC);

COMMENT ON COLUMN relatorios_diarios.metricas IS
    'Snapshot fechado do dia. Sobrevive a retencao de uso_eventos.';

COMMIT;
