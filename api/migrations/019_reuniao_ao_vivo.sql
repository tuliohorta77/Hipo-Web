-- =====================================================================
-- HIPO -- 019_reuniao_ao_vivo.sql
--
-- Transcricao AO VIVO da reuniao (prova de conceito do copiloto).
--
-- O QUE MUDA
--   Durante a call, a tela "Reuniao ao vivo" capta o microfone do
--   vendedor e o audio da aba do Meet, transcreve cada um no proprio
--   Chrome (Web Speech API) e manda o texto em lotes. Aqui ele fica,
--   preso a reuniao -- que e uma tarefa.
--
-- DUAS TABELAS
--   reuniao_sessoes_ao_vivo -- cada vez que alguem ligou a captura. Uma
--     reuniao pode ter mais de uma (a aba fechou e o vendedor abriu de
--     novo). Guarda quem, quando, com que navegador, quais canais
--     funcionaram e os erros que o reconhecimento relatou: e o que diz
--     se o Web Speech serve ou nao, que e a pergunta desta entrega.
--   reuniao_falas_ao_vivo -- cada trecho reconhecido, com o CANAL
--     (vendedor = microfone, cliente = aba do Meet).
--
-- IDEMPOTENCIA DO LOTE
--   O navegador numera as falas (`seq`) e reenvia o lote quando a rede
--   falha. UNIQUE (sessao_id, seq) + ON CONFLICT DO NOTHING fazem o
--   reenvio nao duplicar texto.
--
-- NAO SUBSTITUI A TRANSCRICAO DO MEET (016). Ela continua chegando depois
-- da reuniao e passa a ser o GABARITO: a tela compara as duas.
--
-- NAO E DESTRUTIVA: duas tabelas novas e um indice. Nenhum DROP, nenhum
-- DELETE, idempotente. Nao exige o export previo em CSV.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS reuniao_sessoes_ao_vivo (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reuniao_id    UUID NOT NULL REFERENCES reunioes(id) ON DELETE CASCADE,
    -- Quem ligou a captura. RESTRICT: a sessao e registro de quem estava
    -- na call, e apagar o usuario nao pode apagar a conversa por tabela.
    usuario_id    UUID NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    iniciada_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    encerrada_em  TIMESTAMPTZ,
    -- "Chrome 141", para saber em que navegador o reconhecimento falhou.
    navegador     VARCHAR(120),
    -- Os canais que a tela conseguiu ligar: vendedor, cliente ou os dois.
    canais        TEXT[] NOT NULL DEFAULT '{}',
    -- [{canal, erro, em}] relatados pelo reconhecimento do navegador.
    erros         JSONB NOT NULL DEFAULT '[]'::jsonb,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_ao_vivo_canais
        CHECK (canais <@ ARRAY['vendedor', 'cliente']::TEXT[]),
    CONSTRAINT ck_ao_vivo_encerrada_depois
        CHECK (encerrada_em IS NULL OR encerrada_em >= iniciada_em)
);

CREATE INDEX IF NOT EXISTS idx_ao_vivo_sessoes_reuniao
    ON reuniao_sessoes_ao_vivo (reuniao_id, iniciada_em);

CREATE TABLE IF NOT EXISTS reuniao_falas_ao_vivo (
    id         BIGSERIAL PRIMARY KEY,
    sessao_id  UUID NOT NULL REFERENCES reuniao_sessoes_ao_vivo(id) ON DELETE CASCADE,
    -- Numero da fala dentro da sessao, dado pelo navegador.
    seq        INTEGER NOT NULL,
    canal      VARCHAR(10) NOT NULL,
    inicio     TIMESTAMPTZ NOT NULL,
    fim        TIMESTAMPTZ,
    texto      TEXT NOT NULL,
    -- Confianca que o reconhecimento declarou (0 a 1). O Chrome as vezes
    -- manda 0 para tudo; guardado so para a analise da prova de conceito.
    confianca  REAL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ao_vivo_fala_seq UNIQUE (sessao_id, seq),
    CONSTRAINT ck_ao_vivo_fala_canal CHECK (canal IN ('vendedor', 'cliente')),
    CONSTRAINT ck_ao_vivo_fala_seq CHECK (seq >= 0),
    CONSTRAINT ck_ao_vivo_fala_texto CHECK (length(btrim(texto)) > 0)
);

COMMIT;
