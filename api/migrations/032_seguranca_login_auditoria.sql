-- =====================================================================
-- HIPO -- 032_seguranca_login_auditoria.sql
--
-- Duas trilhas de seguranca, as duas so de escrita pela API:
--
--   login_tentativas    -- cada POST /auth/login, com sucesso ou nao: o
--                          e-mail digitado, o IP e o resultado. E a base do
--                          limite contra forca bruta (services/login_limite)
--                          e o historico de login que o JWT stateless nao
--                          tem.
--
--   leituras_sensiveis  -- quem LEU dado pessoal (contato, socio) e quando.
--                          Uma linha por resposta de rota sensivel, com os
--                          ids dos registros devolvidos. E o que responde
--                          "quem viu o telefone da Fulana" (LGPD, art. 37:
--                          registro das operacoes de tratamento).
--
-- login_tentativas NAO tem FK para usuarios, de proposito: a tentativa
-- com e-mail que nao existe e justamente a que mais interessa, e e-mail
-- digitado nao e usuario. O e-mail e normalizado (lower/trim) antes de
-- gravar, para "Fulano@X" e "fulano@x" contarem como o mesmo alvo.
--
-- leituras_sensiveis TEM FK, com ON DELETE SET NULL, e copia email e
-- cargo do momento da leitura: usuario e desativado, nao apagado, mas se
-- um dia for apagado a trilha continua dizendo quem era.
--
-- O QUE NAO ENTRA: o conteudo lido. A trilha guarda QUAIS registros foram
-- vistos, nunca o telefone ou o e-mail em si -- senao o log viraria uma
-- segunda copia do dado pessoal, com menos protecao que a tabela de origem
-- (mesma regra da 007).
--
-- ADITIVA E IDEMPOTENTE: so CREATE ... IF NOT EXISTS. Nenhum DROP, DELETE
-- ou UPDATE em dado existente. Nao exige export previo. Sem BEGIN/COMMIT:
-- quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================


CREATE TABLE IF NOT EXISTS login_tentativas (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(150) NOT NULL,
    ip          VARCHAR(64),
    sucesso     BOOLEAN      NOT NULL,
    -- 'senha' (credencial errada), 'inativo_ou_inexistente', 'bloqueado'
    -- (barrado pelo limite, sem nem conferir a senha). NULL no sucesso.
    motivo      VARCHAR(30),
    user_agent  VARCHAR(300),
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_login_motivo CHECK (
        (sucesso AND motivo IS NULL)
        OR (NOT sucesso AND motivo IN ('senha', 'inativo_ou_inexistente', 'bloqueado'))
    )
);

-- O limite conta falhas recentes POR E-MAIL e POR IP. Os dois indices
-- sustentam essas contagens e o DELETE da retencao.
CREATE INDEX IF NOT EXISTS idx_login_tentativas_email
    ON login_tentativas (email, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_login_tentativas_ip
    ON login_tentativas (ip, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_login_tentativas_criado
    ON login_tentativas (criado_em DESC);

COMMENT ON TABLE login_tentativas IS
    'Cada POST /auth/login. Base do limite contra forca bruta e do historico de login.';


CREATE TABLE IF NOT EXISTS leituras_sensiveis (
    id             BIGSERIAL PRIMARY KEY,
    usuario_id     UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    usuario_email  VARCHAR(150) NOT NULL,
    cargo          VARCHAR(80),
    -- 'contato' ou 'socio'. Texto e nao enum: recurso novo entra sem
    -- migration.
    recurso        VARCHAR(30)  NOT NULL,
    -- Template da rota (/crm/contatos/{contato_id}), como na telemetria.
    rota           VARCHAR(200) NOT NULL,
    -- Os registros devolvidos naquela resposta. Lista vazia = a busca nao
    -- trouxe ninguem (a tentativa de ver tambem e registro).
    registro_ids   UUID[]       NOT NULL DEFAULT '{}',
    -- Contexto da leitura: conta, oportunidade, termo buscado. Nunca o
    -- dado pessoal devolvido.
    contexto       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ip             VARCHAR(64),
    criado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_leitura_recurso CHECK (length(btrim(recurso)) > 0)
);

-- "o que a pessoa X leu" (por periodo).
CREATE INDEX IF NOT EXISTS idx_leituras_sensiveis_usuario
    ON leituras_sensiveis (usuario_id, criado_em DESC);
-- "quem leu o registro Y" -- o pedido classico do titular.
CREATE INDEX IF NOT EXISTS idx_leituras_sensiveis_registros
    ON leituras_sensiveis USING GIN (registro_ids);
CREATE INDEX IF NOT EXISTS idx_leituras_sensiveis_criado
    ON leituras_sensiveis (criado_em DESC);

COMMENT ON TABLE leituras_sensiveis IS
    'Quem leu dado pessoal (contato, socio) e quando. Guarda os ids, nunca o conteudo.';

