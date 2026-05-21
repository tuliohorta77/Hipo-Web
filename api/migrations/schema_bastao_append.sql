-- ============================================================
-- HIPO — Schema do Bastão (idempotente)
-- Anexado ao schema.sql para o CI conseguir criar o banco de teste.
-- Mesmo conteúdo da migration 010.
-- ============================================================

DO $$ BEGIN
    CREATE TYPE bastao_status_enum AS ENUM (
        'PENDENTE',
        'APROVADO',
        'REJEITADO',
        'REMOVIDO'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS carteira_bastao (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hunter_nome         VARCHAR(150) NOT NULL,
    farmer_nome         VARCHAR(150) NOT NULL,
    cnpj_contador       VARCHAR(20) NOT NULL,
    data_parceria       DATE NOT NULL,
    leads_iniciais      INT NOT NULL DEFAULT 0 CHECK (leads_iniciais >= 0),
    status              bastao_status_enum NOT NULL DEFAULT 'PENDENTE',
    motivo_rejeicao     TEXT,
    criado_por          UUID NOT NULL REFERENCES usuarios(id),
    criado_em           TIMESTAMPTZ DEFAULT NOW(),
    validado_por        UUID REFERENCES usuarios(id),
    validado_em         TIMESTAMPTZ,
    removido_em         TIMESTAMPTZ,
    observacoes         TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bastao_cnpj_unico_ativo
    ON carteira_bastao(cnpj_contador)
    WHERE status IN ('PENDENTE', 'APROVADO');

CREATE INDEX IF NOT EXISTS idx_bastao_hunter
    ON carteira_bastao(hunter_nome, status);

CREATE INDEX IF NOT EXISTS idx_bastao_farmer
    ON carteira_bastao(farmer_nome, status);

CREATE INDEX IF NOT EXISTS idx_bastao_pendentes
    ON carteira_bastao(criado_em DESC)
    WHERE status = 'PENDENTE';
