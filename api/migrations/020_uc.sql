-- =====================================================================
-- HIPO -- 020_uc.sql
--
-- Universidade Corporativa (UC), entrega UC-1: conteudo e manual da
-- funcao. Especificacao: claude/universidade-corporativa.md.
--
-- CINCO TABELAS
--   uc_trilhas        -- trilha de aprendizado, presa a um dos tres
--                        pilares (tecnica, metodo, energia)
--   uc_trilha_cargos  -- o "manual da funcao": quais cargos fazem a
--                        trilha, se e obrigatoria e em quantos dias
--   uc_aulas          -- aula da trilha: texto, video (provedor + id,
--                        nunca a URL crua) e duracao estimada
--   uc_materiais      -- PDF/imagem/documento de apoio, no S3 (mesmo
--                        bucket dos anexos, prefixo uc/)
--   uc_progresso      -- quem abriu e quem concluiu cada VERSAO da aula
--
-- VIDEO COMO PROVEDOR + ID. A URL de embed e montada pelo front a partir
-- do par. Guardar a URL crua deixaria qualquer endereco virar
-- <iframe src>; o CHECK de provedor fecha essa porta no banco tambem.
--
-- PROGRESSO POR VERSAO. Aula que muda de forma relevante sobe `versao`, e
-- quem concluiu a anterior volta a ter a aula pendente -- sem apagar o
-- registro de que concluiu a antiga. Por isso a PK inclui aula_versao.
--
-- `desde` EM uc_trilha_cargos. O prazo de uma obrigatoria conta da
-- entrada da pessoa no cargo OU do dia em que a trilha virou obrigatoria
-- para aquele cargo, o que vier depois. Sem isso, a primeira trilha
-- publicada nasceria atrasada para toda a equipe que ja estava la.
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nenhum DROP,
-- nenhum DELETE, nenhuma coluna alterada. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS uc_trilhas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    titulo        VARCHAR(160) NOT NULL,
    descricao     TEXT,
    pilar         VARCHAR(10)  NOT NULL,
    -- Medida que a trilha ajuda a melhorar. E o elo com o PDI (UC-5):
    -- componente fraco na avaliacao do mes aponta para a trilha que o
    -- reforca. NULL = trilha que nao e de reforco.
    reforca       VARCHAR(20),
    status        VARCHAR(10)  NOT NULL DEFAULT 'rascunho',
    criado_por    UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uc_trilha_pilar   CHECK (pilar IN ('tecnica', 'metodo', 'energia')),
    CONSTRAINT ck_uc_trilha_status  CHECK (status IN ('rascunho', 'publicada', 'arquivada')),
    CONSTRAINT ck_uc_trilha_reforca CHECK (
        reforca IS NULL OR reforca IN (
            'obrigatorias', 'tarefas_no_prazo', 'desfecho_em_dia', 'roteiro', 'metas'
        )
    ),
    CONSTRAINT ck_uc_trilha_titulo  CHECK (length(btrim(titulo)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_uc_trilhas_status ON uc_trilhas (status, pilar);

CREATE TABLE IF NOT EXISTS uc_trilha_cargos (
    trilha_id   UUID NOT NULL REFERENCES uc_trilhas(id) ON DELETE CASCADE,
    cargo       VARCHAR(80) NOT NULL,
    obrigatoria BOOLEAN NOT NULL DEFAULT TRUE,
    prazo_dias  SMALLINT,
    desde       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trilha_id, cargo),
    CONSTRAINT ck_uc_trilha_cargo_prazo CHECK (prazo_dias IS NULL OR prazo_dias BETWEEN 1 AND 365)
);

CREATE INDEX IF NOT EXISTS idx_uc_trilha_cargos_cargo ON uc_trilha_cargos (cargo);

CREATE TABLE IF NOT EXISTS uc_aulas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trilha_id     UUID NOT NULL REFERENCES uc_trilhas(id) ON DELETE CASCADE,
    ordem         SMALLINT NOT NULL,
    titulo        VARCHAR(160) NOT NULL,
    resumo        TEXT,
    conteudo_md   TEXT,
    video_provedor VARCHAR(10),
    video_ref     VARCHAR(120),
    duracao_min   SMALLINT,
    -- Nota minima do quiz (UC-2). Ja nasce aqui para a aula nao mudar de
    -- forma quando o quiz chegar.
    nota_minima   SMALLINT NOT NULL DEFAULT 70,
    versao        SMALLINT NOT NULL DEFAULT 1,
    status        VARCHAR(10) NOT NULL DEFAULT 'publicada',
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uc_aula_ordem UNIQUE (trilha_id, ordem) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_uc_aula_titulo   CHECK (length(btrim(titulo)) > 0),
    CONSTRAINT ck_uc_aula_ordem    CHECK (ordem >= 1),
    CONSTRAINT ck_uc_aula_status   CHECK (status IN ('rascunho', 'publicada')),
    CONSTRAINT ck_uc_aula_provedor CHECK (
        video_provedor IS NULL OR video_provedor IN ('youtube', 'vimeo', 'loom', 'drive')
    ),
    CONSTRAINT ck_uc_aula_video_par CHECK ((video_provedor IS NULL) = (video_ref IS NULL)),
    CONSTRAINT ck_uc_aula_duracao  CHECK (duracao_min IS NULL OR duracao_min BETWEEN 1 AND 600),
    CONSTRAINT ck_uc_aula_nota     CHECK (nota_minima BETWEEN 0 AND 100),
    CONSTRAINT ck_uc_aula_versao   CHECK (versao >= 1)
);

CREATE TABLE IF NOT EXISTS uc_materiais (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aula_id       UUID NOT NULL REFERENCES uc_aulas(id) ON DELETE CASCADE,
    chave_s3      TEXT NOT NULL UNIQUE,
    nome_original VARCHAR(255) NOT NULL,
    tipo_mime     VARCHAR(120) NOT NULL,
    bytes         BIGINT NOT NULL,
    enviado_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uc_material_bytes CHECK (bytes > 0),
    CONSTRAINT ck_uc_material_nome  CHECK (length(btrim(nome_original)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_uc_materiais_aula ON uc_materiais (aula_id, criado_em);

CREATE TABLE IF NOT EXISTS uc_progresso (
    usuario_id   UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    aula_id      UUID NOT NULL REFERENCES uc_aulas(id) ON DELETE CASCADE,
    aula_versao  SMALLINT NOT NULL,
    aberta_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    concluida_em TIMESTAMPTZ,
    PRIMARY KEY (usuario_id, aula_id, aula_versao),
    CONSTRAINT ck_uc_progresso_ordem CHECK (concluida_em IS NULL OR concluida_em >= aberta_em)
);

CREATE INDEX IF NOT EXISTS idx_uc_progresso_aula ON uc_progresso (aula_id, aula_versao);
