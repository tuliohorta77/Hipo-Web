-- =====================================================================
-- HIPO -- 016_reuniao_transcricao.sql
--
-- A transcricao da reuniao, puxada do Google Meet depois que ela acaba.
--
-- O FLUXO
--   1. A reuniao online nasce com sala do Meet (entrega 014).
--   2. Logo depois de criar o evento, o HIPO liga a transcricao
--      AUTOMATICA daquela sala pela Meet REST API. Ninguem precisa
--      lembrar de clicar em "Transcrever" -- e e exatamente o clique que
--      ninguem lembra de dar. `reunioes.transcricao_auto_em` e
--      `transcricao_auto_erro` guardam se isso deu certo.
--   3. Um timer (hipo-transcricoes.timer) passa a cada 15 minutos,
--      procura reuniao que ja acabou e ainda nao tem transcricao, e busca
--      as falas na API. O texto vira linha aqui, presa a reuniao -- que e
--      uma tarefa, entao a transcricao aparece na tarefa.
--   4. Se a chave da Anthropic estiver no .env, sai tambem um resumo com
--      os proximos passos. SUGESTAO: quem registra o desfecho e agenda a
--      proxima tarefa continua sendo a pessoa.
--
-- POR QUE O TEXTO E COPIADO PARA CA, E NAO SO LINKADO
--   A Meet API apaga as falas 30 dias depois da conferencia. O Google Doc
--   que o Meet gera mora no Drive do ANFITRIAO: sai da empresa junto com
--   ele, e so abre para quem o anfitriao compartilhou. O que a operacao
--   combinou com o cliente nao pode depender de nenhum dos dois. O link
--   do Doc e guardado ao lado, como conveniencia.
--
-- UMA LINHA POR REUNIAO
--   A mesma sala pode ter tido duas conferencias (a chamada caiu e todo
--   mundo voltou). O coletor junta as duas numa transcricao so, em ordem
--   de horario: para quem le, foi uma reuniao.
--
-- STATUS
--   aguardando   -- ainda pode chegar (reuniao em andamento, Google
--                   gerando o arquivo, ninguem entrou AINDA)
--   pronta       -- texto gravado
--   indisponivel -- nao vai chegar: ninguem entrou na sala, ou a
--                   transcricao nao foi ligada. `motivo` diz qual.
--
--   Erro de API (credencial, rede) NAO e status: e `erro`, com o status
--   continuando em `aguardando`. Uma queda do Google as 15h nao pode
--   declarar "indisponivel" uma transcricao que existe.
--
-- NAO E DESTRUTIVA: uma tabela nova e duas colunas nulaveis. Nenhum DROP,
-- nenhum DELETE, idempotente. Nao exige o export previo em CSV.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. A transcricao automatica foi ligada na sala?
-- ---------------------------------------------------------------------
ALTER TABLE reunioes
    ADD COLUMN IF NOT EXISTS transcricao_auto_em   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS transcricao_auto_erro TEXT;


-- ---------------------------------------------------------------------
-- 2. A transcricao
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reuniao_transcricoes (
    reuniao_id          UUID PRIMARY KEY REFERENCES reunioes(id) ON DELETE CASCADE,
    status              VARCHAR(16) NOT NULL DEFAULT 'aguardando',
    -- Por que ainda esta aguardando, ou por que nao vai chegar. Frase em
    -- portugues para a tela, e nao codigo.
    motivo              TEXT,
    -- Ultimo erro TECNICO da coleta (403 da delegacao, rede). NULL quando
    -- a ultima tentativa falou com o Google sem problema.
    erro                TEXT,
    tentativas          INTEGER NOT NULL DEFAULT 0,
    ultima_tentativa_em TIMESTAMPTZ,

    -- Os `conferenceRecords/...` que compuseram o texto. Rastro: e o que
    -- permite, com a API ainda dentro dos 30 dias, conferir de onde veio.
    conferencias        TEXT[] NOT NULL DEFAULT '{}',
    documento_url       TEXT,
    idioma              VARCHAR(16),
    -- As falas estruturadas: [{inicio, fim, participante, texto}]. O
    -- `texto` abaixo e derivado delas; as duas ficam porque a tela le o
    -- texto corrido e uma futura busca por fala le a estrutura.
    entradas            JSONB,
    texto               TEXT,
    coletada_em         TIMESTAMPTZ,

    -- O resumo pela IA. Opcional: sem ANTHROPIC_API_KEY a transcricao
    -- chega igual, so sem resumo.
    resumo              TEXT,
    proximos_passos     JSONB,
    resumo_modelo       VARCHAR(64),
    resumo_em           TIMESTAMPTZ,
    resumo_erro         TEXT,

    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_transcricao_status
        CHECK (status IN ('aguardando', 'pronta', 'indisponivel')),
    -- "Pronta" sem texto seria a tela prometendo o que nao tem.
    CONSTRAINT ck_transcricao_pronta_tem_texto
        CHECK (status <> 'pronta' OR (texto IS NOT NULL AND coletada_em IS NOT NULL))
);

-- O coletor pergunta "o que ainda esta aguardando" a cada 15 minutos.
CREATE INDEX IF NOT EXISTS idx_reuniao_transcricoes_aguardando
    ON reuniao_transcricoes (ultima_tentativa_em)
    WHERE status = 'aguardando';

COMMIT;
