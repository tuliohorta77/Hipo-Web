-- ============================================================================
-- HIPO — Schema do banco
--
-- Estado apos a Sprint 0 (limpeza do legado, migration 001_drop_legado.sql).
-- As 30 tabelas de PEX, CROmie, BD Ativados, POs, Carteira e Clientes legado
-- foram removidas. Restam autenticacao e o calendario de dias nao uteis.
--
-- O CRM (contas, contatos, oportunidades e tabelas de dominio) entra na
-- Sprint 1 via 002_crm_core.sql e sera refletido aqui.
--
-- Este arquivo e a fonte usada para criar o banco de teste no CI.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- usuarios
-- ---------------------------------------------------------------------------
-- Autenticacao e cargo. 'cargo' e VARCHAR livre; as permissoes por cargo
-- vivem em api/routers/permissions.py (modulos_do_cargo), nao no banco.
--
-- Cargos canonicos apos a Sprint 0:
--   Franqueado | ADM        -> gestao   (modulos: perfil, usuarios)
--   EC | SDR | EV | EP      -> operacao (modulos: perfil)
--
-- Cargos extintos: Gerente (removido), Hunter e Farmer (fundidos em EC).
-- Um usuario que ainda tenha um desses cargos loga mas nao recebe modulo
-- nenhum -- e isso e proposital, para nao herdar acesso por acidente.
-- ---------------------------------------------------------------------------
CREATE TABLE usuarios (
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
-- Calendario de feriados e dias sem expediente. Sobreviveu a limpeza por ser
-- agnostico ao negocio antigo: sera reaproveitado no calculo de previsao de
-- fechamento e de SLA do CRM (api/services/dias_uteis.py).
--
-- A FK para usuarios usa ON DELETE SET NULL: apagar um usuario preserva os
-- feriados que ele cadastrou, apenas soltando a autoria.
--
-- CONSEQUENCIA NOS TESTES: por causa desta FK, um TRUNCATE usuarios CASCADE
-- tambem esvazia dia_nao_util. A fixture db_conn conta com isso.
-- ---------------------------------------------------------------------------
CREATE TABLE dia_nao_util (
    id                     SERIAL PRIMARY KEY,
    data                   DATE NOT NULL UNIQUE,
    motivo                 TEXT NOT NULL,
    criado_por_usuario_id  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dia_nao_util_ano ON dia_nao_util (EXTRACT(YEAR FROM data));
