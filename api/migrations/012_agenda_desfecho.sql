-- =====================================================================
-- HIPO -- 012_agenda_desfecho.sql
--
-- O rastreio da agenda: quem agendou, e o que aconteceu com a reuniao.
--
-- Responde as duas perguntas que a operacao precisa fechar todo dia:
--
--   "quantos agendamentos por dia, por SDR"   -> reunioes.agendado_por
--   "quantas reunioes por dia, por EV, e com  -> reunioes.desfecho
--    que resultado"
--
-- AGENDADO_POR NAO E CRIADO_POR
--   `criado_por` responde "quem digitou", e e trilha de auditoria: nunca
--   muda, nao se edita, serve para descobrir quem mexeu. `agendado_por`
--   responde "de quem e o credito do agendamento", e e METRICA: o SDR
--   marcou por telefone e o ADM lancou no sistema, e o numero do mes tem
--   que ir para o SDR.
--
--   Sao a mesma pessoa em quase toda linha, e e por isso que a tentacao
--   de usar so `criado_por` e forte. Mas no dia em que divergem -- que e
--   exatamente o dia em que alguem cobre o colega -- a metrica premiaria
--   quem digitou. Duas colunas porque sao duas perguntas.
--
--   O backfill copia criado_por para as linhas que ja existem: e a melhor
--   verdade disponivel sobre elas.
--
-- O DESFECHO E GUARDADO, E NAO SO DEDUZIDO
--   Dava para deduzir tudo de `tarefas` (concluida = realizada; cancelada
--   + relogio = cancelada ou no-show), e services/agenda.desfecho_efetivo
--   faz exatamente isso quando ninguem registrou nada.
--
--   Mas a deducao pura mede A HORA DO CLIQUE, nao a hora do aviso. O
--   cliente avisa segunda uma reuniao de quinta; o EV so registra na
--   quarta; vira "cancelada". O EV que registra na hora um aviso de
--   vespera vira "no-show". O numero passaria a medir quem clica rapido,
--   e sao o SDR e o EV que respondem por ele.
--
--   Entao o formulario PERGUNTA o status e a resposta fica aqui. O
--   relogio nao sai de cena: ele SUGERE a opcao na tela, com a
--   antecedencia escrita ao lado (regra das 24h em
--   services/agenda.desfecho_pelo_relogio).
--
-- NAO EXISTE DESFECHO AUTOMATICO POR TEMPO
--   Reuniao que passou e ninguem marcou fica PENDENTE, aparece num
--   contador na barra e cobra. Virar no-show sozinha depois de N horas
--   fecharia o numero mais rapido, ao preco de inventar um resultado que
--   ninguem afirmou -- e a primeira reuniao que de fato aconteceu e virou
--   no-show por esquecimento destruiria a confianca no relatorio inteiro.
--
-- TIPOS DE REUNIAO: AS SIGLAS CERTAS
--   A semente da 011 era um palpite (so 'Apresentacao' vinha de um convite
--   real). Aqui entram as siglas e os nomes confirmados pela operacao, com
--   acento -- o `nome` vai para o TITULO do evento que o CLIENTE le, e
--   "Diagnostico" sem til numa agenda de cliente parece cadastro torto.
--
--   Por slug, e nao por sigla: a sigla e justamente o que esta mudando.
--
-- NAO E DESTRUTIVA: acrescenta colunas nulaveis e corrige 5 linhas de uma
-- lista de dominio. Nenhum DROP. Idempotente.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Quem agendou
-- ---------------------------------------------------------------------
ALTER TABLE reunioes
    ADD COLUMN IF NOT EXISTS agendado_por UUID REFERENCES usuarios(id) ON DELETE SET NULL;

-- Backfill: para o que ja existe, quem digitou e a melhor verdade que ha.
-- `IS NULL` no WHERE torna o passo idempotente e impede que uma segunda
-- execucao sobrescreva uma correcao feita a mao depois.
UPDATE reunioes SET agendado_por = criado_por WHERE agendado_por IS NULL;

-- "Quantos agendamentos o SDR fez no dia" -- e a pergunta inteira, e ela
-- recorta por criado_em (o dia em que o TRABALHO foi feito), nao pelo dia
-- da reuniao. Por isso as duas colunas no mesmo indice.
CREATE INDEX IF NOT EXISTS idx_reunioes_agendado_por
    ON reunioes (agendado_por, criado_em)
    WHERE agendado_por IS NOT NULL;


