-- =====================================================================
-- HIPO -- 028_contatos_multithreading.sql
--
-- Contatos: varios por oportunidade (ABM / multithreading) e contato
-- obrigatorio nas tarefas de interacao.
--
--   1. contatos ganha 2o telefone, a marca de WhatsApp de cada numero e
--      o LinkedIn. Editar o contato passa a ser o caminho para trocar
--      telefone -- antes era preciso excluir e cadastrar de novo.
--
--   2. oportunidade_contatos: o COMITE da oportunidade. Cada pessoa com o
--      seu papel na decisao (decisor, campeao, influenciador, operacional,
--      compras, tecnico) e no maximo UM principal.
--
--      oportunidades.contato_id CONTINUA EXISTINDO e passa a ser o espelho
--      do principal. Nao saiu porque relatorio, busca, proposta, RPeR e
--      importadores leem a coluna; tira-la seria refator amplo sem ganho
--      para quem usa a tela. Quem escreve o espelho e a API
--      (routers/crm_oportunidade_contatos.definir_principal) -- na mesma
--      transacao de quem mexe na lista.
--
--   3. tarefas.contato_id: com quem e a interacao. Obrigatorio (regra da
--      API, nao CHECK) em ligacao, reuniao, visita, whatsapp e e-mail.
--      Nao e CHECK de proposito: as tarefas antigas abertas continuam
--      validas e a prospeccao em lote abre o "primeiro contato" de quem
--      ainda nao tem contato nenhum -- descobrir a pessoa E a tarefa.
--
-- ADITIVA E IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, CREATE ... IF NOT
-- EXISTS e INSERT ... ON CONFLICT DO NOTHING. Nenhum DROP, nenhum DELETE,
-- nenhum UPDATE em dado existente fora do preenchimento de coluna NOVA.
-- Nao exige export previo.
-- =====================================================================

BEGIN;

-- == 1. Contato: 2o telefone, WhatsApp e LinkedIn ==
ALTER TABLE contatos ADD COLUMN IF NOT EXISTS telefone_whatsapp   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE contatos ADD COLUMN IF NOT EXISTS telefone_2          VARCHAR(20);
ALTER TABLE contatos ADD COLUMN IF NOT EXISTS telefone_2_whatsapp BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE contatos ADD COLUMN IF NOT EXISTS linkedin            VARCHAR(300);

CREATE INDEX IF NOT EXISTS idx_contatos_telefone_2 ON contatos (telefone_2)
    WHERE telefone_2 IS NOT NULL;


-- == 2. O comite da oportunidade ==
CREATE TABLE IF NOT EXISTS oportunidade_contatos (
    oportunidade_id  UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    contato_id       UUID NOT NULL REFERENCES contatos(id)      ON DELETE CASCADE,
    -- NULL = ainda nao classificado. Vocabulario fechado: e a cobertura
    -- do comite que a tela mede, e papel inventado nao entra na conta.
    papel            VARCHAR(20),
    principal        BOOLEAN NOT NULL DEFAULT FALSE,
    criado_por       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (oportunidade_id, contato_id),
    CONSTRAINT ck_opp_contato_papel CHECK (
        papel IS NULL OR papel IN (
            'decisor', 'campeao', 'influenciador',
            'operacional', 'compras', 'tecnico'
        )
    )
);

-- No maximo um principal por oportunidade.
CREATE UNIQUE INDEX IF NOT EXISTS uq_opp_contato_principal
    ON oportunidade_contatos (oportunidade_id) WHERE principal;

CREATE INDEX IF NOT EXISTS idx_opp_contatos_contato
    ON oportunidade_contatos (contato_id);

-- Backfill: o contato que cada oportunidade ja tinha vira o principal do
-- comite. ON CONFLICT torna a migration re-executavel.
INSERT INTO oportunidade_contatos (oportunidade_id, contato_id, principal, criado_por, criado_em)
SELECT o.id, o.contato_id, TRUE, o.criado_por, o.criado_em
  FROM oportunidades o
 WHERE o.contato_id IS NOT NULL
ON CONFLICT (oportunidade_id, contato_id) DO NOTHING;


-- == 3. Com quem e a tarefa ==
ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS contato_id UUID
    REFERENCES contatos(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tarefas_contato
    ON tarefas (contato_id) WHERE contato_id IS NOT NULL;

-- Backfill A (fato): a reuniao da agenda ja dizia com quem era.
UPDATE tarefas t
   SET contato_id = r.contato_id
  FROM reunioes r
 WHERE r.tarefa_id = t.id
   AND r.contato_id IS NOT NULL
   AND t.contato_id IS NULL;

-- Backfill B (ponto de partida): tarefa de interacao AINDA ABERTA de
-- oportunidade sem contato herda o principal da oportunidade. So as
-- abertas -- historico concluido nao ganha um "com quem" que ninguem
-- afirmou. Quem estiver errado troca ao editar.
UPDATE tarefas t
   SET contato_id = o.contato_id
  FROM oportunidades o
 WHERE o.id = t.oportunidade_id
   AND o.contato_id IS NOT NULL
   AND t.contato_id IS NULL
   AND t.concluida_em IS NULL
   AND t.cancelada_em IS NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');

COMMIT;
