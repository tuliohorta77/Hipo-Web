-- =====================================================================
-- HIPO -- 009_anexos.sql
--
-- Anexo de arquivo na tarefa. O caso que trouxe isto: o print do
-- WhatsApp que prova o relato. "O Marcelo deu retorno via whats" vale
-- mais com a conversa do lado, e hoje esse print vive no celular de
-- quem atendeu -- some quando a pessoa sai.
--
-- O ARQUIVO NAO FICA NO BANCO
--   Vai para o S3 (bucket hipo-anexos-<conta>, privado). Aqui fica so o
--   ponteiro: chave do objeto, nome original, tipo e tamanho. Imagem em
--   bytea incharia o dump do RDS e o storage gp2 e o mais caro por GB
--   dos tres candidatos. E, ao contrario da proposta da 008, este
--   arquivo NAO se reproduz sozinho: um print nao tem como ser
--   remontado a partir de dados, entao ele precisa ser guardado de
--   verdade em algum lugar durave l-- e o S3 e esse lugar.
--
-- POR QUE NAO uma tabela generica de anexos desde ja
--   Anexo de oportunidade (contrato, cartao CNPJ) vai existir, e a
--   tentacao e nascer com `entidade_tipo` + `entidade_id`. FK polimorfica
--   nao tem integridade referencial: nada impede uma linha apontar para
--   um id que nao existe em tabela nenhuma, e o banco nao avisa. Enquanto
--   o alvo e um so, a FK real e melhor. Quando o segundo alvo chegar, a
--   migration de entao acrescenta `oportunidade_id` nulavel com o mesmo
--   CHECK de alvo unico que `tarefas` ja usa -- padrao que este projeto
--   ja tem funcionando.
--
-- CHAVE DO OBJETO E IMUTAVEL
--   `tarefas/<tarefa_id>/<anexo_id>.<ext>`. Derivada de ids, nunca do
--   nome que o usuario mandou: nome de arquivo carrega acento, barra,
--   espaco e ".." -- e um deles vira travessia de caminho no bucket. O
--   nome original fica guardado a parte, so para exibir e para o
--   download sair com o nome que a pessoa reconhece.
--
-- ON DELETE CASCADE, e o orfao que sobra no S3
--   Apagar a tarefa apaga a linha, mas NAO apaga o objeto no S3 -- banco
--   nao fala com bucket. O objeto ficaria orfao, pagando storage para
--   sempre. Hoje isso nao acontece porque nada no HIPO apaga tarefa
--   (historico e imutavel; cancelar nao apaga). Se um dia apagar,
--   precisa varrer o bucket antes. Anotado aqui porque e o tipo de
--   consequencia que ninguem lembra na hora de escrever o DELETE.
--
-- NAO E DESTRUTIVA: so cria. Idempotente.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS tarefa_anexos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tarefa_id       UUID NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,

    -- Chave do objeto no S3. UNIQUE porque duas linhas apontando para o
    -- mesmo objeto fariam a exclusao de uma delas apagar o arquivo da
    -- outra -- e o sintoma apareceria na tela da outra pessoa.
    chave_s3        TEXT NOT NULL UNIQUE,

    -- O nome que a pessoa reconhece. So para exibir e para o download.
    nome_original   VARCHAR(255) NOT NULL,
    tipo_mime       VARCHAR(100) NOT NULL,
    bytes           BIGINT NOT NULL,

    enviado_por     UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- A lista vive no codigo (services/anexo.py) E aqui. Duplicacao de
    -- proposito: a validacao da aplicacao da mensagem boa ao usuario, e
    -- o CHECK impede que um script, um psql a mao ou uma rota futura
    -- gravem um tipo que a tela nao sabe mostrar.
    CONSTRAINT ck_anexo_tipo CHECK (
        tipo_mime IN (
            'image/png', 'image/jpeg', 'image/webp', 'image/gif',
            'application/pdf'
        )
    ),
    CONSTRAINT ck_anexo_bytes CHECK (bytes > 0),
    CONSTRAINT ck_anexo_nome CHECK (length(btrim(nome_original)) > 0)
);

-- A consulta e sempre "os anexos desta tarefa, na ordem em que entraram".
CREATE INDEX IF NOT EXISTS idx_tarefa_anexos_tarefa
    ON tarefa_anexos (tarefa_id, criado_em);

COMMIT;
