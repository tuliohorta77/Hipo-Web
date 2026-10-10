-- =====================================================================
-- HIPO -- 040_ligacoes.sql
--
-- Ligacoes pelo Vivo Voz Negocio, gravadas na maquina e transcritas (056).
--
-- O softphone da Vivo (PABX em nuvem da Metaswitch) nao tem API: nao da
-- para pedir a gravacao nem saber quem ligou para quem. O HIPO junta duas
-- metades:
--
--   1. o CLIQUE: o "ligar" no telefone do contato, dentro do HIPO, grava
--      uma linha em `ligacoes` (status 'discando') com quem, para quem e
--      de qual oportunidade/tarefa -- e o navegador abre o tel: no
--      softphone;
--   2. a GRAVACAO: o gravador (agente Windows na maquina do executivo)
--      percebe a chamada pelo audio do softphone, grava microfone e saida
--      em dois canais e manda para o HIPO. O servidor casa a gravacao com
--      o clique mais proximo da mesma pessoa (services/ligacao.casar).
--
-- Gravacao sem clique (o cliente retornou, discou direto no softphone)
-- entra do mesmo jeito, sem vinculo, e a pessoa vincula na tela.
--
-- DUAS TABELAS:
--   ligacao_gravadores  uma linha por maquina com o agente instalado. O
--                       token fica so como hash (SHA-256); quem perde a
--                       maquina revoga na tela.
--   ligacoes            uma linha por ligacao (clique, gravacao ou os dois).
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Sem BEGIN/COMMIT:
-- quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================

