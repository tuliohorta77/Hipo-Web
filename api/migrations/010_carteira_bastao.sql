-- ============================================================
-- HIPO — Migration 010: Passagem de Bastão (Hunter → Farmer)
--
-- Hunter prospecta contador, fecha parceria (Termo + 2 leads),
-- e "passa o bastão" pro Farmer cuidar do relacionamento.
-- Hunter mantém visibilidade pra acompanhar o desempenho do Farmer
-- naquele contador.
--
-- Workflow:
--   1. Hunter cria registro com status PENDENTE
--   2. ADM/Franqueado APROVA ou REJEITA (com motivo)
--   3. Hunter pode REMOVER (soft delete, status REMOVIDO)
--
-- Constraint: um CNPJ só pode estar em 1 bastão ATIVO (PENDENTE ou
-- APROVADO) por vez. Reabrir requer remover o anterior.
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

    -- Quem passou e quem recebeu (nomes — alinham com carteira_colaborador.nome
    -- e carteira_cnpj.colaborador_nome que vem do upload)
    hunter_nome         VARCHAR(150) NOT NULL,
    farmer_nome         VARCHAR(150) NOT NULL,

    -- Contador (CNPJ do contador, igual carteira_cnpj.cnpj_contador)
    cnpj_contador       VARCHAR(20) NOT NULL,

    -- Dados da parceria
    data_parceria       DATE NOT NULL,
    leads_iniciais      INT NOT NULL DEFAULT 0 CHECK (leads_iniciais >= 0),

    -- Workflow
    status              bastao_status_enum NOT NULL DEFAULT 'PENDENTE',
    motivo_rejeicao     TEXT,

    -- Auditoria
    criado_por          UUID NOT NULL REFERENCES usuarios(id),
    criado_em           TIMESTAMPTZ DEFAULT NOW(),
    validado_por        UUID REFERENCES usuarios(id),
    validado_em         TIMESTAMPTZ,
    removido_em         TIMESTAMPTZ,

    -- Observações livres (Hunter pode anotar)
    observacoes         TEXT
);

-- Garante 1:1 ativo: um CNPJ não pode estar em 2 bastões ATIVOS simultâneos.
-- (relação 1:1 conforme decisão de produto — pode ser revista no futuro)
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
