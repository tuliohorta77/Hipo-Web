-- =====================================================================
-- HIPO -- 004_tarefas.sql
--
-- Tarefas do funil: o que foi feito, o que esta em aberto e o que vem.
--
-- DECISOES QUE ESTA TABELA MATERIALIZA
--
-- 1) Toda tarefa pertence a UMA oportunidade (NOT NULL).
--    Sem isso a tarefa vira lista de afazeres pessoal e para de servir para
--    metrica de funil. Tarefa de relacionamento com conta sem oportunidade
--    aberta fica de fora por enquanto -- e item consciente de backlog.
--
-- 2) Situacao NAO e coluna. E derivada de tres campos (prazo, concluida_em,
--    cancelada_em) mais o relogio:
--
--        cancelada_em  IS NOT NULL              -> cancelada
--        concluida_em  IS NOT NULL              -> concluida
--        prazo < agora                          -> atrasada
--        prazo no dia de hoje                   -> hoje
--        senao                                  -> futura
--
--    Guardar 'atrasada' numa coluna exigiria um job para virar o estado a
--    meia-noite, e qualquer falha do job produziria dado mentiroso. Derivar
--    e sempre verdade.
--
-- 3) tarefa_anterior_id forma a CORRENTE de follow-up.
--    Concluir uma tarefa obriga a criar a proxima (regra na API), e a nova
--    aponta para a que a gerou. E isso que permite reconstruir depois "quanto
--    tempo essa negociacao levou entre um contato e outro" sem inferir nada.
--
-- 4) resultado e OPCIONAL.
--    Duas obrigatoriedades no mesmo clique (dizer o que aconteceu E marcar a
--    proxima) viram texto de mentirinha. A obrigatoria e a proxima tarefa,
--    porque e ela que impede a oportunidade de parar.
--
-- NAO E DESTRUTIVA: so cria tabela, tipo e indices. Nenhum DROP.
-- Idempotente: pode rodar duas vezes.
-- =====================================================================

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.oportunidades') IS NULL THEN
        RAISE EXCEPTION 'Tabela oportunidades nao existe. Rode 002_crm_core.sql antes.';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS tarefas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oportunidade_id     UUID NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,

    tipo                VARCHAR(20) NOT NULL,
    titulo              VARCHAR(200) NOT NULL,
    descricao           TEXT,

    responsavel_id      UUID NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    prazo               TIMESTAMPTZ NOT NULL,

    concluida_em        TIMESTAMPTZ,
    resultado           TEXT,
    cancelada_em        TIMESTAMPTZ,
    motivo_cancelamento TEXT,

    -- Qual tarefa gerou esta. NULL na primeira da corrente.
    tarefa_anterior_id  UUID REFERENCES tarefas(id) ON DELETE SET NULL,

    criado_por          UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_tarefa_tipo CHECK (
        tipo IN ('ligacao', 'reuniao', 'visita', 'proposta',
                 'email', 'whatsapp', 'outro')
    ),

    CONSTRAINT ck_tarefa_titulo CHECK (length(btrim(titulo)) > 0),

    -- Concluida e cancelada sao mutuamente exclusivas. Sem este CHECK daria
    -- para ter os dois carimbos e a situacao derivada viraria ambigua.
    CONSTRAINT ck_tarefa_desfecho_unico CHECK (
        concluida_em IS NULL OR cancelada_em IS NULL
    ),

    -- Resultado e observacao do que aconteceu: so faz sentido em tarefa
    -- concluida.
    CONSTRAINT ck_tarefa_resultado CHECK (
        resultado IS NULL OR concluida_em IS NOT NULL
    ),

    CONSTRAINT ck_tarefa_motivo_cancelamento CHECK (
        motivo_cancelamento IS NULL OR cancelada_em IS NOT NULL
    ),

    -- Uma tarefa nao pode ser a propria antecessora.
    CONSTRAINT ck_tarefa_corrente CHECK (
        tarefa_anterior_id IS NULL OR tarefa_anterior_id <> id
    )
);

-- Listagem da aba: tudo daquela oportunidade, na ordem do prazo.
CREATE INDEX IF NOT EXISTS idx_tarefas_oportunidade
    ON tarefas (oportunidade_id, prazo);

-- O indice que a "proxima tarefa" da Etapa 5 vai usar: para um responsavel,
-- a aberta de menor prazo. Parcial porque tarefa fechada nunca entra nessa
-- consulta, e o indice fica pequeno mesmo com anos de historico.
CREATE INDEX IF NOT EXISTS idx_tarefas_abertas
    ON tarefas (responsavel_id, prazo)
    WHERE concluida_em IS NULL AND cancelada_em IS NULL;

-- Contagem de abertas por oportunidade (badge da aba, futuro alerta de
-- oportunidade parada).
CREATE INDEX IF NOT EXISTS idx_tarefas_abertas_por_opp
    ON tarefas (oportunidade_id)
    WHERE concluida_em IS NULL AND cancelada_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_tarefas_anterior
    ON tarefas (tarefa_anterior_id)
    WHERE tarefa_anterior_id IS NOT NULL;

COMMIT;

-- Conferencia -----------------------------------------------------------
--   \d tarefas
--   SELECT conname FROM pg_constraint WHERE conrelid = 'tarefas'::regclass;
