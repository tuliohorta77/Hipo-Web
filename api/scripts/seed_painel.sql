-- =============================================================================
-- HIPO v1.4.0 - Etapa 1: seed do Painel Gerencial em SQL puro
-- =============================================================================
-- Roda apos painel.sql. Idempotente: ON CONFLICT garante que rodar de novo
-- nao duplica nem quebra dados ja inseridos.
--
-- Insere:
--   1. Os 10 KPIs em painel_kpi_config (com tipo, polaridade, fonte, ordem).
--   2. Os 60 feriados nacionais brasileiros (12 por ano × 5 anos: 2026-2030).
--
-- Uso no EC2:
--   scp -i $KEY seed_painel.sql ec2-user@$IP:/tmp/seed_painel.sql
--   ssh -i $KEY ec2-user@$IP
--   sudo -iu hipo
--   source /home/hipo/app/.env
--   psql "$DATABASE_URL" -f /tmp/seed_painel.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. KPIs (10 linhas)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO painel_kpi_config (codigo, nome, tipo, polaridade, ordem, icone, cor_hex, fonte, ativo) VALUES
    ('LEAD',      'Leads',           'cumulativo',     'maior', 1,  'ti-user',            '#2563EB', 'bridge', TRUE),
    ('AGEN',      'Agendamentos',    'cumulativo',     'maior', 2,  'ti-calendar',        '#16A34A', 'bridge', TRUE),
    ('APRE',      'Apresentacoes',   'cumulativo',     'maior', 3,  'ti-device-desktop',  '#7C3AED', 'bridge', TRUE),
    ('NMRR',      'NMRR',            'cumulativo',     'maior', 4,  'ti-trending-up',     '#EA580C', 'bridge', TRUE),
    ('TICK_MED',  'Tick. Medio',     'media',          'maior', 5,  'ti-coin',            '#0891B2', 'bridge', TRUE),
    ('RN_PARC',   'Reun. Parcerias', 'cumulativo',     'maior', 6,  'ti-handshake',       '#7C3AED', 'bridge', TRUE),
    ('AGEND_MES', 'Agend. Mes',      'cumulativo',     'maior', 7,  'ti-calendar-event',  '#16A34A', 'bridge', TRUE),
    ('NOSHOW',    '% No-show',       'taxa_invertida', 'menor', 8,  'ti-user-question',   '#DC2626', 'bridge', TRUE),
    ('APPS',      'APPs',            'cumulativo',     'maior', 9,  'ti-bulb',            '#2563EB', 'bridge', TRUE),
    ('TREIN',     'Treinamento',     'cumulativo',     'maior', 10, 'ti-school',          '#0D9488', 'bridge', TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nome       = EXCLUDED.nome,
    tipo       = EXCLUDED.tipo,
    polaridade = EXCLUDED.polaridade,
    ordem      = EXCLUDED.ordem,
    icone      = EXCLUDED.icone,
    cor_hex    = EXCLUDED.cor_hex,
    fonte      = EXCLUDED.fonte,
    ativo      = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Feriados nacionais brasileiros 2026 a 2030 (60 datas)
-- ─────────────────────────────────────────────────────────────────────────────
-- Fixos: Confraternizacao, Tiradentes, Trabalho, Independencia, Aparecida,
--        Finados, Proclamacao, Natal.
-- Moveis (baseados na Pascoa): Carnaval seg/ter, Sexta-feira Santa, Corpus Christi.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO dia_nao_util (data, motivo) VALUES
    -- 2026 (Pascoa: 05/04/2026)
    ('2026-01-01', 'Confraternizacao Universal'),
    ('2026-02-16', 'Segunda-feira de Carnaval'),
    ('2026-02-17', 'Terca-feira de Carnaval'),
    ('2026-04-03', 'Sexta-feira Santa'),
    ('2026-04-21', 'Tiradentes'),
    ('2026-05-01', 'Dia do Trabalho'),
    ('2026-06-04', 'Corpus Christi'),
    ('2026-09-07', 'Independencia do Brasil'),
    ('2026-10-12', 'Nossa Senhora Aparecida'),
    ('2026-11-02', 'Finados'),
    ('2026-11-15', 'Proclamacao da Republica'),
    ('2026-12-25', 'Natal'),

    -- 2027 (Pascoa: 28/03/2027)
    ('2027-01-01', 'Confraternizacao Universal'),
    ('2027-02-08', 'Segunda-feira de Carnaval'),
    ('2027-02-09', 'Terca-feira de Carnaval'),
    ('2027-03-26', 'Sexta-feira Santa'),
    ('2027-04-21', 'Tiradentes'),
    ('2027-05-01', 'Dia do Trabalho'),
    ('2027-05-27', 'Corpus Christi'),
    ('2027-09-07', 'Independencia do Brasil'),
    ('2027-10-12', 'Nossa Senhora Aparecida'),
    ('2027-11-02', 'Finados'),
    ('2027-11-15', 'Proclamacao da Republica'),
    ('2027-12-25', 'Natal'),

    -- 2028 (Pascoa: 16/04/2028, ano bissexto)
    ('2028-01-01', 'Confraternizacao Universal'),
    ('2028-02-28', 'Segunda-feira de Carnaval'),
    ('2028-02-29', 'Terca-feira de Carnaval'),
    ('2028-04-14', 'Sexta-feira Santa'),
    ('2028-04-21', 'Tiradentes'),
    ('2028-05-01', 'Dia do Trabalho'),
    ('2028-06-15', 'Corpus Christi'),
    ('2028-09-07', 'Independencia do Brasil'),
    ('2028-10-12', 'Nossa Senhora Aparecida'),
    ('2028-11-02', 'Finados'),
    ('2028-11-15', 'Proclamacao da Republica'),
    ('2028-12-25', 'Natal'),

    -- 2029 (Pascoa: 01/04/2029)
    ('2029-01-01', 'Confraternizacao Universal'),
    ('2029-02-12', 'Segunda-feira de Carnaval'),
    ('2029-02-13', 'Terca-feira de Carnaval'),
    ('2029-03-30', 'Sexta-feira Santa'),
    ('2029-04-21', 'Tiradentes'),
    ('2029-05-01', 'Dia do Trabalho'),
    ('2029-05-31', 'Corpus Christi'),
    ('2029-09-07', 'Independencia do Brasil'),
    ('2029-10-12', 'Nossa Senhora Aparecida'),
    ('2029-11-02', 'Finados'),
    ('2029-11-15', 'Proclamacao da Republica'),
    ('2029-12-25', 'Natal'),

    -- 2030 (Pascoa: 21/04/2030)
    ('2030-01-01', 'Confraternizacao Universal'),
    ('2030-03-04', 'Segunda-feira de Carnaval'),
    ('2030-03-05', 'Terca-feira de Carnaval'),
    ('2030-04-19', 'Sexta-feira Santa'),
    ('2030-04-21', 'Tiradentes'),
    ('2030-05-01', 'Dia do Trabalho'),
    ('2030-06-20', 'Corpus Christi'),
    ('2030-09-07', 'Independencia do Brasil'),
    ('2030-10-12', 'Nossa Senhora Aparecida'),
    ('2030-11-02', 'Finados'),
    ('2030-11-15', 'Proclamacao da Republica'),
    ('2030-12-25', 'Natal')
ON CONFLICT (data) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- Verificacao (opcional, so para conferir): descomente as linhas abaixo
-- e roda pra ver as contagens.
-- ─────────────────────────────────────────────────────────────────────────────
-- SELECT 'KPIs inseridos' AS o_que, COUNT(*) AS quantos FROM painel_kpi_config;
-- SELECT 'Feriados inseridos' AS o_que, COUNT(*) AS quantos FROM dia_nao_util;
