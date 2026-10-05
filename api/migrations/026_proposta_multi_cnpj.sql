-- =====================================================================
-- HIPO -- 026_proposta_multi_cnpj.sql
--
-- Proposta com varios CNPJs e tabela de preco por faixa de vidas
-- (pedido do Tulio, 05/10/2026).
--
-- O PROBLEMA
--   Cliente com varios CNPJs (matriz, filiais, empresas do mesmo grupo)
--   e UMA negociacao. Abrir uma oportunidade por CNPJ duplicava o funil,
--   dividia o ticket e deixava cada conta sem saber das outras.
--
-- O QUE ENTRA
--
--   1. oportunidade_contas -- CNPJs ADICIONAIS de uma oportunidade. A conta
--      principal continua em oportunidades.conta_id (nada muda para o
--      funil, a agenda e os relatorios); aqui ficam so as outras. E por
--      esta tabela que a conta de cada CNPJ sabe que esta na mesma
--      oportunidade. Desvincular e logico (removido_em), para o historico
--      da conta contar que ela ja esteve naquela negociacao.
--
--   2. tabela_preco_faixas -- a tabela de preco por faixa de vidas, editada
--      pela gestao. Nasce com a tabela da Controller MedSeg (180/220/260/
--      300 e R$ 15,00 por vida acima de 20). Uma faixa so pode ser aberta
--      (vidas_ate NULL), e ela e a ultima.
--
--   3. propostas.modalidade -- 'por_vida' (o que ja existia: vidas x valor
--      por vida) ou 'tabela' (valor de cada CNPJ sugerido pela faixa e
--      negociavel). Na modalidade tabela, a proposta guarda uma COPIA da
--      tabela usada (tabela_preco): reajuste depois nao muda proposta ja
--      enviada -- mesma decisao do snapshot do executivo.
--
--   4. proposta_itens -- um CNPJ por linha, com vidas e mensalidade. A
--      mensalidade da proposta passa a ser a SOMA dos itens. valor_tabela
--      guarda o que a tabela sugeria naquele dia, para a tela mostrar o
--      desconto dado.
--
-- PROPOSTAS ANTIGAS
--   Ganham um item cada (o CNPJ principal da oportunidade, com
--   vidas x valor_por_vida), para o codigo novo ler tudo do mesmo jeito.
--   E INSERT, nao UPDATE: nenhum dado existente e alterado.
--
-- valor_por_vida passa a aceitar NULL (na modalidade tabela nao existe).
-- E a unica alteracao de coluna existente, e nao apaga dado nenhum.
--
-- ADITIVA E IDEMPOTENTE. Nenhum DROP de tabela ou coluna, nenhum DELETE.
-- Nao exige export previo.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. CNPJs adicionais da oportunidade
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS oportunidade_contas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id  UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    conta_id         UUID NOT NULL REFERENCES contas(id) ON DELETE RESTRICT,
    criado_por       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    removido_por     UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    removido_em      TIMESTAMPTZ
);

-- Um CNPJ aparece uma vez so entre os vinculos VIGENTES de uma
-- oportunidade; vinculos removidos ficam como historico.
CREATE UNIQUE INDEX IF NOT EXISTS uq_oportunidade_contas_vigente
    ON oportunidade_contas (oportunidade_id, conta_id)
    WHERE removido_em IS NULL;

-- "Em que oportunidade esta conta esta?" -- a pergunta da tela da conta,
-- da prospeccao e da criacao de oportunidade.
CREATE INDEX IF NOT EXISTS idx_oportunidade_contas_conta
    ON oportunidade_contas (conta_id)
    WHERE removido_em IS NULL;

-- ---------------------------------------------------------------------
-- 2. Tabela de preco por faixa de vidas
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tabela_preco_faixas (
    id              SERIAL PRIMARY KEY,
    -- Limite superior da faixa, inclusive. NULL = faixa aberta ("acima de").
    vidas_ate       INTEGER,
    -- 'fixo': o valor e a mensalidade do CNPJ inteiro.
    -- 'por_vida': o valor e multiplicado pelas vidas do CNPJ.
    tipo            VARCHAR(10) NOT NULL,
    valor           NUMERIC(12,2) NOT NULL,
    atualizado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_faixa_tipo  CHECK (tipo IN ('fixo', 'por_vida')),
    CONSTRAINT ck_faixa_valor CHECK (valor > 0),
    CONSTRAINT ck_faixa_vidas CHECK (vidas_ate IS NULL OR vidas_ate >= 1)
);

