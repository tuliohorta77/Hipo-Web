-- =====================================================================
-- HIPO -- 017_relatorios_salvos.sql
--
-- Modulo de Relatorios: a montagem de tabela dinamica que o usuario
-- salva no proprio perfil, com nome.
--
-- O QUE E GUARDADO
--   So a MONTAGEM (fonte, periodo, linhas, colunas, valores, filtros), em
--   JSONB. Nunca o resultado: relatorio salvo e uma pergunta, e a resposta
--   tem que ser recalculada a cada abertura -- "vendas deste mes" salvo em
--   setembro mostra outubro em outubro. O periodo relativo (preset) e o
--   caso comum; o fixo existe para fechamento de periodo que nao muda.
--
-- POR QUE `fonte` E COLUNA, SE JA ESTA NO JSON
--   Para listar e agrupar sem abrir o JSON, e para achar com um SELECT
--   simples os relatorios afetados quando uma fonte do catalogo mudar.
--
-- COMPARTILHAR
--   `compartilhado` deixa os colegas VEREM e DUPLICAREM; editar e excluir
--   continuam so do dono (regra na API). Os DADOS de um relatorio
--   compartilhado passam pelo recorte de quem abre, nao de quem criou.
--
-- NOME UNICO POR DONO, sem diferenciar maiusculas e espacos nas pontas:
-- dois "Funil do mes" na mesma lista e o jeito mais rapido de alguem
-- editar o errado.
--
-- ON DELETE CASCADE no dono: relatorio salvo e preferencia pessoal, nao
-- dado da operacao. (Usuario que sai e desativado, nao apagado -- os
-- relatorios dele ficam.)
--
-- ADITIVA E IDEMPOTENTE: uma tabela e dois indices novos. Nenhum DROP,
-- nenhum DELETE, nenhuma coluna alterada. Nao exige export previo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS relatorios_salvos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id     UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nome           VARCHAR(120) NOT NULL,
    descricao      TEXT,
    fonte          VARCHAR(40)  NOT NULL,
    config         JSONB        NOT NULL,
    compartilhado  BOOLEAN      NOT NULL DEFAULT FALSE,
    criado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_relatorio_nome   CHECK (length(btrim(nome)) > 0),
    CONSTRAINT ck_relatorio_config CHECK (jsonb_typeof(config) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_relatorios_salvos_nome
    ON relatorios_salvos (usuario_id, lower(btrim(nome)));

CREATE INDEX IF NOT EXISTS idx_relatorios_salvos_compartilhados
    ON relatorios_salvos (usuario_id)
    WHERE compartilhado;
