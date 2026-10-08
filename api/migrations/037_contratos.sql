-- =====================================================================
-- HIPO -- 037_contratos.sql
--
-- Contrato com assinatura eletronica pela Autentique (entrega 053).
--
-- O contrato nasce de uma VERSAO APROVADA da proposta: o HIPO preenche o
-- modelo .docx, gera o PDF e manda para a Autentique com os quatro
-- signatarios da minuta (contratante, testemunha da contratante,
-- contratada, testemunha da contratada), assinatura sequencial.
--
-- SO EXISTE LINHA DEPOIS QUE A AUTENTIQUE ACEITOU. Falha no envio volta
-- como erro na tela e nada fica gravado -- mesma regra do e-mail (030).
-- Por isso autentique_id e NOT NULL e nao ha status de rascunho.
--
-- O ESTADO VEM DA AUTENTIQUE. O webhook e o timer leem o documento pela
-- API e reescrevem a situacao de cada signatario; contrato_eventos guarda
-- o que aconteceu (e, pelo evento_externo_id unico, impede processar a
-- mesma entrega duas vezes).
--
-- OS PDFs vao para o S3 (bucket dos anexos), quando ha bucket: o original
-- no envio e o assinado quando o ultimo assina. Sem bucket, o download
-- busca na Autentique na hora. O hash SHA-256 do original fica aqui de
-- qualquer jeito -- e o mesmo que a Autentique imprime no rodape.
--
-- ADITIVA E IDEMPOTENTE. Sem BEGIN/COMMIT: quem abre a transacao e o
-- scripts/aplicar_migrations.
-- =====================================================================

CREATE TABLE IF NOT EXISTS contratos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id     UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    -- RESTRICT: proposta nao se apaga (nao ha rota para isso), e se um dia
    -- houver, apagar a base de um contrato enviado tem que ser decisao.
    proposta_id         UUID NOT NULL REFERENCES propostas(id) ON DELETE RESTRICT,
    -- Versao do contrato dentro da oportunidade (cancelou e reenviou = v2).
    versao              INTEGER NOT NULL,
    status              VARCHAR(12) NOT NULL DEFAULT 'enviado',

    autentique_id       VARCHAR(80) NOT NULL,
    sandbox             BOOLEAN NOT NULL DEFAULT FALSE,
    nome_documento      VARCHAR(200) NOT NULL,

    -- Snapshot do que foi para o PDF: data, vigencia, vencimento e os
    -- campos preenchidos (a conta pode mudar de endereco depois).
    data_contrato       DATE NOT NULL,
    inicio_vigencia     DATE NOT NULL,
    dia_vencimento      SMALLINT NOT NULL,
    campos              JSONB NOT NULL,
    hash_original       CHAR(64) NOT NULL,
    modelo_hash         CHAR(64),

    s3_chave_original   VARCHAR(300),
    s3_chave_assinado   VARCHAR(300),

    assinado_em         TIMESTAMPTZ,
    recusado_em         TIMESTAMPTZ,
    cancelado_em        TIMESTAMPTZ,
    cancelado_por       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    motivo_cancelamento TEXT,
    sincronizado_em     TIMESTAMPTZ,
    sincronizacao_erro  TEXT,

    -- A tarefa concluida que registra o envio, e a tarefa aberta que avisa
    -- o executivo quando todos assinam (ou alguem recusa).
    tarefa_envio_id     UUID REFERENCES tarefas(id) ON DELETE SET NULL,
    tarefa_aviso_id     UUID REFERENCES tarefas(id) ON DELETE SET NULL,

    criado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_contrato_versao     UNIQUE (oportunidade_id, versao),
    CONSTRAINT uq_contrato_autentique UNIQUE (autentique_id),
    CONSTRAINT ck_contrato_status CHECK (
        status IN ('enviado', 'assinado', 'recusado', 'cancelado')
    ),
    CONSTRAINT ck_contrato_vencimento CHECK (dia_vencimento BETWEEN 1 AND 28),
    CONSTRAINT ck_contrato_vigencia   CHECK (inicio_vigencia >= data_contrato),
    CONSTRAINT ck_contrato_assinado   CHECK (status <> 'assinado' OR assinado_em IS NOT NULL),
    CONSTRAINT ck_contrato_cancelado  CHECK (status <> 'cancelado' OR cancelado_em IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_contratos_oportunidade
    ON contratos (oportunidade_id, versao DESC);
-- O timer de sincronizacao so olha quem ainda espera assinatura.
CREATE INDEX IF NOT EXISTS idx_contratos_em_aberto
    ON contratos (sincronizado_em NULLS FIRST) WHERE status = 'enviado';
-- Um contrato em andamento por oportunidade: o segundo envio sem cancelar
-- o primeiro mandaria duas versoes para o cliente assinar.
CREATE UNIQUE INDEX IF NOT EXISTS uq_contrato_em_aberto
    ON contratos (oportunidade_id) WHERE status = 'enviado';


CREATE TABLE IF NOT EXISTS contrato_signatarios (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id           UUID NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    ordem                 SMALLINT NOT NULL,
    papel                 VARCHAR(24) NOT NULL,
    nome                  VARCHAR(150) NOT NULL,
    email                 VARCHAR(150) NOT NULL,
    acao                  VARCHAR(20) NOT NULL,
    -- De onde a pessoa veio, quando veio do cadastro.
    contato_id            UUID REFERENCES contatos(id) ON DELETE SET NULL,
    usuario_id            UUID REFERENCES usuarios(id) ON DELETE SET NULL,

    autentique_public_id  VARCHAR(80),
    situacao              VARCHAR(16) NOT NULL DEFAULT 'pendente',
    visualizado_em        TIMESTAMPTZ,
    assinado_em           TIMESTAMPTZ,
    recusado_em           TIMESTAMPTZ,
    motivo_recusa         TEXT,
    reenviado_em          TIMESTAMPTZ,
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_contrato_sig_ordem UNIQUE (contrato_id, ordem),
    CONSTRAINT uq_contrato_sig_papel UNIQUE (contrato_id, papel),
    CONSTRAINT ck_contrato_sig_papel CHECK (
        papel IN ('contratante', 'testemunha_contratante',
                  'contratada', 'testemunha_contratada')
    ),
    CONSTRAINT ck_contrato_sig_acao CHECK (acao IN ('SIGN', 'SIGN_AS_A_WITNESS')),
    CONSTRAINT ck_contrato_sig_situacao CHECK (
        situacao IN ('pendente', 'visualizado', 'assinado', 'recusado', 'falha_entrega')
    )
);

CREATE INDEX IF NOT EXISTS idx_contrato_sig_contrato
    ON contrato_signatarios (contrato_id, ordem);


CREATE TABLE IF NOT EXISTS contrato_eventos (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id        UUID NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    -- enviado, visualizado, assinado, recusado, falha_entrega, concluido,
    -- cancelado, reenviado, webhook (entrega recebida), erro_arquivo
    tipo               VARCHAR(24) NOT NULL,
    origem             VARCHAR(16) NOT NULL,
    descricao          TEXT,
    signatario_id      UUID REFERENCES contrato_signatarios(id) ON DELETE SET NULL,
    -- id do evento na Autentique (event.id), so nas entregas do webhook.
    evento_externo_id  VARCHAR(80),
    usuario_id         UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_contrato_evento_origem CHECK (
        origem IN ('hipo', 'webhook', 'sincronizacao')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contrato_evento_externo
    ON contrato_eventos (evento_externo_id) WHERE evento_externo_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contrato_eventos_contrato
    ON contrato_eventos (contrato_id, criado_em DESC);
