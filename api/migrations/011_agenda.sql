-- =====================================================================
-- HIPO -- 011_agenda.sql
--
-- (Era 010. Renumerada: a 010 ficou com `nao_prospectar`, de outra
--  frente de trabalho, que chegou primeiro no disco.)
--
-- Agenda de reunioes: a grade semanal do Executivo de Vendas, presa a
-- tarefa que ja existia e espelhada no Google Calendar.
--
-- A DECISAO CENTRAL: REUNIAO NAO E UMA TAREFA PARALELA
--   Toda reuniao TEM uma tarefa, e exatamente uma (tarefa_id UNIQUE
--   NOT NULL). A reuniao nao repete titulo, responsavel, prazo, situacao
--   nem alvo -- ela acrescenta o que so a agenda precisa: duracao, tipo,
--   modalidade, quem do cliente vem e o id do evento no Google.
--
--   Duas tabelas paralelas, cada uma com seu proprio "quando" e seu
--   proprio "quem", divergiriam no primeiro reagendamento -- e a que
--   divergisse seria a que o vendedor esta olhando. Com a tarefa como
--   dona do horario e do responsavel, a agenda herda de graca tudo o
--   que ja foi decidido e testado na Sprint 5:
--
--     * situacao derivada (atrasada / hoje / futura / concluida /
--       cancelada), sem coluna de estado e sem job de meia-noite;
--     * "concluir exige agendar a proxima" -- a reuniao acontecida
--       empurra o funil sozinha;
--     * a producao do mes (/crm/tarefas/resumo) ja conta as reunioes,
--       sem endpoint novo e sem risco de contar duas vezes;
--     * "tarefa fechada e imutavel" vira "reuniao que ja aconteceu nao
--       se remarca", de graca;
--     * o drilldown tarefa -> oportunidade -> conta ja existe.
--
-- POR ISSO NAO EXISTEM AS COLUNAS `inicio`, `responsavel_id` E `titulo`
--   inicio    = tarefas.prazo
--   fim       = tarefas.prazo + duracao_min
--   anfitriao = tarefas.responsavel_id  (de quem e a coluna na grade)
--   titulo    = tarefas.titulo
--   Mesma escolha do "vendedor da conta" (derivado dos EVs das
--   oportunidades ativas) e da situacao da tarefa: o que da para
--   derivar nao vira coluna, porque coluna derivada e coluna que
--   mente na primeira vez que alguem esquece de atualizar as duas.
--
--   Consequencia pratica: REAGENDAR e um PATCH no prazo da tarefa, e
--   trocar o anfitriao e um PATCH no responsavel. As duas rotas ja
--   existem e ja validam.
--
-- TIPO DE REUNIAO E LISTA DE DOMINIO, NAO CHECK
--   O tipo de TAREFA e CHECK fechado de proposito -- comparar "quantas
--   ligacoes ate fechar" exige vocabulario estavel. O tipo de REUNIAO
--   segue a mesma logica de metrica, mas o vocabulario ainda esta sendo
--   descoberto: da planilha de origem veio a sigla "CF", e de um convite
--   real veio o nome "Apresentacao" -- dois pedacos de dois vocabularios
--   que ainda nao se encontraram. Cravar um CHECK com um palpite custaria
--   uma migration a cada tipo novo; tabela com slug UNIQUE custa um
--   INSERT.
--
--   A guarda contra a deriva de vocabulario nao esta no banco, esta na
--   API: criar tipo exige o modulo 'usuarios' (gestao). Ler e usar e de
--   todo mundo. Renomear e um UPDATE de uma linha, nao uma migration --
--   que e exatamente o motivo de a tabela existir enquanto os nomes
--   certos nao estao confirmados.
--
-- CONVIDADO EXTERNO E TEXT[], NAO TABELA
--   O e-mail do cliente que entra num convite nao tem vida propria no
--   HIPO: nao se busca por ele, nao se conta quantas reunioes ele teve,
--   nao se edita fora da reuniao. Uma tabela de vinculo aqui cobraria
--   join em toda leitura da grade para guardar um dado que so viaja
--   junto do evento. O contato do cadastro, esse sim, e FK.
--
-- O GOOGLE E ESPELHO, NAO FONTE
--   google_event_id guarda o que o Google devolveu. Se a integracao
--   estiver desligada, cair ou recusar, a reuniao EXISTE do mesmo jeito
--   e o erro fica em google_erro para a tela oferecer "sincronizar" de
--   novo. Mesma regra da narrativa da IA no fechamento diario: recurso
--   acessorio nao derruba o registro principal, e falha silenciosa e
--   pior que falha visivel -- por isso o erro e COLUNA, nao log.
--
-- NAO E DESTRUTIVA: so cria e semeia. Idempotente.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- tipos_reuniao -- o "CF" da grade e o "Apresentacao" do convite
-- ---------------------------------------------------------------------
-- DOIS CAMPOS PORQUE SAO DOIS LEITORES.
--   `sigla` aparece no cartao da grade ("CF - XPTO (Bruno) - ON"), lido
--   de relance por quem ja conhece o negocio, numa celula estreita.
--   `nome` aparece no TITULO do evento do Google ("... | Apresentacao
--   Controller MedSeg"), lido pelo CLIENTE na agenda dele -- e tambem no
--   combobox, onde quem escolhe precisa entender o que esta escolhendo.
-- Uma coluna so obrigaria um dos dois a ler o texto do outro.
--
-- `ordem` existe porque a lista e curta e tem ordem natural de funil
-- (diagnostico antes de fechamento); alfabetica embaralharia isso.
--
-- `ativo` em vez de DELETE: tipo aposentado sai do combobox mas as
-- reunioes antigas continuam sabendo o que foram. Apagar a linha
-- quebraria a FK de meses de historico para arrumar um combobox.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tipos_reuniao (
    id          SERIAL PRIMARY KEY,
    sigla       VARCHAR(8)   NOT NULL UNIQUE,
    nome        VARCHAR(120) NOT NULL,
    slug        VARCHAR(120) NOT NULL UNIQUE,
    ordem       SMALLINT     NOT NULL DEFAULT 100,
    ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_por  UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tipo_reuniao_sigla CHECK (sigla ~ '^[A-Z0-9]{1,8}$'),
    CONSTRAINT ck_tipo_reuniao_nome  CHECK (length(btrim(nome)) > 0)
);

-- Semente. `ON CONFLICT DO NOTHING` garante que rodar a migration duas
-- vezes nao duplica nem estoura.
--
-- O `nome` importa mais que a sigla: ele vai para o TITULO do evento no
-- Google, na forma "<razao social> <CNPJ> | <nome> Controller MedSeg". Foi
-- assim que 'Apresentacao' entrou -- copiado de um convite real da
-- operacao, nao inventado.
--
-- ATENCAO: so 'Apresentacao' esta confirmado. Os outros quatro sao a
-- leitura mais provavel das siglas que apareceram na planilha de origem.
-- Corrigir e um UPDATE de uma linha, nao uma migration -- que e exatamente
-- o motivo de isto ser tabela e nao CHECK:
--   UPDATE tipos_reuniao SET nome = 'nome certo' WHERE sigla = 'CF';
INSERT INTO tipos_reuniao (sigla, nome, slug, ordem) VALUES
    ('CD',  'Diagnostico',    'diagnostico',    10),
    ('AP',  'Apresentacao',   'apresentacao',   20),
    ('CF',  'Fechamento',     'fechamento',     30),
    ('FUP', 'Follow-up',      'follow-up',      40),
    ('VT',  'Visita tecnica', 'visita-tecnica', 50)
ON CONFLICT (slug) DO NOTHING;


-- ---------------------------------------------------------------------
-- reunioes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reunioes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- NOT NULL e UNIQUE: uma reuniao e sempre exatamente uma tarefa, e
    -- uma tarefa nunca vira duas reunioes. O UNIQUE nao e zelo: sem ele,
    -- "colocar na agenda" clicado duas vezes criaria duas linhas com o
    -- mesmo horario e o mesmo dono, e a grade mostraria a reuniao em
    -- duplicidade sem ninguem entender por que.
    --
    -- CASCADE porque a reuniao nao existe sem a tarefa. Hoje nada no
    -- HIPO apaga tarefa (cancelar nao apaga), entao o CASCADE e rede,
    -- nao caminho -- mas se um dia apagar, o evento no Google fica
    -- orfao: banco nao fala com calendario. Ver a nota equivalente em
    -- 009_anexos.sql sobre o orfao no S3.
    tarefa_id     UUID NOT NULL UNIQUE REFERENCES tarefas(id) ON DELETE CASCADE,

    -- O horario e o dono NAO estao aqui: sao tarefas.prazo e
    -- tarefas.responsavel_id. Ver o cabecalho.
    duracao_min   SMALLINT NOT NULL DEFAULT 30,

    tipo_id       INTEGER REFERENCES tipos_reuniao(id) ON DELETE RESTRICT,
    modalidade    VARCHAR(12) NOT NULL DEFAULT 'online',

    -- Endereco quando presencial, link quando online. Nao ha CHECK
    -- amarrando um ao outro de proposito: reuniao online com endereco
    -- (a sala de onde o vendedor vai falar) e reuniao presencial com
    -- link (o socio que entra remoto) sao dois casos reais, e um CHECK
    -- que os proibisse so ensinaria a equipe a escolher a modalidade
    -- errada para conseguir salvar.
    endereco      TEXT,
    link_video    TEXT,

    -- Quem do cliente vem. FK para o cadastro; e-mails avulsos vao em
    -- `convidados`. Os dois viram `attendees` do evento do Google.
    contato_id    UUID REFERENCES contatos(id) ON DELETE SET NULL,
    convidados    TEXT[] NOT NULL DEFAULT '{}',

    observacoes   TEXT,

    -- ── Espelho no Google Calendar ──────────────────────────────
    -- calendario e o e-mail do anfitriao NO MOMENTO da sincronizacao.
    -- Guardado, e nao derivado do responsavel atual, porque o evento
    -- vive no calendario de quem era o dono quando ele foi criado:
    -- para APAGAR ou ATUALIZAR aquele evento e preciso personificar
    -- aquela pessoa, nao a de agora. Sem esta coluna, trocar o
    -- anfitriao deixaria um evento fantasma na agenda do anterior,
    -- inalcancavel.
    google_calendar_id     TEXT,
    google_event_id        TEXT,
    google_link            TEXT,
    google_sincronizado_em TIMESTAMPTZ,
    -- Ultimo erro de sincronizacao, em portugues. E COLUNA e nao log
    -- porque a tela precisa dizer "o convite nao saiu" -- um convite
    -- que o cliente nunca recebeu e uma reuniao que nao vai acontecer,
    -- e descobrir isso pelo silencio custa a reuniao.
    google_erro            TEXT,

    criado_por    UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 5 min e o minimo que faz sentido marcar; 8h e um dia inteiro de
    -- expediente. O teto existe para um erro de digitacao (300 em vez
    -- de 30) nao pintar a semana inteira de ocupado.
    CONSTRAINT ck_reuniao_duracao CHECK (duracao_min BETWEEN 5 AND 480),
    CONSTRAINT ck_reuniao_modalidade CHECK (modalidade IN ('online', 'presencial')),
    -- Evento no Google sempre sabe em que calendario mora e quando foi
    -- gravado. Sem isso, uma linha com event_id e sem calendar_id seria
    -- um evento que nao da para atualizar nem apagar.
    CONSTRAINT ck_reuniao_google_completo CHECK (
        google_event_id IS NULL
        OR (google_calendar_id IS NOT NULL AND google_sincronizado_em IS NOT NULL)
    )
);

