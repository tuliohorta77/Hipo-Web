-- ============================================================================
-- HIPO — Schema do banco
--
-- Estado apos a Sprint 1 (CRM nativo de medicina ocupacional).
--
-- Historico:
--   001_drop_legado.sql  removeu PEX, CROmie, BD Ativados, POs e Carteira
--   002_crm_core.sql     criou as 11 tabelas do CRM
--   003_fase_suspect.sql acrescentou a fase 'suspect' na boca do funil
--   004_tarefas.sql      criou a tabela de tarefas do funil
--   005_parceiros.sql    EC responsavel por parceiro + trilha da carteira
--   006_tarefas_parceiro.sql  tarefa presa ao parceiro (alvo alternativo)
--
-- Este arquivo e a fonte usada para criar o banco de teste no CI e deve
-- refletir o estado acumulado das migrations.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- usuarios
-- ---------------------------------------------------------------------------
-- Autenticacao e cargo. 'cargo' e VARCHAR livre; as permissoes por cargo
-- vivem em api/routers/permissions.py (modulos_do_cargo), nao no banco.
--
-- Cargos canonicos: Franqueado | ADM (gestao) e EC | SDR | EV | EP (operacao).
-- Cargos extintos: Gerente (removido), Hunter e Farmer (fundidos em EC).
-- ---------------------------------------------------------------------------
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


