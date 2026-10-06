-- ============================================================================
-- HIPO — 001_drop_legado.sql
-- Sprint 0: remocao do legado PEX / CROmie / BD Ativados / POs / Carteira.
--
-- APLICADA EM PRODUCAO: 2026-08-06
-- Backup previo: hipo-backup-legado-20260806-211928.zip
--   sha256 340e1b40d38305d22de5df00f6b2238bead9ac2b817e0835c5fa6aeec316e085
--   664.428 linhas em 32 tabelas, CSV.gz + _schema_completo.sql
--
-- Numeracao reiniciada: as migrations 002..011 do ciclo anterior foram
-- removidas do repositorio junto com as tabelas que criavam.
--
-- 30 tabelas removidas. Sobrevivem 'usuarios' e 'dia_nao_util'.
-- Cairam em cascata 6 views: vw_po_ausentes, vw_bd_ativados_atual,
-- vw_compliance_usuarios, pex_metas_mensais, vw_pex_mes_atual,
-- vw_reconciliacao_atual.
--
-- *** IRREVERSIVEL. Nao reexecutar sem novo backup. ***
-- ============================================================================

BEGIN;

DO $$
DECLARE r record; n int;
BEGIN
  -- Nao roda depois que o CRM ja existe.
  IF to_regclass('public.contas') IS NOT NULL THEN
    RAISE EXCEPTION 'Tabela contas ja existe — a 001 ja rodou. Abortando.';
  END IF;

  -- Banco precisa ser o do HIPO.
  IF to_regclass('public.usuarios') IS NULL THEN
    RAISE EXCEPTION 'usuarios ausente — banco errado. Abortando.';
  END IF;

  -- Banco novo (CI, instancia nova): so as duas tabelas da 000 (mais a
  -- schema_migrations do scripts/aplicar_migrations.py), nada a remover.
  -- O loop abaixo vira no-op e a contagem final confere.
  -- Banco com outras tabelas e usuarios vazia continua sendo banco errado.
  IF (SELECT count(*) FROM public.usuarios) = 0
     AND EXISTS (SELECT 1 FROM pg_tables
                 WHERE schemaname = 'public'
                   AND tablename NOT IN ('usuarios', 'dia_nao_util', 'schema_migrations')) THEN
    RAISE EXCEPTION 'usuarios vazia num banco com outras tabelas — banco errado. Abortando.';
  END IF;

  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname = 'public'
             AND tablename NOT IN ('usuarios', 'dia_nao_util', 'schema_migrations')
           ORDER BY tablename
  LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
    RAISE NOTICE 'drop: %', r.tablename;
  END LOOP;

  SELECT count(*) INTO n FROM pg_tables
   WHERE schemaname = 'public' AND tablename <> 'schema_migrations';
  IF n <> 2 THEN
    RAISE EXCEPTION 'Esperava 2 tabelas (usuarios, dia_nao_util), restaram %. Rollback.', n;
  END IF;

  RAISE NOTICE 'OK — restaram usuarios e dia_nao_util';
END $$;

COMMIT;
