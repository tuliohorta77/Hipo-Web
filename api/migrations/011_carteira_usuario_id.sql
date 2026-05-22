-- ============================================================
-- HIPO — Migration 011: Vínculo usuário ↔ colaborador
--
-- Até aqui o vínculo entre um usuário (login) e um colaborador da
-- carteira era por CONVENÇÃO: usuarios.nome tinha que casar com
-- carteira_colaborador.nome. Frágil — qualquer divergência de
-- digitação quebrava o vínculo silenciosamente.
--
-- Esta migration cria o vínculo EXPLÍCITO: carteira_colaborador
-- ganha a coluna usuario_id, FK para usuarios(id).
--
-- Cardinalidade 1:1 (decisão de produto v1.3.0): um usuário pode
-- estar vinculado a no máximo UM colaborador. Garantido pelo
-- UNIQUE abaixo. Observação: no PostgreSQL um índice/constraint
-- UNIQUE permite múltiplos NULL — então vários colaboradores SEM
-- vínculo coexistem normalmente, e o UNIQUE só impede repetir um
-- usuario_id de fato preenchido.
--
-- ON DELETE SET NULL: se o usuário for removido, o colaborador
-- NÃO é apagado — apenas perde o vínculo (volta a "sem usuário").
--
-- Idempotente: pode ser reaplicada sem erro.
-- ============================================================

-- 1. Coluna (nullable — colaboradores entram pelo upload sem usuário;
--    o vínculo é feito manualmente depois, na tela Configurar).
ALTER TABLE carteira_colaborador
    ADD COLUMN IF NOT EXISTS usuario_id UUID;

-- 2. Foreign key para usuarios(id), com ON DELETE SET NULL.
DO $$ BEGIN
    ALTER TABLE carteira_colaborador
        ADD CONSTRAINT fk_colaborador_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 3. UNIQUE — garante a cardinalidade 1:1 (múltiplos NULL permitidos).
DO $$ BEGIN
    ALTER TABLE carteira_colaborador
        ADD CONSTRAINT uq_colaborador_usuario UNIQUE (usuario_id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 4. Índice para a filtragem por usuário (dashboards Hunter/Farmer
--    fazem WHERE usuario_id = $1). Parcial: só indexa linhas com
--    vínculo, que são as únicas consultadas por esse filtro.
CREATE INDEX IF NOT EXISTS idx_colaborador_usuario
    ON carteira_colaborador(usuario_id)
    WHERE usuario_id IS NOT NULL;
