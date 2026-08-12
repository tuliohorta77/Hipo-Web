-- =====================================================================
-- HIPO -- 005_parceiros.sql
--
-- Gestao da carteira de parceiros (Sprint 6).
--
-- O parceiro NAO e uma entidade nova. E uma conta com eh_finder = true --
-- sempre uma empresa, mesmo quando e um contador autonomo (entra com o CNPJ
-- dele). Nao existe tabela `parceiros` e nao existe indicador pessoa fisica.
--
-- Esta migration adiciona duas coisas:
--
-- 1) contas.ec_responsavel_id -- um EC dono por parceiro.
--    E o que da sentido a "minha carteira" e o que permite a tela por
--    funcao. Fica em contas e nao numa tabela de vinculo porque a relacao e
--    1:1: um parceiro tem no maximo um EC responsavel a cada momento. O
--    historico de quem foi dono quando vive em parceiro_eventos.
--
--    O CHECK ck_contas_ec_so_parceiro amarra o campo ao eh_finder: conta que
--    nao e parceira nao pode ter EC responsavel. Consequencia pratica, e
--    proposital: desmarcar o parceiro TEM que limpar o responsavel na mesma
--    transacao, senao o banco recusa. A regra vive na API
--    (routers/crm_parceiros.py) e o CHECK e a ultima linha de defesa.
--
-- 2) parceiro_eventos -- trilha de quem mexeu na carteira.
--    Mesma escolha de oportunidade_eventos: sem registrar a transicao, "de
--    quem era essa carteira em marco" vira pergunta sem resposta, e esse
--    dado nao da para reconstruir depois. Transferencia em massa grava uma
--    linha POR PARCEIRO, nao uma linha por lote -- o que interessa depois e
--    a historia de cada parceiro, nao a do clique.
--
-- SOBRE O CHECK DE FORMATO DOS EVENTOS
--    A versao rigorosa seria amarrar de/para a cada tipo ('atribuido' exige
--    de IS NULL e para NOT NULL, etc). Ela NAO esta aqui de proposito: as
--    duas FKs sao ON DELETE SET NULL, e apagar um usuario dispararia um
--    UPDATE que reavalia o CHECK e falharia com erro incompreensivel, ou
--    travaria a exclusao. O que sobra e o CHECK de tipo mais a garantia de
--    que de <> para. A forma correta de cada evento e responsabilidade da
--    API, que e quem escreve.
--
-- NAO E DESTRUTIVA: adiciona coluna, constraint, indices e uma tabela.
-- Nenhum DROP de dado. Idempotente: pode rodar duas vezes.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. EC responsavel pelo parceiro
-- ---------------------------------------------------------------------

ALTER TABLE contas
    ADD COLUMN IF NOT EXISTS ec_responsavel_id UUID REFERENCES usuarios(id) ON DELETE SET NULL;

-- DROP + ADD para a migration ser idempotente: ADD CONSTRAINT nao aceita
-- IF NOT EXISTS no PostgreSQL 15.
ALTER TABLE contas DROP CONSTRAINT IF EXISTS ck_contas_ec_so_parceiro;
ALTER TABLE contas ADD CONSTRAINT ck_contas_ec_so_parceiro
    CHECK (ec_responsavel_id IS NULL OR eh_finder);

-- Parcial: a esmagadora maioria das contas nao e parceira e nunca vai ter
-- responsavel. O indice serve a pergunta "quais sao os parceiros do EC X",
-- que e a tela inteira.
CREATE INDEX IF NOT EXISTS idx_contas_ec_responsavel
    ON contas (ec_responsavel_id)
    WHERE ec_responsavel_id IS NOT NULL;

COMMENT ON COLUMN contas.ec_responsavel_id IS
    'EC dono da relacao de parceria. So pode ser preenchido se eh_finder.';

-- ---------------------------------------------------------------------
-- 2. Trilha de eventos da parceria
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS parceiro_eventos (
    id               BIGSERIAL PRIMARY KEY,
    conta_id         UUID NOT NULL REFERENCES contas(id)   ON DELETE CASCADE,
    tipo             VARCHAR(20) NOT NULL,
    de_usuario_id    UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    para_usuario_id  UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    usuario_id       UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_parceiro_evento_tipo CHECK (
        tipo IN ('marcado', 'desmarcado', 'atribuido', 'transferido', 'removido')
    ),
    CONSTRAINT ck_parceiro_evento_de_para CHECK (
        de_usuario_id IS NULL OR de_usuario_id <> para_usuario_id
    )
);

CREATE INDEX IF NOT EXISTS idx_parceiro_eventos_conta
    ON parceiro_eventos (conta_id, criado_em DESC);

-- "O que o EC X fez / recebeu" e a pergunta da passagem de carteira.
CREATE INDEX IF NOT EXISTS idx_parceiro_eventos_para
    ON parceiro_eventos (para_usuario_id)
    WHERE para_usuario_id IS NOT NULL;

COMMIT;