-- Dois limites iguais, ou duas faixas abertas, deixariam a tabela ambigua.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tabela_preco_faixas_limite
    ON tabela_preco_faixas ((COALESCE(vidas_ate, 2147483647)));

INSERT INTO tabela_preco_faixas (vidas_ate, tipo, valor)
SELECT v.vidas_ate, v.tipo, v.valor
  FROM (VALUES
        (5,    'fixo',     180.00),
        (10,   'fixo',     220.00),
        (15,   'fixo',     260.00),
        (20,   'fixo',     300.00),
        (NULL, 'por_vida',  15.00)
       ) AS v(vidas_ate, tipo, valor)
 WHERE NOT EXISTS (SELECT 1 FROM tabela_preco_faixas);

-- ---------------------------------------------------------------------
-- 3. Modalidade da proposta e copia da tabela
-- ---------------------------------------------------------------------

ALTER TABLE propostas ADD COLUMN IF NOT EXISTS modalidade VARCHAR(10)
    NOT NULL DEFAULT 'por_vida';
ALTER TABLE propostas ADD COLUMN IF NOT EXISTS tabela_preco JSONB;

ALTER TABLE propostas ALTER COLUMN valor_por_vida DROP NOT NULL;

ALTER TABLE propostas DROP CONSTRAINT IF EXISTS ck_proposta_valor_vida;
ALTER TABLE propostas ADD CONSTRAINT ck_proposta_valor_vida
    CHECK (valor_por_vida IS NULL OR valor_por_vida > 0);

ALTER TABLE propostas DROP CONSTRAINT IF EXISTS ck_proposta_modalidade;
ALTER TABLE propostas ADD CONSTRAINT ck_proposta_modalidade CHECK (
    (modalidade = 'por_vida' AND valor_por_vida IS NOT NULL)
    OR
    (modalidade = 'tabela' AND tabela_preco IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- 4. Itens (CNPJs) da proposta
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS proposta_itens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposta_id   UUID NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
    ordem         SMALLINT NOT NULL,
    conta_id      UUID REFERENCES contas(id) ON DELETE SET NULL,
    -- Snapshot: a proposta enviada continua dizendo o CNPJ e a razao
    -- social que foram enviados.
    cnpj          CHAR(14) NOT NULL,
    razao_social  VARCHAR(200) NOT NULL,
    vidas         INTEGER NOT NULL,
    mensalidade   NUMERIC(12,2) NOT NULL,
    valor_tabela  NUMERIC(12,2),
    CONSTRAINT uq_proposta_item_ordem UNIQUE (proposta_id, ordem),
    CONSTRAINT uq_proposta_item_cnpj  UNIQUE (proposta_id, cnpj),
    CONSTRAINT ck_proposta_item_vidas CHECK (vidas >= 1),
    CONSTRAINT ck_proposta_item_valor CHECK (mensalidade >= 0),
    CONSTRAINT ck_proposta_item_tabela CHECK (valor_tabela IS NULL OR valor_tabela >= 0)
);

CREATE INDEX IF NOT EXISTS idx_proposta_itens_conta
    ON proposta_itens (conta_id);

-- Propostas antigas: um item, o CNPJ principal da oportunidade.
INSERT INTO proposta_itens (proposta_id, ordem, conta_id, cnpj, razao_social,
                            vidas, mensalidade)
SELECT p.id, 1, o.conta_id, c.cnpj, p.cliente_razao_social, p.vidas,
       ROUND(p.vidas * p.valor_por_vida, 2)
  FROM propostas p
  JOIN oportunidades o ON o.id = p.oportunidade_id
  JOIN contas c        ON c.id = o.conta_id
 WHERE p.valor_por_vida IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM proposta_itens i WHERE i.proposta_id = p.id);

COMMIT;
