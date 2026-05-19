-- ============================================================
-- HIPO — Migration 008: Coluna precisa_trocar_senha em usuarios
--
-- Adiciona uma flag pra forçar troca de senha no próximo login.
-- Por ora não está ativada na lógica (opção B: troca opcional via
-- página /perfil), mas a coluna fica pronta caso a gente queira
-- exigir trocas periódicas no futuro.
--
-- Aplicação: idempotente — usa IF NOT EXISTS.
-- ============================================================

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS precisa_trocar_senha BOOLEAN DEFAULT FALSE;