-- ---------------------------------------------------------------------
-- 2. O desfecho
-- ---------------------------------------------------------------------
ALTER TABLE reunioes
    ADD COLUMN IF NOT EXISTS desfecho             VARCHAR(12),
    ADD COLUMN IF NOT EXISTS desfecho_em          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS desfecho_por         UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS desfecho_observacao  TEXT,
    -- O que o RELOGIO dizia no momento do registro, guardado ao lado do
    -- que a pessoa escolheu. Nao e desconfianca: e o unico jeito de, seis
    -- meses depois, responder "esse no-show foi avisado com quanto tempo?"
    -- sem reconstruir nada. Quando os dois discordam, ha uma conversa a
    -- ter -- e ela so existe se o par tiver sido guardado.
    ADD COLUMN IF NOT EXISTS desfecho_antecedencia_horas NUMERIC(10,2);

DO $$
BEGIN
    -- Vocabulario fechado, ao contrario de tipos_reuniao: aqui os tres
    -- valores SAO a metrica, e um quarto inventado por alguem quebraria a
    -- soma sem quebrar nada visivel.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_reuniao_desfecho'
    ) THEN
        ALTER TABLE reunioes ADD CONSTRAINT ck_reuniao_desfecho
            CHECK (desfecho IS NULL OR desfecho IN ('realizada', 'cancelada', 'no_show'));
    END IF;

    -- Desfecho registrado sempre sabe QUANDO foi registrado. Sem o par, um
    -- desfecho sem carimbo seria um dado que nao da para auditar nem
    -- ordenar -- e o relatorio de um mes fechado depende dos dois.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_reuniao_desfecho_em'
    ) THEN
        ALTER TABLE reunioes ADD CONSTRAINT ck_reuniao_desfecho_em
            CHECK (
                (desfecho IS NULL     AND desfecho_em IS NULL)
                OR
                (desfecho IS NOT NULL AND desfecho_em IS NOT NULL)
            );
    END IF;
END $$;

-- O relatorio pergunta "as reunioes desta janela, com que desfecho". O
-- recorte por dia vem de `tarefas.prazo` (ja indexado pela 011); este
-- indice serve o filtro por desfecho dentro dela.
CREATE INDEX IF NOT EXISTS idx_reunioes_desfecho
    ON reunioes (desfecho)
    WHERE desfecho IS NOT NULL;


-- ---------------------------------------------------------------------
-- 3. Os tipos de reuniao, confirmados pela operacao
-- ---------------------------------------------------------------------
-- A 011 semeou um palpite. Estes sao os certos, com acento -- o `nome` sai
-- no titulo do evento que o cliente le.
--
-- Por slug: a sigla e o que muda (CD->DG, CF->FC, FUP->FP), entao usa-la
-- como chave aqui erraria o alvo na segunda execucao.
--
-- Sem colisao na UNIQUE de sigla: DG, FC e FP nao existiam antes.
UPDATE tipos_reuniao SET sigla = 'DG', nome = 'Diagnóstico'    WHERE slug = 'diagnostico';
UPDATE tipos_reuniao SET sigla = 'AP', nome = 'Apresentação'   WHERE slug = 'apresentacao';
UPDATE tipos_reuniao SET sigla = 'FC', nome = 'Fechamento'     WHERE slug = 'fechamento';
UPDATE tipos_reuniao SET sigla = 'FP', nome = 'FUP'            WHERE slug = 'follow-up';
UPDATE tipos_reuniao SET sigla = 'VT', nome = 'Visita Técnica' WHERE slug = 'visita-tecnica';

-- Banco novo (CI, provisionamento do zero) nao passou pela 011: o INSERT
-- abaixo garante que ele nasca com a lista certa. Em banco que ja tem os
-- cinco, o ON CONFLICT nao faz nada e quem corrigiu foi o UPDATE acima.
INSERT INTO tipos_reuniao (sigla, nome, slug, ordem) VALUES
    ('DG', 'Diagnóstico',    'diagnostico',    10),
    ('AP', 'Apresentação',   'apresentacao',   20),
    ('FC', 'Fechamento',     'fechamento',     30),
    ('FP', 'FUP',            'follow-up',      40),
    ('VT', 'Visita Técnica', 'visita-tecnica', 50)
ON CONFLICT (slug) DO NOTHING;

COMMIT;
