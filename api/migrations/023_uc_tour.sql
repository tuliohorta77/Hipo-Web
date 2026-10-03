-- =====================================================================
-- HIPO -- 023_uc_tour.sql
--
-- Universidade Corporativa: tour guiado nas aulas de uso do HIPO.
--
-- Uma aula pode trazer uma lista de passos. Cada passo diz a tela (rota),
-- o elemento a destacar (atributo data-tour no front) e o texto do balao.
-- O botao "Me mostra no HIPO" da aula abre a tela real e percorre os
-- passos. O tour so OLHA: nao cria nem altera dado nenhum.
--
-- Formato (validado em services/uc.validar_tour):
--   [{"rota": "/crm/tarefas", "alvo": "tar-filtros",
--     "titulo": "...", "texto": "...", "clicar": ["opo-cartao-abrir"]}]
--
-- NAO E DESTRUTIVA: uma coluna nova, anulavel, sem default. Nenhum DROP,
-- nenhum DELETE. Idempotente. Nao exige export previo.
-- =====================================================================

ALTER TABLE uc_aulas ADD COLUMN IF NOT EXISTS tour JSONB;
