-- =====================================================================
-- HIPO -- 008_propostas.sql
--
-- Proposta comercial gerada dentro do HIPO, a partir do modelo .pptx da
-- Controller MedSeg.
--
-- POR QUE UMA TABELA, E NAO CAMPOS NA OPORTUNIDADE
--   Proposta tem VERSAO. O cliente pede desconto, o vendedor refaz, e
--   duas semanas depois alguem pergunta "o que a gente mandou primeiro".
--   Guardado na oportunidade, o valor antigo seria sobrescrito pelo novo
--   e a pergunta ficaria sem resposta -- justamente na hora em que ela
--   vale dinheiro.
--
-- O ARQUIVO NAO E GUARDADO
--   Guardamos os DADOS; o .pptx e o .pdf sao remontados sob demanda a
--   partir do modelo. Um pptx de 16 MB por versao encheria o RDS por um
--   arquivo que se reproduz em segundos. A consequencia, que e aceita de
--   propósito: se a arte do modelo mudar, baixar uma proposta antiga traz
--   os dados antigos na arte nova.
--
-- SNAPSHOT DO EXECUTIVO E DO CLIENTE
--   nome, e-mail e telefone do executivo, e a razao social do cliente,
--   sao COPIADOS no momento da geracao. Quando alguem troca de telefone
--   ou a empresa muda de razao social, a proposta enviada continua
--   contando o que foi enviado. Mesma decisao do 'cargo' em uso_eventos.
--
-- ESCOPO EM JSONB
--   E uma lista ordenada de linhas livres, que vira uma linha por bullet
--   no slide. Nao ha consulta por item, nao ha catalogo ainda -- quando
--   houver (ver Pendencias: catalogo de servicos), isto vira FK e a
--   migration de entao converte. Text[] serviria; jsonb evita mais uma
--   conversao no asyncpg.
--
-- NAO E DESTRUTIVA: so cria e adiciona coluna. Idempotente.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Telefone do executivo, no cadastro de usuario
-- ---------------------------------------------------------------------
--
-- O slide de fechamento traz nome, e-mail e telefone de quem vendeu. Os
-- dois primeiros ja existiam; o telefone estava sendo digitado a mao em
-- cada proposta -- e digitado errado.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR(30);

COMMENT ON COLUMN usuarios.telefone IS
    'Telefone de contato do usuario, exibido na proposta comercial. '
    'Formato livre: sai no slide exatamente como foi digitado.';

-- ---------------------------------------------------------------------
-- 2. propostas
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS propostas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id     UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    versao              INTEGER NOT NULL,

    -- Quadro de investimento. mensalidade e investimento NAO sao colunas:
    -- sao vidas x valor_por_vida e a soma com treinamentos e laudos.
    -- Guardar o derivado abriria espaco para linha onde a conta nao fecha.
    vidas               INTEGER NOT NULL,
    valor_por_vida      NUMERIC(12,2) NOT NULL,
    treinamentos        NUMERIC(12,2) NOT NULL DEFAULT 0,
    laudos              NUMERIC(12,2) NOT NULL DEFAULT 0,

    escopo              JSONB NOT NULL,

    cidade              VARCHAR(80) NOT NULL DEFAULT 'Guarulhos',
    data_proposta       DATE NOT NULL,
    validade            DATE NOT NULL,

    -- Snapshot: ver nota no cabecalho.
    cliente_razao_social  VARCHAR(200) NOT NULL,
    executivo_id          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    executivo_nome        VARCHAR(150) NOT NULL,
    executivo_email       VARCHAR(150) NOT NULL,
    executivo_telefone    VARCHAR(30),

    criado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_proposta_versao UNIQUE (oportunidade_id, versao),
    CONSTRAINT ck_proposta_vidas        CHECK (vidas >= 1),
    CONSTRAINT ck_proposta_valor_vida   CHECK (valor_por_vida > 0),
    CONSTRAINT ck_proposta_treinamentos CHECK (treinamentos >= 0),
    CONSTRAINT ck_proposta_laudos       CHECK (laudos >= 0),
    CONSTRAINT ck_proposta_validade     CHECK (validade >= data_proposta),
    -- Escopo vazio geraria um slide com a lista em branco.
    CONSTRAINT ck_proposta_escopo       CHECK (jsonb_array_length(escopo) >= 1)
);

-- A aba Proposta lista as versoes da oportunidade, da mais nova para a
-- mais antiga. E o unico acesso que existe hoje.
CREATE INDEX IF NOT EXISTS idx_propostas_oportunidade
    ON propostas (oportunidade_id, versao DESC);

COMMIT;
