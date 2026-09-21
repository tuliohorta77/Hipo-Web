-- ============================================================================
-- HIPO — 014: enriquecimento cadastral por CNPJ
--
-- Aditiva e idempotente. NENHUM DROP, nenhum DELETE, nenhuma coluna alterada
-- de tipo. Pode rodar duas vezes seguidas sem efeito na segunda.
--
-- O QUE ESTA MIGRATION MATERIALIZA
--
--   * `cnaes` — o CNAE deixa de ser texto solto e vira registro com
--     mapeamento próprio: qual vertical comercial ele representa e qual o
--     grau de risco (Quadro I da NR-4, 1 a 4). Nasce VAZIO de propósito:
--     nenhum CNAE chega mapeado, porque mapa chutado é pior que mapa
--     ausente — ninguém confere o que já veio preenchido. A tela pede o
--     mapeamento quando o CNAE aparece pela primeira vez numa conta.
--
--   * `conta_socios` — o QSA da Receita. Guarda o documento SEMPRE
--     mascarado: a Receita já entrega `***123456**`, e o normalizador
--     mascara de novo caso alguma fonte paga devolva o CPF inteiro. CPF
--     completo não entra nesta tabela em hipótese nenhuma.
--
--   * `conta_enriquecimentos` — cache e trilha. Toda consulta a fonte
--     externa fica registrada com o payload cru, inclusive as que falharam.
--     É o que permite responder "de onde saiu esse dado" seis meses depois,
--     e é o que evita pagar duas vezes pela mesma consulta.
--
--   * Colunas novas em `contas` — os campos que a Receita preenche e que
--     antes eram digitados: CNAE, porte, situação cadastral, data de
--     abertura e capital social. Mais a PROCEDÊNCIA do nº de funcionários,
--     que é a coluna que impede o erro caro descrito abaixo.
--
-- POR QUE `num_funcionarios_origem` EXISTE
--
--   O nº de funcionários de fonte paga é ESTIMATIVA (base RAIS/CAGED, com
--   defasagem de meses). O nº que o cliente informa é o número de vidas do
--   contrato. Os dois cabem na mesma coluna e valem coisas diferentes:
--   estimativa serve para priorizar quem prospectar; vida declarada serve
--   para precificar. Sem a procedência, um enriquecimento noturno
--   sobrescreveria o número que o vendedor ouviu do cliente por um palpite
--   de um ano atrás — e a proposta sairia errada sem ninguém perceber.
--
--   A regra que a aplicação garante: ESTIMADO NUNCA SOBRESCREVE DECLARADO.
--
-- NOTA SOBRE O conftest
--
--   A fixture `db_conn` roda TRUNCATE usuarios CASCADE. As três tabelas
--   novas têm FK para `usuarios`, então o CASCADE as alcança e cada teste
--   começa do zero — sem precisar de TRUNCATE explícito como o que
--   `relatorios_diarios` exigiu. Se alguma FK para usuarios sair daqui no
--   futuro, o TRUNCATE dedicado passa a ser obrigatório.
-- ============================================================================


