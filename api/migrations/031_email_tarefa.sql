-- =====================================================================
-- HIPO -- 031_email_tarefa.sql
--
-- O e-mail enviado pelo HIPO vira tarefa concluida (entrega 050c).
--
--   Todo envio da aba E-mails passa a gravar, na mesma transacao, uma
--   tarefa JA CONCLUIDA da oportunidade (tipo 'email', ou 'proposta' quando
--   vai com o PDF de uma versao), em nome de quem enviou e com o contato.
--   E o que faz o envio aparecer na lista de tarefas, na linha do tempo e
--   na producao do mes. emails_enviados.tarefa_id aponta para ela.
--
--   Backfill: os e-mails ja enviados ganham a tarefa agora, com a data do
--   envio. Mesma regra de services/email_comercial.tarefa_do_envio.
--
-- ADITIVA E IDEMPOTENTE: ADD COLUMN IF NOT EXISTS; o backfill so pega
-- e-mail sem tarefa. Nenhum DROP, DELETE ou TRUNCATE. Sem BEGIN/COMMIT:
-- quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE emails_enviados
    ADD COLUMN IF NOT EXISTS tarefa_id UUID REFERENCES tarefas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_emails_tarefa ON emails_enviados (tarefa_id);

DO $$
DECLARE
    e RECORD;
    nova UUID;
BEGIN
    FOR e IN
        SELECT em.*, p.versao AS proposta_versao
          FROM emails_enviados em
          LEFT JOIN propostas p ON p.id = em.proposta_id
         WHERE em.tarefa_id IS NULL
         ORDER BY em.enviado_em
    LOOP
        INSERT INTO tarefas (
            oportunidade_id, tipo, titulo, descricao, responsavel_id, prazo,
            criado_por, concluida_em, resultado, contato_id
        )
        VALUES (
            e.oportunidade_id,
            CASE WHEN e.proposta_versao IS NOT NULL THEN 'proposta' ELSE 'email' END,
            left(
                CASE WHEN e.proposta_versao IS NOT NULL
                     THEN 'Proposta v' || e.proposta_versao || ' enviada por e-mail'
                     ELSE 'E-mail enviado: ' || regexp_replace(btrim(e.assunto), '\s+', ' ', 'g')
                END, 200),
            e.corpo,
            e.remetente_id,
            e.enviado_em,
            e.remetente_id,
            e.enviado_em,
            'Enviado pelo HIPO para ' || array_to_string(e.para, ', ')
                || CASE WHEN cardinality(e.cc) > 0
                        THEN ' (cc ' || array_to_string(e.cc, ', ') || ')' ELSE '' END
                || COALESCE(' · anexo ' || e.anexo_nome, ''),
            e.contato_id
        )
        RETURNING id INTO nova;

        UPDATE emails_enviados SET tarefa_id = nova WHERE id = e.id;
    END LOOP;
END
$$;
