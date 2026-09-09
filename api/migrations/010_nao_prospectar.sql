-- =====================================================================
-- HIPO -- 010_nao_prospectar.sql
--
-- Marca de "esta empresa nao deve ser prospectada".
--
-- O CASO QUE TROUXE ISTO
--   A Controller MedSeg ja atende ~330 empresas. A carteira da Oraculus
--   traz ~950 empresas para o topo do funil. Sem uma marca, nada impede
--   um SDR de abrir oportunidade em cima de quem ja e cliente -- e o
--   custo nao e um registro duplicado, e uma ligacao comercial para um
--   cliente ativo.
--
-- POR QUE COLUNA EM `contas`, E NAO TABELA DE BLOQUEIO POR CNPJ
--   `contas.cnpj` ja e a chave de negocio, ja e UNIQUE e ja produz o 409
--   com o registro existente. Uma tabela paralela por CNPJ faria o mesmo
--   documento existir em dois lugares, e o 409 -- que e onde a pessoa
--   realmente esbarra -- nao enxergaria a lista sem uma consulta extra em
--   toda criacao de conta. Uma fonte de verdade so.
--
-- POR QUE O MOTIVO E OBRIGATORIO
--   Bloqueio sem motivo vira misterio em tres meses, e ninguem se sente
--   autorizado a liberar o que nao sabe por que foi bloqueado. O CHECK
--   amarra os tres campos: marcado exige motivo e data; desmarcado exige
--   os dois nulos, para o registro nao guardar um motivo orfao que a tela
--   mostraria como se ainda valesse.
--
-- O QUE ESTA MARCA NAO FAZ
--   Nao mexe em `ativo` (delete logico -- a empresa existe e e visivel),
--   nao mexe em `eh_finder` (relacao de parceria e outro eixo: um cliente
--   MedSeg pode indicar) e nao fecha oportunidade nenhuma. Ela bloqueia a
--   CRIACAO de oportunidade nova. Oportunidade ja aberta segue viva de
--   proposito: encerrar negocio em andamento por causa de uma carga em
--   massa seria a migration decidindo o que e trabalho do vendedor.
--
-- NAO E DESTRUTIVA: so acrescenta coluna. Idempotente.
-- =====================================================================

BEGIN;

ALTER TABLE contas
    ADD COLUMN IF NOT EXISTS nao_prospectar        BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE contas
    ADD COLUMN IF NOT EXISTS nao_prospectar_motivo TEXT;

ALTER TABLE contas
    ADD COLUMN IF NOT EXISTS nao_prospectar_em     TIMESTAMPTZ;

ALTER TABLE contas
    ADD COLUMN IF NOT EXISTS nao_prospectar_por    UUID REFERENCES usuarios(id) ON DELETE SET NULL;

-- Os tres campos andam juntos. Marcado sem motivo e bloqueio anonimo;
-- desmarcado com motivo e texto morto que a tela mostraria como vigente.
ALTER TABLE contas DROP CONSTRAINT IF EXISTS ck_contas_nao_prospectar;
ALTER TABLE contas ADD CONSTRAINT ck_contas_nao_prospectar CHECK (
    (nao_prospectar
        AND nao_prospectar_em IS NOT NULL
        AND nao_prospectar_motivo IS NOT NULL
        AND length(btrim(nao_prospectar_motivo)) > 0)
    OR
    (NOT nao_prospectar
        AND nao_prospectar_em IS NULL
        AND nao_prospectar_motivo IS NULL
        AND nao_prospectar_por IS NULL)
);

-- Indice parcial: a pergunta e sempre "quais estao bloqueadas", nunca
-- "quais nao estao" -- as nao bloqueadas sao quase todas.
CREATE INDEX IF NOT EXISTS idx_contas_nao_prospectar
    ON contas (id) WHERE nao_prospectar;

COMMIT;