-- ── CNAEs e seu mapeamento ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cnaes (
    codigo       CHAR(7) PRIMARY KEY,           -- só dígitos, sem máscara: 8610101
    descricao    VARCHAR(300) NOT NULL,

    -- O mapeamento. Ambos NULL = CNAE conhecido mas ainda não classificado;
    -- é esse estado que a tela cobra.
    vertical_id  INTEGER REFERENCES verticais(id) ON DELETE SET NULL,
    grau_risco   SMALLINT,                      -- NR-4, Quadro I: 1 a 4

    mapeado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    mapeado_em   TIMESTAMPTZ,

    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_cnaes_codigo CHECK (codigo ~ '^[0-9]{7}$'),
    CONSTRAINT ck_cnaes_descricao CHECK (length(btrim(descricao)) > 0),
    CONSTRAINT ck_cnaes_grau CHECK (grau_risco IS NULL OR grau_risco BETWEEN 1 AND 4),
    -- Mapeamento sem autoria vira mistério — o mesmo raciocínio do
    -- `nao_prospectar_motivo`. Quem classificou uma vertical inteira
    -- precisa ficar registrado.
    CONSTRAINT ck_cnaes_mapeado CHECK (
        (vertical_id IS NULL AND grau_risco IS NULL) OR mapeado_em IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_cnaes_vertical ON cnaes (vertical_id);
CREATE INDEX IF NOT EXISTS idx_cnaes_nao_mapeados
    ON cnaes (codigo) WHERE vertical_id IS NULL AND grau_risco IS NULL;


-- ── Colunas novas em contas ─────────────────────────────────────────────────

ALTER TABLE contas ADD COLUMN IF NOT EXISTS cnae_codigo CHAR(7);
ALTER TABLE contas ADD COLUMN IF NOT EXISTS porte VARCHAR(40);
ALTER TABLE contas ADD COLUMN IF NOT EXISTS situacao_cadastral VARCHAR(40);
ALTER TABLE contas ADD COLUMN IF NOT EXISTS data_abertura DATE;
ALTER TABLE contas ADD COLUMN IF NOT EXISTS capital_social NUMERIC(15,2);
ALTER TABLE contas ADD COLUMN IF NOT EXISTS num_funcionarios_origem VARCHAR(12);
ALTER TABLE contas ADD COLUMN IF NOT EXISTS num_funcionarios_em TIMESTAMPTZ;
ALTER TABLE contas ADD COLUMN IF NOT EXISTS enriquecida_em TIMESTAMPTZ;
ALTER TABLE contas ADD COLUMN IF NOT EXISTS enriquecida_fonte VARCHAR(30);

-- FK e CHECKs em bloco próprio: ADD CONSTRAINT não tem IF NOT EXISTS, então
-- cada um verifica o catálogo antes. É o que torna a migration repetível.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_contas_cnae'
    ) THEN
        ALTER TABLE contas
            ADD CONSTRAINT fk_contas_cnae
            FOREIGN KEY (cnae_codigo) REFERENCES cnaes(codigo) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_contas_num_func_origem'
    ) THEN
        ALTER TABLE contas
            ADD CONSTRAINT ck_contas_num_func_origem
            CHECK (num_funcionarios_origem IS NULL
                   OR num_funcionarios_origem IN ('declarado', 'estimado'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_contas_capital'
    ) THEN
        ALTER TABLE contas
            ADD CONSTRAINT ck_contas_capital
            CHECK (capital_social IS NULL OR capital_social >= 0);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_contas_cnae ON contas (cnae_codigo);
CREATE INDEX IF NOT EXISTS idx_contas_sem_enriquecimento
    ON contas (id) WHERE enriquecida_em IS NULL AND ativo;


-- ── CNAEs secundários da conta ──────────────────────────────────────────────
--
-- N:N. Existe porque a empresa de medicina ocupacional não é comprada pelo
-- CNAE principal: uma indústria com CNAE fiscal de holding e CNAE secundário
-- de metalurgia tem o risco da metalurgia. O principal decide a vertical; os
-- secundários entram na leitura de risco.

CREATE TABLE IF NOT EXISTS conta_cnaes_secundarios (
    conta_id    UUID   NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
    cnae_codigo CHAR(7) NOT NULL REFERENCES cnaes(codigo) ON DELETE CASCADE,
    PRIMARY KEY (conta_id, cnae_codigo)
);

CREATE INDEX IF NOT EXISTS idx_conta_cnaes_sec_cnae
    ON conta_cnaes_secundarios (cnae_codigo);


-- ── Quadro societário ───────────────────────────────────────────────────────
--
-- DOCUMENTO SEMPRE MASCARADO. A Receita entrega `***123456**` nos dados
-- abertos e é assim que fica guardado. Se uma fonte paga devolver o CPF
-- inteiro, `services/enriquecimento/modelo.mascarar_documento()` corta antes
-- de chegar aqui. O CHECK abaixo é a segunda barreira: 11 dígitos seguidos
-- não entram nesta coluna.

CREATE TABLE IF NOT EXISTS conta_socios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conta_id            UUID NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
    nome                VARCHAR(200) NOT NULL,
    -- Chave de casamento da busca reversa: nome sem acento, maiúsculo e com
    -- espaço colapsado. Fica em coluna materializada e não em função no
    -- WHERE para o índice poder ser usado.
    nome_normalizado    VARCHAR(200) NOT NULL,
    documento_mascarado VARCHAR(20),
    qualificacao        VARCHAR(150),
    faixa_etaria        VARCHAR(40),
    entrada_em          DATE,
    eh_pj               BOOLEAN NOT NULL DEFAULT FALSE,
    fonte               VARCHAR(30) NOT NULL,
    capturado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- FK para usuarios: é o que faz o TRUNCATE CASCADE do conftest alcançar
    -- esta tabela. Não é decorativa.
    criado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,

    CONSTRAINT ck_socios_nome CHECK (length(btrim(nome)) > 0),
    CONSTRAINT ck_socios_doc_mascarado CHECK (
        documento_mascarado IS NULL OR documento_mascarado !~ '[0-9]{11}'
    )
);

-- COALESCE no índice único: sócio sem documento (acontece em QSA antigo)
-- casaria com qualquer outro sem documento se o NULL entrasse na chave —
-- em índice único, NULL nunca é igual a NULL, e a mesma pessoa entraria
-- duas vezes a cada reconsulta.
CREATE UNIQUE INDEX IF NOT EXISTS uq_conta_socios
    ON conta_socios (conta_id, nome_normalizado, COALESCE(documento_mascarado, ''));

CREATE INDEX IF NOT EXISTS idx_socios_nome_norm ON conta_socios (nome_normalizado);
CREATE INDEX IF NOT EXISTS idx_socios_documento
    ON conta_socios (documento_mascarado) WHERE documento_mascarado IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_socios_conta ON conta_socios (conta_id);


-- ── Cache e trilha das consultas ────────────────────────────────────────────
--
-- Guarda o payload CRU, inclusive de consulta que falhou. Duas razões:
-- responder "de onde veio esse dado" depois, e não pagar duas vezes pela
-- mesma pergunta dentro do TTL.
--
-- `conta_id` é NULL nas consultas feitas ANTES da conta existir — que é o
-- caso mais comum, porque a consulta acontece no formulário de cadastro.
-- O CNPJ é a chave real.

CREATE TABLE IF NOT EXISTS conta_enriquecimentos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cnpj           CHAR(14) NOT NULL,
    conta_id       UUID REFERENCES contas(id) ON DELETE SET NULL,
    fonte          VARCHAR(30) NOT NULL,
    sucesso        BOOLEAN NOT NULL,
    erro           TEXT,
    payload        JSONB,
    consultado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consultado_por UUID REFERENCES usuarios(id) ON DELETE SET NULL,

    CONSTRAINT ck_enriq_cnpj CHECK (cnpj ~ '^[0-9]{14}$')
);

-- O índice que o cache consulta: última consulta bem-sucedida por (cnpj, fonte).
CREATE INDEX IF NOT EXISTS idx_enriq_cache
    ON conta_enriquecimentos (cnpj, fonte, consultado_em DESC) WHERE sucesso;
CREATE INDEX IF NOT EXISTS idx_enriq_conta ON conta_enriquecimentos (conta_id);
