-- =====================================================================
-- HIPO -- 038_contrato_aviso.sql
--
-- Aviso de contrato assinado para faturamento, contratos e ADM (054).
--
-- Quando o ultimo signatario assina, o HIPO manda um e-mail com o PDF
-- assinado e o resumo do negocio para a lista CONTRATO_AVISO_DESTINATARIOS
-- do .env, saindo do Gmail do executivo da proposta.
--
--   aviso_enviado_em  -- quando saiu. Preenchido = nao manda de novo, nem
--                        pelo webhook repetido nem pelo timer.
--   aviso_para        -- para quem foi (a lista do .env muda com o tempo;
--                        o registro diz quem recebeu ESTE).
--   aviso_remetente   -- de qual caixa saiu.
--   aviso_erro        -- a ultima falha, em portugues, para a tela.
--   aviso_tentativas  -- o timer tenta de novo ate o limite do codigo
--                        (services/contrato.MAX_TENTATIVAS_AVISO); depois
--                        so o botao "Reenviar aviso" da tela.
--
-- ADITIVA E IDEMPOTENTE. Sem BEGIN/COMMIT: quem abre a transacao e o
-- scripts/aplicar_migrations.
-- =====================================================================

ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aviso_enviado_em TIMESTAMPTZ;
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aviso_para TEXT[];
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aviso_remetente VARCHAR(150);
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aviso_erro TEXT;
ALTER TABLE contratos ADD COLUMN IF NOT EXISTS aviso_tentativas SMALLINT NOT NULL DEFAULT 0;

-- O timer olha os assinados ainda sem aviso.
CREATE INDEX IF NOT EXISTS idx_contratos_aviso_pendente
    ON contratos (assinado_em) WHERE status = 'assinado' AND aviso_enviado_em IS NULL;