CREATE TABLE IF NOT EXISTS ligacao_gravadores (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id        UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    -- Rotulo da maquina ("Notebook da Kethlleen"), para a tela de revogar.
    nome              VARCHAR(80) NOT NULL,
    -- SHA-256 do token em hex. O token em claro aparece UMA vez na tela.
    token_hash        CHAR(64) NOT NULL UNIQUE,
    -- Os primeiros caracteres, para reconhecer na lista sem expor o resto.
    token_prefixo     VARCHAR(16) NOT NULL,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    criado_por        UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    -- Pulso do agente (a cada poucos minutos). E o "gravador ligado" da tela.
    ultimo_contato_em TIMESTAMPTZ,
    versao_agente     VARCHAR(20),
    maquina           VARCHAR(120),
    revogado_em       TIMESTAMPTZ,
    CONSTRAINT ck_gravador_nome CHECK (length(btrim(nome)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_gravadores_usuario
    ON ligacao_gravadores (usuario_id) WHERE revogado_em IS NULL;

CREATE TABLE IF NOT EXISTS ligacoes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id            UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    -- O alvo. Oportunidade OU conta de parceiro, como nas tarefas; os dois
    -- nulos = gravacao ainda sem vinculo.
    oportunidade_id       UUID REFERENCES oportunidades(id) ON DELETE SET NULL,
    conta_id              UUID REFERENCES contas(id)        ON DELETE SET NULL,
    contato_id            UUID REFERENCES contatos(id)      ON DELETE SET NULL,
    tarefa_id             UUID REFERENCES tarefas(id)       ON DELETE SET NULL,
    telefone              VARCHAR(30),
    -- clique   = nasceu do "ligar" no HIPO;
    -- gravador = nasceu da gravacao, sem clique para casar.
    origem                VARCHAR(10) NOT NULL,
    clicada_em            TIMESTAMPTZ,
    gravador_id           UUID REFERENCES ligacao_gravadores(id) ON DELETE SET NULL,
    -- Id que o AGENTE deu para a gravacao. O agente reenvia o que nao
    -- conseguiu mandar (internet caiu, notebook fechou); com este id o
    -- reenvio cai na mesma linha em vez de duplicar a ligacao.
    gravacao_local_id     VARCHAR(64),
    -- Inicio e fim do AUDIO, no relogio do servidor (o agente manda os
    -- dois e o servidor corrige o desvio do relogio da maquina).
    inicio_em             TIMESTAMPTZ,
    fim_em                TIMESTAMPTZ,
    duracao_s             INTEGER,
    -- ligacoes/<usuario_id>/<ligacao_id>.flac no bucket dos anexos. Nulo
    -- depois da retencao (audio_removido_em) -- a transcricao fica.
    audio_s3_chave        TEXT,
    audio_bytes           BIGINT,
    audio_removido_em     TIMESTAMPTZ,
    -- discando      clique feito, gravacao ainda nao chegou;
    -- enviando      o agente pediu o endereco de upload;
    -- transcrevendo audio no S3, job no AWS Transcribe;
    -- pronta        transcricao gravada (resumo pode vir depois);
    -- sem_fala      audio sem fala nenhuma (so chamou, caixa postal muda);
    -- sem_gravacao  clique sem gravacao depois da janela (gravador
    --               desligado, ligou pelo celular);
    -- erro          falhou; `erro` diz o que.
    status                VARCHAR(14) NOT NULL DEFAULT 'discando',
    transcricao_job       VARCHAR(200),
    transcricao_iniciada_em TIMESTAMPTZ,
    -- [{inicio, fim, participante, canal, texto}] -- mesmo formato das
    -- reunioes, mais o canal (0 = quem ligou, 1 = cliente).
    transcricao_entradas  JSONB,
    transcricao_texto     TEXT,
    transcrita_em         TIMESTAMPTZ,
    fala_usuario_pct      SMALLINT,
    tentativas            SMALLINT NOT NULL DEFAULT 0,
    erro                  TEXT,
    resumo                TEXT,
    proximos_passos       JSONB,
    resumo_modelo         VARCHAR(80),
    resumo_em             TIMESTAMPTZ,
    resumo_erro           TEXT,
    vinculada_por         UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    vinculada_em          TIMESTAMPTZ,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ligacao_origem CHECK (origem IN ('clique', 'gravador')),
    CONSTRAINT ck_ligacao_status CHECK (status IN (
        'discando', 'enviando', 'transcrevendo', 'pronta',
        'sem_fala', 'sem_gravacao', 'erro')),
    CONSTRAINT ck_ligacao_alvo CHECK (num_nonnulls(oportunidade_id, conta_id) <= 1),
    CONSTRAINT ck_ligacao_clique CHECK (origem <> 'clique' OR clicada_em IS NOT NULL),
    CONSTRAINT ck_ligacao_fala CHECK (
        fala_usuario_pct IS NULL OR fala_usuario_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_ligacao_duracao CHECK (duracao_s IS NULL OR duracao_s >= 0)
);

-- Casamento: os cliques ainda sem gravacao de uma pessoa, pelo horario.
CREATE INDEX IF NOT EXISTS idx_ligacoes_cliques_abertos
    ON ligacoes (usuario_id, clicada_em) WHERE status = 'discando';

-- Reenvio do agente: a mesma gravacao, a mesma linha.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ligacoes_gravacao_local
    ON ligacoes (usuario_id, gravacao_local_id) WHERE gravacao_local_id IS NOT NULL;

-- Aba Ligacoes da oportunidade e do parceiro.
CREATE INDEX IF NOT EXISTS idx_ligacoes_oportunidade
    ON ligacoes (oportunidade_id, criado_em DESC) WHERE oportunidade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ligacoes_conta
    ON ligacoes (conta_id, criado_em DESC) WHERE conta_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ligacoes_tarefa
    ON ligacoes (tarefa_id) WHERE tarefa_id IS NOT NULL;

-- "Ligacoes sem vinculo" da pessoa.
CREATE INDEX IF NOT EXISTS idx_ligacoes_sem_vinculo
    ON ligacoes (usuario_id, criado_em DESC)
    WHERE oportunidade_id IS NULL AND conta_id IS NULL AND status <> 'discando';

-- O coletor olha so o que esta em andamento.
CREATE INDEX IF NOT EXISTS idx_ligacoes_em_andamento
    ON ligacoes (status, atualizado_em)
    WHERE status IN ('discando', 'enviando', 'transcrevendo');
