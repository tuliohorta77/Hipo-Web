-- =====================================================================
-- HIPO -- 042_ligacao_duplicada.sql
--
-- Gravacao duplicada de ligacao (gravador 1.0.7).
--
-- O canal do cliente grava tudo o que toca no headset. Se a ligacao ainda
-- esta aberta no softphone e a pessoa da play numa gravacao pelo HIPO, o
-- gravador manda uma segunda gravacao com a mesma conversa (13/10/2026).
-- O coletor compara a transcricao com as ligacoes da mesma pessoa dos 15
-- minutos em volta (services/ligacao.mesma_conversa) e marca a copia:
--
--   ligacoes.duplicada_de  -- a ligacao original. Preenchido, a linha some
--                             da faixa "sem vinculo" e das contas de
--                             atividade. So linha SEM vinculo e marcada.
--
-- ADITIVA E IDEMPOTENTE. Sem BEGIN/COMMIT: quem abre a transacao e o
-- scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE ligacoes ADD COLUMN IF NOT EXISTS duplicada_de UUID
    REFERENCES ligacoes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ligacoes_duplicada_de
    ON ligacoes (duplicada_de) WHERE duplicada_de IS NOT NULL;
