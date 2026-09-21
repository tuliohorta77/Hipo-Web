-- ============================================================================
-- HIPO — 015: procedência do mapeamento de CNAE
--
-- Aditiva e idempotente. Nenhum DROP, nenhum DELETE.
--
-- POR QUE ESTA COLUNA EXISTE
--
-- A 014 fazia o CNAE nascer sem vertical, esperando alguém classificar um a
-- um. Com centenas de códigos distintos na base, isso é trabalho que não
-- termina — e vertical vazia não classifica nada.
--
-- A partir daqui o CNAE nasce com a vertical DERIVADA da seção da CNAE 2.0
-- (a hierarquia oficial do IBGE: todo código pertence a uma divisão, toda
-- divisão a uma das 21 seções). Isso não é chute: é a estrutura da própria
-- classificação.
--
-- Mas derivado não é o mesmo que decidido por gente, e o sistema precisa
-- saber a diferença por três motivos:
--
--   1. A TELA mostra "sugerido" em vez de afirmar. Quem olha sabe que
--      aquilo veio de uma regra, não de uma decisão comercial.
--   2. A PERMISSÃO muda: corrigir uma sugestão é trabalho operacional, como
--      corrigir qualquer cadastro. Trocar o que uma pessoa já decidiu é de
--      gestão, porque vale para a base inteira. Sem esta coluna, os dois
--      casos seriam indistinguíveis e a regra de gestão travaria a correção
--      de uma sugestão automática.
--   3. Uma futura recarga da derivação pode refazer os 'derivado' sem
--      encostar no que humano decidiu.
--
-- O GRAU DE RISCO CONTINUA NULO. Ele vem do Anexo I da NR-4, que é norma e
-- tem valor por SUBCLASSE — dentro da mesma divisão há código de grau 1 e
-- de grau 4. Derivar grau por seção seria inventar o número que decide
-- dimensionamento de SESMT. Carregar a tabela oficial é passo à parte
-- (scripts/carregar_grau_risco_nr4.py).
-- ============================================================================

ALTER TABLE cnaes ADD COLUMN IF NOT EXISTS mapeamento_origem VARCHAR(12);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_cnaes_origem'
    ) THEN
        ALTER TABLE cnaes
            ADD CONSTRAINT ck_cnaes_origem
            CHECK (mapeamento_origem IS NULL
                   OR mapeamento_origem IN ('derivado', 'humano'));
    END IF;
END
$$;

-- Os CNAEs já classificados ANTES desta migration foram classificados à
-- mão, pela tela — não havia derivação. Marcar como 'humano' preserva essa
-- decisão: sem isto, uma recarga da derivação passaria por cima delas.
UPDATE cnaes
   SET mapeamento_origem = 'humano'
 WHERE mapeamento_origem IS NULL
   AND (vertical_id IS NOT NULL OR grau_risco IS NOT NULL);

-- A fila de trabalho passa a ser "sugestões a confirmar" + "sem nada".
CREATE INDEX IF NOT EXISTS idx_cnaes_origem
    ON cnaes (mapeamento_origem) WHERE mapeamento_origem IS NOT NULL;