-- ---------------------------------------------------------------------------
-- dia_nao_util
-- ---------------------------------------------------------------------------
-- Calendario de feriados e dias sem expediente. Sobreviveu a limpeza da
-- Sprint 0 por ser agnostico ao negocio antigo: sera reaproveitado no calculo
-- de previsao de fechamento e de SLA (api/services/dias_uteis.py).
--
-- CONSEQUENCIA NOS TESTES: por causa da FK para usuarios, um
-- TRUNCATE usuarios CASCADE tambem esvazia dia_nao_util.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dia_nao_util (
    id                     SERIAL PRIMARY KEY,
    data                   DATE NOT NULL UNIQUE,
    motivo                 TEXT NOT NULL,
    criado_por_usuario_id  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dia_nao_util_ano ON dia_nao_util (EXTRACT(YEAR FROM data));


-- ============================================================================
-- CRM  (espelha api/migrations/002_crm_core.sql)
-- ============================================================================

-- Busca por trecho de razao social usa ILIKE '%x%'; sem trigram isso vira
-- seq scan. pg_trgm esta disponivel no RDS e na imagem postgres:15 do CI.
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ---------------------------------------------------------------------------
-- Listas de dominio
-- ---------------------------------------------------------------------------
-- Nascem vazias. Qualquer usuario com o modulo 'crm' cria pelo proprio
-- combobox. O slug normalizado (services/texto.py) e UNIQUE: um POST com
-- slug ja existente devolve o registro existente em vez de 409.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verticais (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    slug        VARCHAR(120) NOT NULL UNIQUE,
    criado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS origens (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    slug        VARCHAR(120) NOT NULL UNIQUE,
    criado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concorrentes (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    slug        VARCHAR(120) NOT NULL UNIQUE,
    criado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Duas listas logicas separadas por 'tipo', como decidido:
--   'perda'        -> por que o cliente recusou (entra na taxa de conversao)
--   'cancelamento' -> erro nosso de CRM (fica FORA da taxa de conversao)
CREATE TABLE IF NOT EXISTS motivos_desfecho (
    id          SERIAL PRIMARY KEY,
    tipo        VARCHAR(20) NOT NULL,
    nome        VARCHAR(120) NOT NULL,
    slug        VARCHAR(120) NOT NULL,
    criado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_motivo_tipo CHECK (tipo IN ('perda', 'cancelamento')),
    CONSTRAINT uq_motivo_tipo_slug UNIQUE (tipo, slug)
);


-- ---------------------------------------------------------------------------
-- contas  (empresa-cliente)
-- ---------------------------------------------------------------------------
-- CNPJ e armazenado so com digitos (CHAR(14)) e e UNIQUE. A validacao de
-- digito verificador vive em services/cnpj.py; o CHECK aqui garante apenas
-- que nada alem de digito entre na coluna.
--
-- NAO existe coluna de vendedor: o "vendedor da conta" e derivado na leitura
-- a partir dos EVs das oportunidades com status='ativa'.
--
-- eh_finder marca a conta como parceira indicadora (ex.: escritorio de
-- contabilidade). E ligado automaticamente na primeira vez que a conta e
-- usada como finder_conta_id de uma oportunidade, e tambem pode ser ligado
-- a mao -- e o que permite prospectar um contador antes da primeira
-- indicacao e acompanhar "parceiro que ainda nao indicou nada".
--
-- ec_responsavel_id e o EC dono da relacao de parceria (Sprint 6). Fica em
-- contas, e nao numa tabela de vinculo, porque a relacao e 1:1 a cada
-- momento; o historico de quem foi dono quando vive em parceiro_eventos.
-- O CHECK amarra o campo ao eh_finder: desmarcar o parceiro TEM que limpar o
-- responsavel na mesma transacao, senao o banco recusa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contas (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    razao_social      VARCHAR(200) NOT NULL,
    nome_fantasia     VARCHAR(200),
    cnpj              CHAR(14) NOT NULL UNIQUE,
    vertical_id       INTEGER REFERENCES verticais(id) ON DELETE SET NULL,
    num_funcionarios  INTEGER,
    cep               CHAR(8),
    logradouro        VARCHAR(200),
    numero            VARCHAR(20),
    complemento       VARCHAR(100),
    bairro            VARCHAR(100),
    cidade            VARCHAR(100),
    uf                CHAR(2),
    telefone          VARCHAR(20),
    telefone_2        VARCHAR(20),
    email             VARCHAR(150),
    eh_finder         BOOLEAN NOT NULL DEFAULT FALSE,
    ec_responsavel_id UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    observacoes       TEXT,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    criado_por        UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_contas_cnpj       CHECK (cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT ck_contas_cep        CHECK (cep IS NULL OR cep ~ '^[0-9]{8}$'),
    CONSTRAINT ck_contas_uf         CHECK (uf IS NULL OR uf ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_contas_num_func   CHECK (num_funcionarios IS NULL OR num_funcionarios >= 0),
    CONSTRAINT ck_contas_razao      CHECK (length(btrim(razao_social)) > 0),
    CONSTRAINT ck_contas_ec_so_parceiro CHECK (ec_responsavel_id IS NULL OR eh_finder)
);

CREATE INDEX IF NOT EXISTS idx_contas_razao_trgm  ON contas USING gin (razao_social gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contas_fantasia_trgm ON contas USING gin (nome_fantasia gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contas_vertical    ON contas (vertical_id);
CREATE INDEX IF NOT EXISTS idx_contas_finder      ON contas (eh_finder) WHERE eh_finder;
CREATE INDEX IF NOT EXISTS idx_contas_ativo       ON contas (ativo) WHERE ativo;

-- Parcial: a esmagadora maioria das contas nao e parceira e nunca vai ter
-- responsavel. Serve a pergunta "quais sao os parceiros do EC X".
CREATE INDEX IF NOT EXISTS idx_contas_ec_responsavel
    ON contas (ec_responsavel_id) WHERE ec_responsavel_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- contatos  +  conta_contatos  (N:N)
-- ---------------------------------------------------------------------------
-- Contato e entidade independente: a mesma pessoa pode estar vinculada a mais
-- de uma conta. O vinculo carrega o cargo daquela pessoa naquela empresa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contatos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome             VARCHAR(150) NOT NULL,
    telefone         VARCHAR(20),
    email            VARCHAR(150),
    data_nascimento  DATE,
    observacoes      TEXT,
    ativo            BOOLEAN NOT NULL DEFAULT TRUE,
    criado_por       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_contatos_nome CHECK (length(btrim(nome)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_contatos_nome_trgm ON contatos USING gin (nome gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contatos_email     ON contatos (lower(email));
CREATE INDEX IF NOT EXISTS idx_contatos_telefone  ON contatos (telefone);

CREATE TABLE IF NOT EXISTS conta_contatos (
    conta_id    UUID NOT NULL REFERENCES contas(id)   ON DELETE CASCADE,
    contato_id  UUID NOT NULL REFERENCES contatos(id) ON DELETE CASCADE,
    cargo       VARCHAR(100),
    principal   BOOLEAN NOT NULL DEFAULT FALSE,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (conta_id, contato_id)
);

-- No maximo um contato principal por conta (entre os vinculos ativos).
CREATE UNIQUE INDEX IF NOT EXISTS uq_conta_contato_principal
    ON conta_contatos (conta_id) WHERE principal AND ativo;

CREATE INDEX IF NOT EXISTS idx_conta_contatos_contato ON conta_contatos (contato_id);


-- ---------------------------------------------------------------------------
-- oportunidades
-- ---------------------------------------------------------------------------
-- Numeracao propria via sequence: OPP-<ano>-<5 digitos>. O ano vem do
-- momento da criacao e a sequence e global (nao reinicia por ano) — o que
-- garante unicidade sem risco de colisao sob concorrencia.
--
-- INVARIANTE CENTRAL (ck_opp_fase_status):
--   ativa | suspensa                     -> fase <> 'finalizado'
--   perdido | cancelado | conquistado    -> fase =  'finalizado'
--
-- fase_desfecho guarda a fase imediatamente anterior ao Finalizado. E o que
-- permite medir em qual fase se perde e de qual fase vem o ganho.
--
-- Temperatura: 0..90 em passos de 10, obrigatoria enquanto a oportunidade
-- esta ativa e ignorada nos demais status (o valor antigo e preservado).
-- ---------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS oportunidade_numero_seq AS BIGINT START WITH 1;

CREATE TABLE IF NOT EXISTS oportunidades (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero              VARCHAR(20) NOT NULL UNIQUE,
    conta_id            UUID NOT NULL REFERENCES contas(id)   ON DELETE RESTRICT,
    contato_id          UUID REFERENCES contatos(id)          ON DELETE SET NULL,
    fase                VARCHAR(20) NOT NULL DEFAULT 'suspect',
    status              VARCHAR(20) NOT NULL DEFAULT 'ativa',
    fase_desfecho       VARCHAR(20),
    motivo_desfecho_id  INTEGER REFERENCES motivos_desfecho(id) ON DELETE SET NULL,
    valor_mensalidade   NUMERIC(12,2),
    temperatura         SMALLINT,
    previsao_fechamento DATE,
    descricao           TEXT,
    observacoes         TEXT,
    origem_id           INTEGER REFERENCES origens(id) ON DELETE SET NULL,
    finder_conta_id     UUID REFERENCES contas(id)     ON DELETE SET NULL,
    proxima_acao_em     TIMESTAMPTZ,
    proxima_acao_tipo   VARCHAR(50),
    criado_por          UUID REFERENCES usuarios(id)   ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_opp_fase CHECK (
        fase IN ('suspect', 'lead', 'qualificacao', 'apresentacao',
                 'negociacao', 'finalizado')
    ),
    CONSTRAINT ck_opp_status CHECK (
        status IN ('ativa', 'suspensa', 'perdido', 'cancelado', 'conquistado')
    ),
    CONSTRAINT ck_opp_fase_status CHECK (
        (status IN ('ativa', 'suspensa')                    AND fase <> 'finalizado')
        OR
        (status IN ('perdido', 'cancelado', 'conquistado')  AND fase =  'finalizado')
    ),
    -- Finalizado sempre sabe de onde veio; nao-finalizado nunca tem desfecho.
    CONSTRAINT ck_opp_fase_desfecho CHECK (
        (fase = 'finalizado' AND fase_desfecho IN (
            'suspect','lead','qualificacao','apresentacao','negociacao'))
        OR
        (fase <> 'finalizado' AND fase_desfecho IS NULL)
    ),
    -- Perda e cancelamento exigem motivo; conquista nao.
    CONSTRAINT ck_opp_motivo CHECK (
        status NOT IN ('perdido', 'cancelado') OR motivo_desfecho_id IS NOT NULL
    ),
    CONSTRAINT ck_opp_temperatura CHECK (
        temperatura IS NULL OR (temperatura BETWEEN 0 AND 90 AND temperatura % 10 = 0)
    ),
    CONSTRAINT ck_opp_temperatura_ativa CHECK (
        status <> 'ativa' OR temperatura IS NOT NULL
    ),
    CONSTRAINT ck_opp_valor CHECK (
        valor_mensalidade IS NULL OR valor_mensalidade >= 0
    ),
    -- Uma conta nao indica a si mesma.
    CONSTRAINT ck_opp_finder_nao_e_a_conta CHECK (
        finder_conta_id IS NULL OR finder_conta_id <> conta_id
    )
);

CREATE INDEX IF NOT EXISTS idx_opp_conta       ON oportunidades (conta_id);
CREATE INDEX IF NOT EXISTS idx_opp_contato     ON oportunidades (contato_id);
CREATE INDEX IF NOT EXISTS idx_opp_fase_status ON oportunidades (fase, status);
CREATE INDEX IF NOT EXISTS idx_opp_ativas      ON oportunidades (conta_id) WHERE status = 'ativa';
CREATE INDEX IF NOT EXISTS idx_opp_finder      ON oportunidades (finder_conta_id) WHERE finder_conta_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_opp_previsao    ON oportunidades (previsao_fechamento);
CREATE INDEX IF NOT EXISTS idx_opp_proxima     ON oportunidades (proxima_acao_em) WHERE proxima_acao_em IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Relacionamentos da oportunidade
-- ---------------------------------------------------------------------------
-- Um mesmo usuario pode aparecer com mais de um papel (ex.: quem prospectou
-- como SDR e tocou como EV), por isso a PK inclui o papel.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oportunidade_envolvidos (
    oportunidade_id  UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    usuario_id       UUID NOT NULL REFERENCES usuarios(id)      ON DELETE CASCADE,
    papel            VARCHAR(10) NOT NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (oportunidade_id, usuario_id, papel),
    CONSTRAINT ck_envolvido_papel CHECK (papel IN ('EC', 'SDR', 'EV'))
);

CREATE INDEX IF NOT EXISTS idx_envolvidos_usuario ON oportunidade_envolvidos (usuario_id);
CREATE INDEX IF NOT EXISTS idx_envolvidos_ev      ON oportunidade_envolvidos (oportunidade_id) WHERE papel = 'EV';

CREATE TABLE IF NOT EXISTS oportunidade_concorrentes (
    oportunidade_id  UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    concorrente_id   INTEGER NOT NULL REFERENCES concorrentes(id) ON DELETE CASCADE,
    PRIMARY KEY (oportunidade_id, concorrente_id)
);

-- Trilha de auditoria: toda mudanca de fase/status vira uma linha aqui.
-- E a base do "proxima tarefa" da Etapa 5 e das metricas de tempo por fase.
CREATE TABLE IF NOT EXISTS oportunidade_eventos (
    id               BIGSERIAL PRIMARY KEY,
    oportunidade_id  UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    tipo             VARCHAR(30) NOT NULL,
    de               VARCHAR(30),
    para             VARCHAR(30),
    usuario_id       UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_evento_tipo CHECK (tipo IN ('fase', 'status', 'criacao', 'reabertura'))
);

CREATE INDEX IF NOT EXISTS idx_eventos_opp ON oportunidade_eventos (oportunidade_id, criado_em DESC);


-- ---------------------------------------------------------------------------
-- usuarios_preferencias
-- ---------------------------------------------------------------------------
-- Preferencias de UI persistidas no banco, nao no localStorage — o HIPO e a
-- fonte primaria. Ex.: crm_oportunidades_visao = 'tabela' | 'kanban'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios_preferencias (
    usuario_id     UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    chave          VARCHAR(60) NOT NULL,
    valor          TEXT NOT NULL,
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (usuario_id, chave)
);


-- ---------------------------------------------------------------------------
-- tarefas  (espelha api/migrations/004_tarefas.sql + 006_tarefas_parceiro.sql)
-- ---------------------------------------------------------------------------
-- Toda tarefa tem EXATAMENTE UM alvo: uma oportunidade ou um parceiro (conta).
-- Nunca zero, nunca os dois -- ck_tarefa_alvo. Zero alvos seria a lista de
-- afazeres pessoal que a Sprint 5 recusou de proposito; dois alvos tornaria
-- ambiguo em qual funil a tarefa conta.
--
-- SITUACAO NAO E COLUNA. E derivada de prazo + concluida_em + cancelada_em
-- mais o relogio (services/tarefa.py):
--     cancelada / concluida / atrasada / hoje / futura
-- Guardar 'atrasada' numa coluna exigiria um job virando o estado a
-- meia-noite, e qualquer falha do job produziria dado mentiroso.
--
-- tarefa_anterior_id forma a corrente de follow-up: concluir obriga a criar a
-- proxima (regra na API), e a nova aponta para a que a gerou. A obrigacao vale
-- para tarefa de OPORTUNIDADE; na de parceiro a proxima e oferecida, nao
-- exigida -- parceria nao tem estado final, e exigir a proxima para sempre
-- produziria corrente infinita de tarefa de mentira. Quem cobra cadencia ali
-- e o farol semanal, que fica vermelho sozinho.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tarefas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id     UUID REFERENCES oportunidades(id) ON DELETE CASCADE,
    conta_id            UUID REFERENCES contas(id) ON DELETE CASCADE,
    tipo                VARCHAR(20) NOT NULL,
    titulo              VARCHAR(200) NOT NULL,
    descricao           TEXT,
    responsavel_id      UUID NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    prazo               TIMESTAMPTZ NOT NULL,
    concluida_em        TIMESTAMPTZ,
    resultado           TEXT,
    cancelada_em        TIMESTAMPTZ,
    motivo_cancelamento TEXT,
    tarefa_anterior_id  UUID REFERENCES tarefas(id) ON DELETE SET NULL,
    criado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tarefa_tipo CHECK (
        tipo IN ('ligacao', 'reuniao', 'visita', 'proposta',
                 'email', 'whatsapp', 'outro')
    ),
    CONSTRAINT ck_tarefa_titulo CHECK (length(btrim(titulo)) > 0),
    CONSTRAINT ck_tarefa_desfecho_unico CHECK (
        concluida_em IS NULL OR cancelada_em IS NULL
    ),
    CONSTRAINT ck_tarefa_resultado CHECK (
        resultado IS NULL OR concluida_em IS NOT NULL
    ),
    CONSTRAINT ck_tarefa_motivo_cancelamento CHECK (
        motivo_cancelamento IS NULL OR cancelada_em IS NOT NULL
    ),
    CONSTRAINT ck_tarefa_corrente CHECK (
        tarefa_anterior_id IS NULL OR tarefa_anterior_id <> id
    ),
    -- Exatamente um alvo. Ver o comentario do bloco.
    CONSTRAINT ck_tarefa_alvo CHECK (
        num_nonnulls(oportunidade_id, conta_id) = 1
    )
);

CREATE INDEX IF NOT EXISTS idx_tarefas_oportunidade
    ON tarefas (oportunidade_id, prazo);

-- Aba de tarefas do parceiro.
CREATE INDEX IF NOT EXISTS idx_tarefas_conta
    ON tarefas (conta_id, prazo)
    WHERE conta_id IS NOT NULL;

-- Farol semanal. Olha concluida_em (quando o contato ACONTECEU), nao prazo.
CREATE INDEX IF NOT EXISTS idx_tarefas_conta_concluidas
    ON tarefas (conta_id, concluida_em)
    WHERE conta_id IS NOT NULL AND concluida_em IS NOT NULL;

-- Indice que a "proxima tarefa" da Etapa 5 vai usar. Parcial: tarefa fechada
-- nunca entra nessa consulta.
CREATE INDEX IF NOT EXISTS idx_tarefas_abertas
    ON tarefas (responsavel_id, prazo)
    WHERE concluida_em IS NULL AND cancelada_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_tarefas_abertas_por_opp
    ON tarefas (oportunidade_id)
    WHERE concluida_em IS NULL AND cancelada_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_tarefas_anterior
    ON tarefas (tarefa_anterior_id)
    WHERE tarefa_anterior_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- parceiro_eventos  (trilha da carteira de parceiros -- Sprint 6)
-- ---------------------------------------------------------------------------
-- Mesma escolha de oportunidade_eventos: sem registrar a transicao, "de quem
-- era essa carteira em marco" vira pergunta sem resposta, e esse dado nao da
-- para reconstruir depois.
--
-- Transferencia em massa grava uma linha POR PARCEIRO, nao uma por lote: o
-- que interessa depois e a historia de cada parceiro, nao a do clique.
--
-- O CHECK rigoroso de forma (amarrar de/para a cada tipo) NAO esta aqui de
-- proposito: as duas FKs sao ON DELETE SET NULL, e apagar um usuario
-- dispararia um UPDATE que reavalia o CHECK e travaria a exclusao. A forma
-- correta de cada evento e responsabilidade da API, que e quem escreve.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parceiro_eventos (
    id               BIGSERIAL PRIMARY KEY,
    conta_id         UUID NOT NULL REFERENCES contas(id)   ON DELETE CASCADE,
    tipo             VARCHAR(20) NOT NULL,
    de_usuario_id    UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    para_usuario_id  UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    usuario_id       UUID REFERENCES usuarios(id)          ON DELETE SET NULL,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_parceiro_evento_tipo CHECK (
        tipo IN ('marcado', 'desmarcado', 'atribuido', 'transferido', 'removido')
    ),
    CONSTRAINT ck_parceiro_evento_de_para CHECK (
        de_usuario_id IS NULL OR de_usuario_id <> para_usuario_id
    )
);

CREATE INDEX IF NOT EXISTS idx_parceiro_eventos_conta
    ON parceiro_eventos (conta_id, criado_em DESC);

CREATE INDEX IF NOT EXISTS idx_parceiro_eventos_para
    ON parceiro_eventos (para_usuario_id)
    WHERE para_usuario_id IS NOT NULL;


-- ===========================================================================
-- TELEMETRIA DE USO E FECHAMENTO DIARIO  (migration 007)
-- ===========================================================================
-- Espelha api/migrations/007_telemetria.sql. O CI monta o banco de teste com
-- `psql -f api/schema.sql`, NAO com as migrations: migration que nao chega
-- aqui derruba toda a suite que usa `db_conn`, porque o conftest trunca
-- `relatorios_diarios` na fixture.
--
-- POR QUE UMA TABELA DE REQUESTS E NAO SO EVENTOS DE NEGOCIO
--   As trilhas que ja existem (oportunidade_eventos, parceiro_eventos,
--   tarefas) respondem "o que mudou". Nao respondem "quem abriu o sistema e
--   nao fez nada", que e o sintoma que antecede o abandono de uma ferramenta
--   interna. uso_eventos responde adocao; as trilhas respondem resultado.
--
-- O QUE NAO ENTRA, DE PROPOSITO
--   Corpo de request, querystring e headers. Guardamos o TEMPLATE da rota
--   (/crm/contas/{conta_id}), nunca o path com o id preenchido: uma busca por
--   CNPJ viraria dado pessoal num log sem o mesmo cuidado de acesso que a
--   tabela de origem.
--
-- CARGO DESNORMALIZADO
--   Copiado no momento do uso. Quem muda de cargo nao reescreve o passado: o
--   que a pessoa fez como SDR nao vira retroativamente acao de EC.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS uso_eventos (
    id           BIGSERIAL PRIMARY KEY,
    usuario_id   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    cargo        VARCHAR(80),
    metodo       VARCHAR(10)  NOT NULL,
    rota         VARCHAR(200) NOT NULL,
    modulo       VARCHAR(40),
    status       SMALLINT     NOT NULL,
    duracao_ms   INTEGER      NOT NULL,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_uso_status  CHECK (status BETWEEN 100 AND 599),
    CONSTRAINT ck_uso_duracao CHECK (duracao_ms >= 0)
);

-- O relatorio sempre recorta por dia; sustenta as agregacoes e o DELETE da
-- retencao.
CREATE INDEX IF NOT EXISTS idx_uso_eventos_criado
    ON uso_eventos (criado_em DESC);

-- "o que a pessoa X fez hoje" -- a secao por colaborador do relatorio.
CREATE INDEX IF NOT EXISTS idx_uso_eventos_usuario
    ON uso_eventos (usuario_id, criado_em DESC)
    WHERE usuario_id IS NOT NULL;

-- "quais telas sao usadas" e "onde da erro".
CREATE INDEX IF NOT EXISTS idx_uso_eventos_rota
    ON uso_eventos (rota, criado_em DESC);

COMMENT ON TABLE uso_eventos IS
    'Uma linha por request autenticada. Rota e o template, nunca o path com ids.';


-- ---------------------------------------------------------------------------
-- relatorios_diarios -- o fechamento de cada dia
-- ---------------------------------------------------------------------------
-- Uma linha por dia, com as metricas congeladas em JSONB. Guardar o numero
-- fechado (e nao so recalcular na hora) e o que permite comparar ontem com
-- hoje depois que a retencao ja apagou os eventos brutos.
--
-- 'narrativa' e o texto gerado pela IA. Fica NULL quando a chave nao esta
-- configurada, quando a chamada falhou ou quando a validacao numerica
-- descartou o texto -- o relatorio sai assim mesmo, so com os numeros. A IA
-- e enfeite util, nao dependencia.
--
-- NAO tem FK para usuarios, entao o TRUNCATE CASCADE do conftest nao a
-- alcanca: a fixture a trunca explicitamente.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS relatorios_diarios (
    dia               DATE PRIMARY KEY,
    metricas          JSONB       NOT NULL,
    narrativa         TEXT,
    narrativa_modelo  VARCHAR(60),
    destinatarios     TEXT[],
    enviado_em        TIMESTAMPTZ,
    erro              TEXT,
    gerado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relatorios_diarios_dia
    ON relatorios_diarios (dia DESC);

COMMENT ON COLUMN relatorios_diarios.metricas IS
    'Snapshot fechado do dia. Sobrevive a retencao de uso_eventos.';
