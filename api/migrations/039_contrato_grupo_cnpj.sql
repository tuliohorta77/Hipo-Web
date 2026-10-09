-- =====================================================================
-- HIPO -- 039_contrato_grupo_cnpj.sql
--
-- Contrato por raiz de CNPJ, Anexo 1, substituicao e servicos extras (055).
--
-- Regra do Tulio (09/10/2026):
--   * matriz e filiais (mesma raiz = 8 primeiros digitos do CNPJ) saem no
--     MESMO contrato: a matriz qualifica a contratante, as demais vao no
--     Anexo 1;
--   * raizes diferentes = empresas diferentes = um contrato cada, sempre;
--   * CNPJ novo depois de assinado: contrato novo com todos os CNPJs da
--     raiz, que SUBSTITUI o anterior quando e assinado (sem aditivo).
--
--   contratos.raiz_cnpj         -- a raiz do grupo deste contrato
--   contratos.servicos          -- chaves do catalogo marcadas no envio
--   contratos.servicos_livres   -- linhas escritas a mao
--   contratos.substitui_ids     -- os assinados que este substitui (na hora
--                                  do envio; viram 'substituido' quando este
--                                  e assinado)
--   contratos.substituido_por   -- no contrato antigo, quem o substituiu
--   contrato_cnpjs              -- os CNPJs do contrato (snapshot), contratante
--                                  primeiro
--
-- Contratos ja existentes: raiz = a do CNPJ principal da oportunidade; os
-- CNPJs vem dos itens da proposta de origem.
--
-- ADITIVA. A trava de "um contrato em andamento" passa de por oportunidade
-- para por oportunidade + raiz (DROP INDEX, nao de tabela nem de coluna).
-- Sem BEGIN/COMMIT: quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE contratos ADD COLUMN IF NOT EXISTS raiz_cnpj CHAR(8);
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS servicos TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS servicos_livres TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS substitui_ids UUID[] NOT NULL DEFAULT '{}';
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS substituido_por UUID
    REFERENCES contratos(id) ON DELETE SET NULL;
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS substituido_em TIMESTAMPTZ;

UPDATE contratos k
   SET raiz_cnpj = LEFT(c.cnpj, 8)
  FROM oportunidades o
  JOIN contas c ON c.id = o.conta_id
 WHERE o.id = k.oportunidade_id
   AND k.raiz_cnpj IS NULL;

ALTER TABLE contratos ALTER COLUMN raiz_cnpj SET NOT NULL;

ALTER TABLE contratos DROP CONSTRAINT IF EXISTS ck_contrato_status;
ALTER TABLE contratos ADD CONSTRAINT ck_contrato_status CHECK (
    status IN ('enviado', 'assinado', 'recusado', 'cancelado', 'substituido')
);
ALTER TABLE contratos DROP CONSTRAINT IF EXISTS ck_contrato_substituido;
ALTER TABLE contratos ADD CONSTRAINT ck_contrato_substituido CHECK (
    status <> 'substituido' OR substituido_em IS NOT NULL
);

DROP INDEX IF EXISTS uq_contrato_em_aberto;
CREATE UNIQUE INDEX IF NOT EXISTS uq_contrato_em_aberto_raiz
    ON contratos (oportunidade_id, raiz_cnpj) WHERE status = 'enviado';
-- "Qual o contrato vigente desta empresa?" -- consultado no envio, para
-- saber o que o contrato novo substitui.
CREATE INDEX IF NOT EXISTS idx_contratos_raiz_assinado
    ON contratos (raiz_cnpj) WHERE status = 'assinado';


CREATE TABLE IF NOT EXISTS contrato_cnpjs (
    contrato_id   UUID NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    ordem         SMALLINT NOT NULL,
    conta_id      UUID REFERENCES contas(id) ON DELETE SET NULL,
    cnpj          CHAR(14) NOT NULL,
    razao_social  VARCHAR(200) NOT NULL,
    vidas         INTEGER NOT NULL,
    mensalidade   NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (contrato_id, ordem),
    CONSTRAINT uq_contrato_cnpj UNIQUE (contrato_id, cnpj)
);

CREATE INDEX IF NOT EXISTS idx_contrato_cnpjs_cnpj ON contrato_cnpjs (cnpj);

INSERT INTO contrato_cnpjs (contrato_id, ordem, conta_id, cnpj, razao_social, vidas,
                            mensalidade)
SELECT k.id, i.ordem, i.conta_id, i.cnpj, i.razao_social, i.vidas, i.mensalidade
  FROM contratos k
  JOIN proposta_itens i ON i.proposta_id = k.proposta_id
 WHERE NOT EXISTS (SELECT 1 FROM contrato_cnpjs x WHERE x.contrato_id = k.id)
ON CONFLICT DO NOTHING;
