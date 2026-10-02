-- =====================================================================
-- HIPO -- 022_base_receita.sql
--
-- A base de Dados Abertos do CNPJ da Receita, recortada pelas UFs de
-- atuacao, para a tela de Prospeccao fatiar por CNAE e regiao.
--
-- O QUE ESTA BASE E -- E O QUE ELA NAO E
--   E FONTE DE CONSULTA, nao cadastro. Nada aqui e conta, lead ou
--   oportunidade. A empresa so entra no CRM quando um SDR a PUXA pela tela
--   (POST /crm/prospeccao/puxar), e nesse momento ganha autor, data e
--   oportunidade com dono -- a mesma trilha de qualquer cadastro por
--   formulario. E isso que mantem a diretriz "nada entra por importacao":
--   a base fica ao lado do CRM, e o CRM continua nascendo de gente.
--
-- QUEM ESCREVE AQUI
--   So o script `scripts/carregar_base_receita.py`, uma vez por mes. A API
--   apenas le. Por isso nenhuma tabela tem FK para usuarios: o TRUNCATE
--   CASCADE do conftest nao as alcanca, e o db_conn as trunca por nome.
--
-- SO EMPRESAS ATIVAS, E SEM MEI
--   A carga descarta situacao cadastral diferente de 02 (ativa) e, por
--   padrao, MEI -- que tem no maximo um empregado e nao compra medicina
--   ocupacional. As duas decisoes reduzem a tabela a menos da metade. Por
--   isso nao existe coluna de situacao: toda linha e ativa.
--
-- CNAE COMO TEXTO DE TAMANHO FIXO
--   Filtrar por divisao ("41"), grupo ("412") ou subclasse ("4120400") vira
--   faixa: '41' -> BETWEEN '4100000' AND '4199999'. Com 7 digitos sempre,
--   a ordem do texto e a ordem do numero, e o indice btree serve as tres.
--
-- NAO E DESTRUTIVA: quatro tabelas novas, nenhum DROP, nenhum DELETE.
-- Idempotente. Nao exige o export previo em CSV.
--
-- O CONTEUDO, POR OUTRO LADO, E SUBSTITUIDO A CADA CARGA MENSAL (o script
-- troca a tabela inteira). Isso e permitido porque o dado e publico e
-- reproduzivel a partir dos ZIPs da Receita -- nao e trabalho de ninguem.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS receita_estabelecimentos (
    cnpj               CHAR(14) PRIMARY KEY,
    cnpj_basico        CHAR(8)  NOT NULL,
    matriz             BOOLEAN  NOT NULL,
    razao_social       VARCHAR(200) NOT NULL,
    nome_fantasia      VARCHAR(200),
    natureza_juridica  CHAR(4),
    -- Codigo da Receita: 00 nao informado, 01 ME, 03 EPP, 05 demais.
    -- E faixa de FATURAMENTO, nao de funcionarios.
    porte              CHAR(2),
    capital_social     NUMERIC(17,2),
    -- Optante do Simples. Quem NAO e optante fatura acima do teto do
    -- Simples -- e o melhor sinal de porte que a base publica oferece.
    simples            BOOLEAN,
    mei                BOOLEAN,
    data_abertura      DATE,
    cnae_principal     CHAR(7) NOT NULL,
    cnaes_secundarios  CHAR(7)[] NOT NULL DEFAULT '{}',
    logradouro         VARCHAR(200),
    numero             VARCHAR(20),
    complemento        VARCHAR(100),
    bairro             VARCHAR(100),
    cep                CHAR(8),
    uf                 CHAR(2) NOT NULL,
    -- Codigo de municipio da RECEITA (tabela TOM/SIAFI, 4 digitos), que
    -- NAO e o codigo do IBGE. O nome mora em receita_municipios.
    municipio_codigo   CHAR(4) NOT NULL,
    telefone           VARCHAR(20),
    telefone_2         VARCHAR(20),
    email              VARCHAR(150),
    CONSTRAINT ck_receita_cnpj CHECK (cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT ck_receita_cnae CHECK (cnae_principal ~ '^[0-9]{7}$'),
    CONSTRAINT ck_receita_uf   CHECK (uf ~ '^[A-Z]{2}$')
);

-- UF por igualdade, CNAE por faixa: e a pergunta da tela.
CREATE INDEX IF NOT EXISTS idx_receita_uf_cnae
    ON receita_estabelecimentos (uf, cnae_principal);
-- A mesma pergunta recortada por cidade.
CREATE INDEX IF NOT EXISTS idx_receita_uf_municipio_cnae
    ON receita_estabelecimentos (uf, municipio_codigo, cnae_principal);
-- "Incluir CNAE secundario": o risco de uma empresa nem sempre esta no
-- CNAE fiscal. Ver conta_cnaes_secundarios (014).
CREATE INDEX IF NOT EXISTS idx_receita_cnaes_sec
    ON receita_estabelecimentos USING gin (cnaes_secundarios);

CREATE TABLE IF NOT EXISTS receita_municipios (
    codigo  CHAR(4) PRIMARY KEY,
    nome    VARCHAR(100) NOT NULL,
    uf      CHAR(2) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_receita_municipios_uf
    ON receita_municipios (uf, nome);

CREATE TABLE IF NOT EXISTS receita_cnaes (
    codigo     CHAR(7) PRIMARY KEY,
    descricao  VARCHAR(300) NOT NULL,
    CONSTRAINT ck_receita_cnaes_codigo CHECK (codigo ~ '^[0-9]{7}$')
);

-- Uma linha por execucao do script. A tela mostra a ultima concluida
-- ("base de 2026-09, carregada em 05/10"): quem fatia precisa saber de
-- quando e o dado que esta olhando.
CREATE TABLE IF NOT EXISTS receita_cargas (
    id                SERIAL PRIMARY KEY,
    referencia        VARCHAR(20) NOT NULL,
    ufs               VARCHAR(100) NOT NULL,
    status            VARCHAR(12) NOT NULL DEFAULT 'carregando',
    estabelecimentos  INTEGER,
    observacao        TEXT,
    iniciada_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    concluida_em      TIMESTAMPTZ,
    CONSTRAINT ck_receita_cargas_status
        CHECK (status IN ('carregando', 'concluida', 'erro'))
);
CREATE INDEX IF NOT EXISTS idx_receita_cargas_concluidas
    ON receita_cargas (concluida_em DESC) WHERE status = 'concluida';

COMMIT;
