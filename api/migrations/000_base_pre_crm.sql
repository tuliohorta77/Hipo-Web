-- ============================================================================
-- HIPO -- 000_base_pre_crm.sql
-- As duas tabelas que existiam ANTES da 001 e sobreviveram a ela.
--
-- Por que existe: a 001 (drop do legado) parte de um banco que ja tinha
-- usuarios e dia_nao_util, criadas pelo ciclo anterior de migrations, que
-- saiu do repositorio. Sem esta 000, a sequencia 001..NNN nao sobe em banco
-- vazio -- e banco vazio e exatamente o que o CI e uma instancia nova usam.
--
-- Em PRODUCAO (base principal e MOS) esta migration e registrada como
-- legado pela 030 e nunca roda: as duas tabelas ja estao la.
--
-- Formato: o de antes da 008 (telefone entra na 008, ADD COLUMN IF NOT
-- EXISTS). gen_random_uuid() e nativo no PostgreSQL 13+.
-- ============================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome                  VARCHAR(150) NOT NULL,
    email                 VARCHAR(150) UNIQUE NOT NULL,
    senha_hash            TEXT NOT NULL,
    cargo                 VARCHAR(80),
    ativo                 BOOLEAN DEFAULT TRUE,
    precisa_trocar_senha  BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dia_nao_util (
    id                     SERIAL PRIMARY KEY,
    data                   DATE NOT NULL UNIQUE,
    motivo                 TEXT NOT NULL,
    criado_por_usuario_id  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dia_nao_util_ano ON dia_nao_util (EXTRACT(YEAR FROM data));