-- A grade pergunta "as reunioes desta semana", e a resposta vem da
-- tarefa. Sem este indice a consulta da semana varre `tarefas` inteira.
-- NAO e parcial (ao contrario de idx_tarefas_abertas): a agenda mostra
-- tambem o que ja aconteceu -- semana passada e consulta legitima.
CREATE INDEX IF NOT EXISTS idx_tarefas_responsavel_prazo
    ON tarefas (responsavel_id, prazo);

CREATE INDEX IF NOT EXISTS idx_reunioes_tipo
    ON reunioes (tipo_id) WHERE tipo_id IS NOT NULL;

-- "Quais reunioes ainda nao chegaram no Google" -- a fila de reenvio.
-- Parcial: em regime normal quase toda linha esta sincronizada, e o
-- indice so precisa conhecer as que faltam.
CREATE INDEX IF NOT EXISTS idx_reunioes_nao_sincronizadas
    ON reunioes (criado_em) WHERE google_event_id IS NULL;


-- ---------------------------------------------------------------------
-- reuniao_participantes -- "pode ter mais envolvidos"
-- ---------------------------------------------------------------------
-- Os NOSSOS que entram na reuniao alem do anfitriao: o EP que vai
-- explicar o servico, o SDR que agendou e quer ouvir, o gestor que
-- acompanha.
--
-- O ANFITRIAO NAO ENTRA AQUI. Ele e tarefas.responsavel_id, e e o que
-- define de quem e a coluna na grade. Repeti-lo nesta tabela criaria a
-- pergunta "e se as duas discordarem?", que nao tem resposta boa.
--
-- Sem papel na PK (diferente de oportunidade_envolvidos): la o mesmo
-- usuario pode ser SDR e EV do mesmo negocio, porque papel e funcao no
-- ciclo. Aqui so existe "vai estar na sala", e estar duas vezes na
-- mesma sala nao quer dizer nada.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reuniao_participantes (
    reuniao_id  UUID NOT NULL REFERENCES reunioes(id)  ON DELETE CASCADE,
    usuario_id  UUID NOT NULL REFERENCES usuarios(id)  ON DELETE CASCADE,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (reuniao_id, usuario_id)
);

-- "Em que reunioes eu entro sem ser o dono" -- a agenda de quem
-- participa mas nao conduz.
CREATE INDEX IF NOT EXISTS idx_reuniao_participantes_usuario
    ON reuniao_participantes (usuario_id);

COMMIT;
