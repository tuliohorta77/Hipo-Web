-- =====================================================================
-- HIPO -- 030_emails.sql
--
-- E-mail comercial pela Gmail API (entrega 050).
--
--   email_modelos    -- os modelos que a gestao edita (primeiro contato e
--                       envio de proposta). Semeados com os textos que a
--                       equipe ja mandava a mao. Tabela vazia = vale o
--                       MODELOS_PADRAO do codigo (services/email_comercial).
--
--   emails_enviados  -- cada e-mail que saiu da caixa de um vendedor por
--                       uma oportunidade: para quem, o texto como foi, a
--                       proposta anexada, os ids do Gmail e se o cliente
--                       respondeu. E a base do fluxo de Touchs (cadencia):
--                       o "sem resposta ha N dias" sai daqui.
--
--   So e-mail ENVIADO vira linha. Envio que o Gmail recusou volta como erro
--   para a tela e nao e gravado: seria registro de algo que o cliente nunca
--   viu.
--
-- ADITIVA E IDEMPOTENTE: CREATE ... IF NOT EXISTS e INSERT ... ON CONFLICT
-- DO NOTHING. Nenhum DROP, DELETE ou UPDATE em dado existente. Sem
-- BEGIN/COMMIT: quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================

CREATE TABLE IF NOT EXISTS email_modelos (
    slug            VARCHAR(40) PRIMARY KEY,
    nome            VARCHAR(80) NOT NULL,
    assunto         VARCHAR(250) NOT NULL,
    corpo           TEXT NOT NULL,
    -- O modelo de proposta pede a escolha da versao e anexa o PDF.
    anexa_proposta  BOOLEAN NOT NULL DEFAULT FALSE,
    ordem           SMALLINT NOT NULL DEFAULT 0,
    atualizado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_email_modelo_nome    CHECK (length(btrim(nome)) > 0),
    CONSTRAINT ck_email_modelo_assunto CHECK (length(btrim(assunto)) > 0),
    CONSTRAINT ck_email_modelo_corpo   CHECK (length(btrim(corpo)) > 0)
);

CREATE TABLE IF NOT EXISTS emails_enviados (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id   UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    -- Com quem e a conversa. Mesmo papel do tarefas.contato_id (045).
    contato_id        UUID REFERENCES contatos(id) ON DELETE SET NULL,
    -- Modelo de partida. Texto livre, e nao FK: o modelo pode ser editado
    -- depois, e o que vale para o historico e o texto gravado abaixo.
    modelo_slug       VARCHAR(40),
    proposta_id       UUID REFERENCES propostas(id) ON DELETE SET NULL,
    proposta_item_id  UUID REFERENCES proposta_itens(id) ON DELETE SET NULL,
    anexo_nome        VARCHAR(200),

    -- Quem enviou e de que caixa. O e-mail e copiado: se o usuario trocar
    -- de endereco, a verificacao de resposta continua olhando a caixa de
    -- onde a mensagem saiu.
    remetente_id      UUID NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    remetente_email   VARCHAR(150) NOT NULL,

    para              TEXT[] NOT NULL,
    cc                TEXT[] NOT NULL DEFAULT '{}',
    assunto           VARCHAR(250) NOT NULL,
    corpo             TEXT NOT NULL,
    com_assinatura    BOOLEAN NOT NULL DEFAULT FALSE,

    gmail_message_id  VARCHAR(64) NOT NULL,
    gmail_thread_id   VARCHAR(64),
    enviado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Resposta do cliente (scripts/verificar_respostas_email, a cada 15
    -- min, e o botao da tela). So cabecalhos: o corpo da resposta nao e lido.
    respondido_em     TIMESTAMPTZ,
    resposta_de       VARCHAR(200),
    verificado_em     TIMESTAMPTZ,
    verificacao_erro  TEXT,

    CONSTRAINT ck_email_para CHECK (cardinality(para) >= 1),
    CONSTRAINT ck_email_assunto CHECK (length(btrim(assunto)) > 0),
    CONSTRAINT ck_email_item_tem_proposta CHECK (
        proposta_item_id IS NULL OR proposta_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_emails_oportunidade
    ON emails_enviados (oportunidade_id, enviado_em DESC);

-- A fila da verificacao de resposta: so o que ainda nao foi respondido.
CREATE INDEX IF NOT EXISTS idx_emails_sem_resposta
    ON emails_enviados (enviado_em)
    WHERE respondido_em IS NULL AND gmail_thread_id IS NOT NULL;

INSERT INTO email_modelos (slug, nome, assunto, corpo, anexa_proposta, ordem)
VALUES
(
    'primeiro_contato',
    'Primeiro contato',
    'Medicina Ocupacional e Segurança do Trabalho',
    E'Olá, {{contato_primeiro_nome}}, tudo bem?\n' ||
    E'\n' ||
    E'Meu nome é {{remetente_primeiro_nome}} e faço parte da equipe comercial da Controller Medicina e Segurança do Trabalho.\n' ||
    E'\n' ||
    E'Atendemos empresas em todas as regiões do Brasil, oferecendo uma solução completa para Medicina Ocupacional e Segurança do Trabalho, desde os exames ocupacionais até a gestão das obrigações de SST.\n' ||
    E'\n' ||
    E'Além dos exames, nossa contratação já contempla ASO, PCMSO, PGR e LTCAT, proporcionando mais praticidade e centralização para a empresa.\n' ||
    E'\n' ||
    E'Queria entender como vocês fazem essa gestão atualmente e se existe algum ponto que podemos ajudar a melhorar — seja em prazo, atendimento, custo ou centralização dos serviços.\n' ||
    E'\n' ||
    E'Atenciosamente,',
    FALSE,
    1
),
(
    'proposta',
    'Envio de proposta',
    'Proposta comercial {{nossa_empresa}} — {{empresa}}',
    E'{{saudacao}}, {{contato_primeiro_nome}}, tudo bem?\n' ||
    E'\n' ||
    E'Conforme alinhamos em nossa reunião, envio em anexo a proposta comercial para a {{razao_social}}.\n' ||
    E'O documento detalha o escopo completo dos serviços apresentados e seus valores.\n' ||
    E'\n' ||
    E'Fico à disposição para maiores esclarecimentos.\n' ||
    E'\n' ||
    E'At.te',
    TRUE,
    2
)
ON CONFLICT (slug) DO NOTHING;
