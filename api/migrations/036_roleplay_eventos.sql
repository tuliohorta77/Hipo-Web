-- =====================================================================
-- HIPO -- 036_roleplay_eventos.sql
--
-- Carreira · Roleplay com IA: diario da conexao de voz de cada treino
-- (abriu, goAway, caiu, reconectou, cliente sem resposta...). Serve para
-- diagnosticar "travou" sem depender da memoria de quem treinou.
-- Lista [{t_ms, tipo, detalhe}] montada pelo navegador, limitada no servidor.
--
-- ADITIVA E IDEMPOTENTE: so ADD COLUMN IF NOT EXISTS. Nao exige export.
-- =====================================================================

ALTER TABLE roleplay_sessoes
    ADD COLUMN IF NOT EXISTS eventos JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE roleplay_sessoes
    ADD COLUMN IF NOT EXISTS sem_resposta SMALLINT NOT NULL DEFAULT 0;
