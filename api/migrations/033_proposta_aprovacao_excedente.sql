-- =====================================================================
-- HIPO -- 033_proposta_aprovacao_excedente.sql
--
-- Proposta: valor por vida excedente e aprovacao do EV (entrega 051).
--
--   1. valor_vida_excedente -- na modalidade tabela, o que o cliente paga
--      por vida acima do plano escolhido. Campo do EV (sugestao: o valor
--      da faixa aberta da tabela). Sai no rodape do slide. Na modalidade
--      por vida fica NULL: o excedente e o proprio valor por vida.
--
--   2. aprovada_em / aprovada_por -- o "ok" do EV depois de ver a
--      proposta no visualizador do HIPO. So proposta aprovada pode ir
--      anexada no e-mail. Proposta enviada sem ninguem ter olhado o
--      arquivo e o que esta trava existe para impedir.
--
-- Backfill:
--   * propostas JA EXISTENTES entram como aprovadas, com a data e o autor
--     da geracao: ate hoje elas eram baixadas, abertas e enviadas -- a
--     conferencia aconteceu fora do HIPO. Sem isto, o e-mail deixaria de
--     anexar versoes que ja estao com o cliente.
--   * na modalidade tabela, o excedente vem da faixa aberta da copia da
--     tabela que a proposta guardou (era o que o rodape da 042 dizia).
--
-- ADITIVA E IDEMPOTENTE: ADD COLUMN IF NOT EXISTS; os UPDATEs so tocam
-- linha com o campo vazio. Nenhum DROP, DELETE ou TRUNCATE. Sem
-- BEGIN/COMMIT: quem abre a transacao e o scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE propostas
    ADD COLUMN IF NOT EXISTS valor_vida_excedente NUMERIC(12,2);
ALTER TABLE propostas
    ADD COLUMN IF NOT EXISTS aprovada_em TIMESTAMPTZ;
ALTER TABLE propostas
    ADD COLUMN IF NOT EXISTS aprovada_por UUID REFERENCES usuarios(id) ON DELETE SET NULL;

ALTER TABLE propostas DROP CONSTRAINT IF EXISTS ck_proposta_excedente;
ALTER TABLE propostas ADD CONSTRAINT ck_proposta_excedente
    CHECK (valor_vida_excedente IS NULL OR valor_vida_excedente > 0);

UPDATE propostas
   SET aprovada_em = criado_em, aprovada_por = criado_por
 WHERE aprovada_em IS NULL;

UPDATE propostas p
   SET valor_vida_excedente = (
        SELECT (f->>'valor')::numeric
          FROM jsonb_array_elements(p.tabela_preco) f
         WHERE f->>'vidas_ate' IS NULL AND f->>'tipo' = 'por_vida'
         LIMIT 1
       )
 WHERE p.modalidade = 'tabela'
   AND p.valor_vida_excedente IS NULL
   AND p.tabela_preco IS NOT NULL;
