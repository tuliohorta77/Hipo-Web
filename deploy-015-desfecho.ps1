# =====================================================================
#  HIPO -- 015: rastreio da agenda (quem agendou + o que aconteceu)
# =====================================================================
#
#  O QUE MUDA
#
#  A agenda passa a responder as duas perguntas que a operacao fecha
#  todo dia:
#
#     "quantos agendamentos por dia, por SDR"
#     "quantas reunioes por dia, por EV -- e com que resultado"
#
#  Para isso, tres coisas:
#
#   1. AGENDADO_POR. Campo proprio, ao lado do anfitriao. `criado_por`
#      responde "quem digitou" e e auditoria; `agendado_por` responde "de
#      quem e o credito" e e METRICA. Sao a mesma pessoa em quase toda
#      linha -- e no dia em que divergem, que e o dia em que alguem cobre
#      o colega, uma coluna so premiaria quem digitou.
#
#   2. DESFECHO: realizada / cancelada / no-show. O botao de status pedido
#      na conversa. A regra das 24h SUGERE, a pessoa escolhe, e o relogio
#      fica guardado ao lado da escolha (desfecho_antecedencia_horas).
#      Reuniao que passou e ninguem marcou fica PENDENTE e cobra num
#      contador -- nao vira no-show sozinha. Inventar um resultado que
#      ninguem afirmou destruiria a confianca no relatorio inteiro.
#
#   3. RELATORIO, num modal dentro da propria Agenda, na janela da semana
#      que esta na tela.
#
#  E duas correcoes que vem junto:
#
#   4. SIGLAS DOS TIPOS. A semente da 011 era palpite. Entram as
#      confirmadas: DG/AP/FC/FP/VT, com acento -- o `nome` vai para o
#      TITULO do evento que o CLIENTE le.
#
#   5. A GRADE DA EQUIPE VOLTA A SER CLICAVEL. Ela estava travada com o
#      argumento de que "a celula vazia e vazia para quem?". O argumento
#      estava certo sobre o dado e errado sobre a pessoa: quem abre a
#      grade da equipe e o SDR, e ele abre para achar onde cabe a reuniao
#      do EV. A trava saiu da grade e ficou no formulario, que e onde ela
#      cabe -- salvar continua travado ate escolher o anfitriao.
#
#  DOIS PASSOS QUE O CI NAO FAZ
#
#  O job de deploy faz rsync + restart, e mais nada.
#
#    1. MIGRATION 012 (ANTES do deploy). Aditiva e idempotente. Coluna que
#       existe antes do codigo que a usa nunca quebra nada; o contrario,
#       sim -- o SELECT da agenda passaria a pedir `r.desfecho` num banco
#       que ainda nao tem a coluna, e a tela inteira daria 500.
#    2. NADA DE .env NEM DE pip NESTA ENTREGA. Sem chave nova, sem
#       biblioteca nova. O restart vem do proprio deploy.
#
#  FLUXO
#     0. pre-voo (arquivos no disco, escopo do commit, SSH vivo)
#     1. testes locais (pytest das regras puras + vitest + build)
#     2. migration no RDS
#     3. push -> CI -> PR -> merge -> deploy CONFERIDO pelo nome do job
#     4. smoke (health + as rotas novas respondendo)
#
#  USO
#     .\deploy-015-desfecho.ps1
#     .\deploy-015-desfecho.ps1 -PularTestes
#     .\deploy-015-desfecho.ps1 -PularMigration    # se ja rodou
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularMigration,
    [switch]$PularSmoke,

    [string]$RamoAlvo    = "main",
    [string]$UrlPublica  = "https://hipogestao.com.br",
    [string]$Ip          = "63.179.88.212",
    [string]$UsuarioSsh  = "ec2-user",
    [string]$Chave       = "$HOME\Downloads\chave-hipo.pem",
    [string]$Mensagem    = "feat(agenda): desfecho da reuniao, agendado por e relatorio de produtividade"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# TODO MARCADOR AQUI E ASCII PURO, e nenhum deles pode depender de acento:
# Get-Content -Raw de um arquivo UTF-8 no PowerShell 5.1 embaralha acento, e
# a checagem falharia num arquivo que esta CERTO.
#
# Isso ja custou uma execucao na 014: o marcador do Agenda.jsx era "Marcar
# reuniao em", tirado do aria-label da celula vazia. So que o aria-label e
# um template literal -- `Marcar reuniao em ${dia} as ${slot}` -- e a
# palavra no arquivo tem til. A versao sem acento nao existia em lugar
# nenhum, e o pre-voo acusou "versao ANTIGA" num arquivo recem-escrito.
#
# A licao: o marcador tem que ser um trecho que exista LITERALMENTE no
# arquivo e nao passe perto de acento. Caminho de rota, nome de simbolo e
# nome de constante servem; texto de interface, nao.
$ESPERADOS = @(
    @{ Arquivo = "api\migrations\012_agenda_desfecho.sql";   Marcador = "ck_reuniao_desfecho_em" },
    @{ Arquivo = "api\services\agenda.py";                   Marcador = "sugestao_de_desfecho" },
    @{ Arquivo = "api\routers\crm_agenda.py";                Marcador = "registrar_desfecho" },
    @{ Arquivo = "api\routers\crm_agenda.py";                Marcador = "ProdutividadeOut" },
    @{ Arquivo = "api\schema.sql";                           Marcador = "desfecho_antecedencia_horas" },
    @{ Arquivo = "api\tests\test_agenda_regras.py";          Marcador = "TestSugestaoDeDesfecho" },
    @{ Arquivo = "api\tests\test_crm_agenda.py";             Marcador = "TestProdutividade" },
    @{ Arquivo = "infra\aplicar-012-agenda-desfecho.sh";     Marcador = "idx_reunioes_agendado_por" },
    @{ Arquivo = "web\src\components\crm\agendaComum.js";    Marcador = "antecedenciaEmPalavras" },
    @{ Arquivo = "web\src\components\crm\ModalReuniao.jsx";  Marcador = "PainelDesfecho" },
    @{ Arquivo = "web\src\components\crm\ProdutividadeAgenda.jsx"; Marcador = "/crm/agenda/produtividade" },
    @{ Arquivo = "web\src\pages\crm\Agenda.jsx";             Marcador = "ProdutividadeAgenda" },
    @{ Arquivo = "web\src\pages\crm\Agenda.jsx";             Marcador = "tomDoCartao" },
    @{ Arquivo = "web\src\tests\Agenda.test.jsx";            Marcador = "pendente_de_desfecho" },
    @{ Arquivo = "web\src\tests\ModalReuniao.test.jsx";      Marcador = "desfecho_sugerido" },
    @{ Arquivo = "web\src\tests\ProdutividadeAgenda.test.jsx"; Marcador = "taxa_realizacao" }
)

# =====================================================================
# Utilidades
# =====================================================================

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

function Passo($texto)  { Write-Host "  -> $texto" -ForegroundColor Gray }
function Bom($texto)    { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto)  { Write-Host "  !!  $texto" -ForegroundColor Yellow }

function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Executar($descricao, $bloco) {
    Passo $descricao
    & $bloco
    if ($LASTEXITCODE -ne 0) { Abortar "$descricao falhou (codigo $LASTEXITCODE)." }
}

function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

function RunMaisRecente($ramoDoRun) {
    $bruto = & gh run list --workflow=ci-cd.yml --branch $ramoDoRun --limit 1 `
        --json databaseId,createdAt,event,status,conclusion
    if ($LASTEXITCODE -ne 0) { return $null }
    $lista = @($bruto | ConvertFrom-Json)
    if ($lista.Count -eq 0) { return $null }
    return $lista[0]
}

function EsperarRunNovo($ramoDoRun, $idAntes, $segundos = 45) {
    Passo "esperando ${segundos}s para o Actions acordar no ramo $ramoDoRun..."
    Start-Sleep -Seconds $segundos
    $atual = RunMaisRecente $ramoDoRun
    if (-not $atual) { return $null }
    $ehNovo = ([string]$atual.databaseId) -ne ([string]$idAntes)
    $idade  = (Get-Date) - [datetime]$atual.createdAt
    if ($ehNovo -or $idade.TotalMinutes -lt 3) { return $atual }
    return $null
}

function AcompanharRun($runId, $oQueEsperar) {
    Passo "acompanhando o run $runId ($oQueEsperar)..."
    & gh run watch $runId --exit-status
    if ($LASTEXITCODE -ne 0) {
        Abortar "o CI ficou vermelho no run $runId. Nada foi para producao. $REPO_URL"
    }
}

function ExigirDeployFeito($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler os jobs do run $runId. $REPO_URL" }
    $deploy = @((($bruto | ConvertFrom-Json).jobs) | Where-Object { $_.name -like "Deploy*" })
    if ($deploy.Count -eq 0) { Abortar "o run $runId nao tem job de Deploy. $REPO_URL" }

    $conclusao = [string]$deploy[0].conclusion
    if ($conclusao -eq "success") { Bom "job de Deploy concluido com sucesso"; return }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. O codigo esta no repositorio, mas NAO em producao."
    }
    Abortar "o job de Deploy terminou como '$conclusao' no run $runId. $REPO_URL"
}

# =====================================================================
# 0. Pre-voo
# =====================================================================

Titulo "0. Pre-voo"

if (-not (Test-Path "api\main.py")) {
    Abortar "rode a partir da raiz do repositorio (a pasta que tem api\ e web\)."
}
Bom "raiz do repositorio"

foreach ($item in $ESPERADOS) {
    if (-not (Test-Path $item.Arquivo)) {
        Abortar "arquivo da 015 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) marcadores da 015 conferem no disco"

# A 015 depende da 011: sem `reunioes`, os ADD COLUMN da 012 falham.
if (-not (Test-Path "api\migrations\011_agenda.sql")) {
    Abortar "api\migrations\011_agenda.sql nao existe. A 012 acrescenta colunas na tabela que a 011 cria."
}
Bom "a 011 esta no disco"

# A armadilha do schema.sql: o CI monta o banco de teste com
# `psql -f api/schema.sql`, NAO com as migrations. Migration que nao chega
# la derruba dezenas de testes no runner e passa verde na maquina de quem
# migrou a mao -- foi assim que a fase 'suspect' derrubou 45 de uma vez.
#
# Aqui a checagem e por COLUNA e por CONSTRAINT, e nao por CREATE TABLE:
# a 012 nao cria tabela nenhuma, so acrescenta a `reunioes`.
$schema = Get-Content "api\schema.sql" -Raw
foreach ($coluna in @("agendado_por", "desfecho_em", "desfecho_antecedencia_horas")) {
    if ($schema -notmatch [regex]::Escape($coluna)) {
        Abortar "api\schema.sql nao tem a coluna '$coluna'. O CI monta o banco de teste a partir dele -- a suite inteira cairia."
    }
}
foreach ($ck in @("ck_reuniao_desfecho", "ck_reuniao_desfecho_em")) {
    if ($schema -notmatch [regex]::Escape($ck)) {
        Abortar "api\schema.sql nao tem a constraint '$ck'. Banco de teste e producao ficariam diferentes."
    }
}
Bom "schema.sql espelha a migration 012"

# As siglas confirmadas pela operacao precisam estar nos DOIS lugares: na
# migration (que corrige producao) e no schema.sql (que semeia o banco do
# CI). Uma so faria o teste passar com uma lista e a producao rodar com
# outra -- e a sigla sai no rotulo da grade e no titulo do convite.
foreach ($sigla in @("'DG'", "'AP'", "'FC'", "'FP'", "'VT'")) {
    if ($schema -notmatch [regex]::Escape($sigla)) {
        Abortar "api\schema.sql nao semeia a sigla $sigla. Confira a lista de tipos_reuniao."
    }
}
Bom "as 5 siglas confirmadas estao no schema.sql"

# Asserts de igualdade exata em modulos_do_cargo quebram a cada modulo
# novo. Esta entrega NAO cria modulo (a agenda vive em 'crm'), entao os
# asserts tem que continuar como estavam.
$asserts = @(Select-String -Path "api\tests\*.py" -Pattern 'modulos_do_cargo.*==|body\["modulos"\].*==' -ErrorAction SilentlyContinue)
Passo "asserts de modulos_do_cargo encontrados: $($asserts.Count) (a 015 nao cria modulo, entao nenhum deveria mudar)"

$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }
    $inesperados = @($sujos | Where-Object {
        $_ -notmatch 'api/(migrations/012_agenda_desfecho\.sql|services/agenda\.py|routers/crm_agenda\.py|tests/test_(agenda_regras|crm_agenda)\.py|schema\.sql)' -and
        $_ -notmatch 'infra/aplicar-012-agenda-desfecho\.sh' -and
        $_ -notmatch 'web/src/(components/crm/(ModalReuniao\.jsx|agendaComum\.js|ProdutividadeAgenda\.jsx)|pages/crm/Agenda\.jsx|tests/(Agenda|ModalReuniao|ProdutividadeAgenda)\.test\.jsx)' -and
        $_ -notmatch 'deploy-015-desfecho\.ps1'
    })
    if ($inesperados.Count -gt 0) {
        Write-Host ""
        Aviso "$($inesperados.Count) arquivo(s) fora do escopo desta entrega."
        Confirmar "Levar tudo isso junto mesmo assim?"
    }
    else { Bom "so os arquivos da 015" }
}
else { Aviso "arvore limpa -- nada novo para commitar." }

Passo "SSH..."
& ssh -i $Chave -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 `
    "$UsuarioSsh@$Ip" "echo vivo" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Abortar "SSH nao respondeu. A migration precisa dele -- resolva antes de comecar."
}
Bom "SSH vivo"

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
$ramo  = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"
$noAlvo = ($ramo -eq $RamoAlvo)
if (-not $noAlvo) {
    Aviso "push em '$ramo' NAO deploya: o deploy so roda na '$RamoAlvo'."
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "o CI ainda roda tudo."
}
else {
    Titulo "1. Testes locais"

    # As regras da agenda sao PURAS: sem banco, sem rede, sem Google.
    # Rodam no Windows sem Postgres, ao contrario de test_crm_agenda.py,
    # que so valida no CI.
    Push-Location "api"
    try {
        $env:PYTHONPATH = (Get-Location).Path
        Executar "pytest (regras da agenda)" { python -m pytest tests/test_agenda_regras.py -q }
        Bom "regras da agenda verdes"
    }
    finally { Pop-Location }

    Push-Location "web"
    try {
        Executar "vitest" { npx vitest run }
        Bom "frontend verde"
        Executar "vite build" { npx vite build }
        Bom "build verde"
    }
    finally { Pop-Location }
}

# =====================================================================
# 2. Migration no RDS
# =====================================================================

if ($PularMigration) {
    Titulo "2. Migration -- PULADA"
    Aviso "so use isto se a 012 JA foi aplicada; sem as colunas, a Agenda da 500 no primeiro SELECT."
}
else {
    Titulo "2. Migration 012_agenda_desfecho no RDS"

    Write-Host ""
    Write-Host "  ADITIVA e IDEMPOTENTE: ADD COLUMN / CREATE INDEX IF NOT EXISTS," -ForegroundColor Gray
    Write-Host "  constraints dentro de um DO que checa pg_constraint, e UPDATEs" -ForegroundColor Gray
    Write-Host "  por slug numa lista de dominio de 5 linhas. Nenhum DROP -- por" -ForegroundColor Gray
    Write-Host "  isso nao exige o export em CSV que as destrutivas exigem." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Ela MUDA dois dados existentes, de proposito:" -ForegroundColor Yellow
    Write-Host "    - agendado_por recebe criado_por onde esta NULL (backfill)" -ForegroundColor Gray
    Write-Host "    - tipos_reuniao recebe as siglas certas: DG/AP/FC/FP/VT" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Roda ANTES do deploy: o SELECT da agenda passa a pedir" -ForegroundColor Gray
    Write-Host "  r.desfecho, e num banco sem a coluna a tela inteira da 500." -ForegroundColor Gray

    Confirmar "Aplicar a 012 no RDS de producao?"

    Executar "enviando a migration" {
        scp -i $Chave "api\migrations\012_agenda_desfecho.sql" "${UsuarioSsh}@${Ip}:/tmp/012_agenda_desfecho.sql"
    }
    Executar "enviando o aplicador" {
        scp -i $Chave "infra\aplicar-012-agenda-desfecho.sh" "${UsuarioSsh}@${Ip}:/tmp/aplicar-012-agenda-desfecho.sh"
    }
    Executar "aplicando" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo bash /tmp/aplicar-012-agenda-desfecho.sh /tmp/012_agenda_desfecho.sql"
    }
    Bom "colunas de rastreio criadas e siglas corrigidas"
}

# =====================================================================
# 3. Push, CI e deploy
# =====================================================================

Titulo "3. Push e deploy"

$sujos = & git status --porcelain
if ($sujos) {
    Confirmar "Commitar e empurrar?"
    Executar "git add"    { git add -A }
    Executar "git commit" { git commit -m $Mensagem }
    Bom "commit criado"
}

$aFrente = "0"
try   { $aFrente = (& git rev-list --count "origin/$ramo..$ramo").Trim() }
catch { $aFrente = "?" }

# O id do run ANTES do push. Sem ele nao ha como distinguir "o Actions ja
# criou o run novo" de "ainda nao criou, e estou olhando o anterior" -- e o
# anterior esta verde, entao a diferenca e entre conferir o deploy e
# inventar que ele aconteceu.
$idAntesDoPush = ""
if ($temGh) {
    $anterior = RunMaisRecente $ramo
    if ($anterior) { $idAntesDoPush = [string]$anterior.databaseId }
}

Executar "git push" { git push origin $ramo }
$empurrouAlgo = ($aFrente -ne "0")
Bom "codigo no repositorio, no ramo $ramo"

if (-not $temGh) {
    Aviso "gh nao instalado -- abra o PR, mergeie e confira o job Deploy em $REPO_URL"
}
elseif ($noAlvo) {
    if ($empurrouAlgo) {
        $runMain = EsperarRunNovo $RamoAlvo $idAntesDoPush 60
        if (-not $runMain) {
            Abortar "push feito mas nao vi run novo na $RamoAlvo. Confira o deploy em $REPO_URL"
        }
        AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
        ExigirDeployFeito ([string]$runMain.databaseId)
    }
    else {
        Aviso "nada empurrado -- pulando a conferencia do CI"
    }
}
else {
    if ($empurrouAlgo) {
        $antes = RunMaisRecente $ramo
        $idAntes = ""
        if ($antes) { $idAntes = [string]$antes.databaseId }
        $atual = EsperarRunNovo $ramo $idAntes
        if ($atual) {
            AcompanharRun ([string]$atual.databaseId) "Backend Tests + Frontend Tests"
            Bom "testes verdes no ramo"
        }
        else { Aviso "nenhum run novo no ramo. $REPO_URL" }
    }

    $numeroPr = ""
    $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number
    if ($LASTEXITCODE -eq 0) {
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -gt 0) { $numeroPr = [string]$prs[0].number }
    }

    if (-not $numeroPr) {
        Passo "nenhum PR aberto -- criando"
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 015 -- rastreio da agenda. Migration 012 (aditiva) aplicada antes do deploy: agendado_por + desfecho em reunioes, e as siglas confirmadas dos tipos (DG/AP/FC/FP/VT). O desfecho e PERGUNTADO -- a regra das 24h sugere e o relogio fica guardado ao lado da escolha. Reuniao que passou sem registro fica pendente e cobra; nada vira no-show sozinho. Sem chave nova no .env e sem biblioteca nova."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se foi 'No commits between', o merge ja aconteceu."
        }
        $prs = @((& gh pr list --head $ramo --base $RamoAlvo --state open --json number) | ConvertFrom-Json)
        if ($prs.Count -eq 0) { Abortar "PR criado mas nao encontrado. $REPO_URL" }
        $numeroPr = [string]$prs[0].number
    }
    Bom "PR #$numeroPr"

    Confirmar "Mergear o PR #$numeroPr em $RamoAlvo agora?"

    $antesMain = RunMaisRecente $RamoAlvo
    $idAntesMain = ""
    if ($antesMain) { $idAntesMain = [string]$antesMain.databaseId }

    Executar "gh pr merge" { gh pr merge $numeroPr --merge }
    Bom "PR #$numeroPr mergeado"

    $runMain = EsperarRunNovo $RamoAlvo $idAntesMain 60
    if (-not $runMain) {
        Abortar "merge feito mas nao vi run novo na $RamoAlvo. $REPO_URL"
    }
    AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
    ExigirDeployFeito ([string]$runMain.databaseId)
}

# =====================================================================
# 4. Smoke
# =====================================================================

Titulo "4. Smoke"

if ($PularSmoke) {
    Aviso "smoke pulado"
}
else {
    Passo "API..."
    try {
        $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
        if (-not $health.versao) { Abortar "/health respondeu sem o campo 'versao': $($health | ConvertTo-Json -Compress)" }
        Bom "API viva -- versao $($health.versao)"
    }
    catch {
        Abortar "a API NAO respondeu: $($_.Exception.Message). Veja 'sudo journalctl -u hipo-api -n 50'."
    }

    # A versao do app nao e bumpada, entao /health nao diz o que esta no
    # ar. As ROTAS dizem.
    #
    # ATENCAO ao conferir isto a mao: /api/openapi.json e grande, e ja
    # aconteceu de uma leitura truncada dizer que as rotas nao existiam
    # quando existiam. A prova barata e o proprio endpoint: 401 (pede
    # login) prova que a rota EXISTE; 404 prova que nao.
    Passo "rotas novas no openapi..."
    try {
        $spec = Invoke-RestMethod -Uri "$UrlPublica/api/openapi.json" -TimeoutSec 20
        $rotas = $spec.paths.PSObject.Properties.Name
        foreach ($r in @("/crm/agenda/produtividade", "/crm/agenda/reunioes/{reuniao_id}/desfecho")) {
            if ($rotas -notcontains $r) { Abortar "a rota $r NAO esta em producao. O deploy do codigo novo nao chegou." }
        }
        Bom "as rotas de desfecho e produtividade estao no ar"
    }
    catch {
        Abortar "nao consegui ler o openapi: $($_.Exception.Message)"
    }

    Passo "front..."
    try {
        $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
        if ($front.StatusCode -ne 200) { Abortar "o front respondeu HTTP $($front.StatusCode)" }
        Bom "front servido (HTTP 200)"
    }
    catch { Abortar "o front nao respondeu: $($_.Exception.Message)" }
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Rastreio da agenda no ar"

Write-Host ""
Write-Host "  RELOGUE ANTES DE CONFERIR." -ForegroundColor Yellow
Write-Host "  O front le os modulos do localStorage.hipo_user, gravado no" -ForegroundColor Gray
Write-Host "  login. Ctrl+Shift+R recarrega os assets mas nao zera o" -ForegroundColor Gray
Write-Host "  localStorage -- so logout/login forca um /auth/me novo." -ForegroundColor Gray
Write-Host "  (Desta vez o relogin e pelo BUNDLE: a 015 nao cria modulo.)" -ForegroundColor Gray
Write-Host ""
Write-Host "  O passeio de conferencia:" -ForegroundColor Gray
Write-Host "     1. Agenda -> abra uma reuniao ja marcada" -ForegroundColor White
Write-Host "     2. la embaixo: 'O que aconteceu?' com as tres respostas," -ForegroundColor White
Write-Host "        a sugerida ja marcada e a antecedencia escrita ao lado" -ForegroundColor White
Write-Host "     3. 'Realizada' pede a proxima tarefa; cancelada e no-show, nao" -ForegroundColor White
Write-Host "     4. de volta na grade: botao 'Produtividade', no topo a direita" -ForegroundColor White
Write-Host "     5. e o seletor 'Marcadas por ...', ao lado do de anfitriao" -ForegroundColor White
Write-Host ""
Write-Host "  O QUE MUDOU NO COMPORTAMENTO, e vale avisar a equipe:" -ForegroundColor Yellow
Write-Host "     - 'Cancelar reuniao' saiu do modal. Cancelar agora e uma das" -ForegroundColor Gray
Write-Host "       tres respostas de 'O que aconteceu?'. A rota antiga continua" -ForegroundColor Gray
Write-Host "       viva para o cancelamento pela tela de Tarefas." -ForegroundColor Gray
Write-Host "     - a grade da EQUIPE voltou a aceitar clique: o formulario abre" -ForegroundColor Gray
Write-Host "       sem anfitriao e so libera o salvar depois de escolher um." -ForegroundColor Gray
Write-Host "     - reuniao que passou sem resposta aparece com borda tracejada" -ForegroundColor Gray
Write-Host "       na grade e conta no KPI 'Sem desfecho'. Nada vira no-show" -ForegroundColor Gray
Write-Host "       sozinho -- por decisao, nao por falta de implementacao." -ForegroundColor Gray
Write-Host ""
Write-Host "  CONFIRA O NOME DO TIPO 'FP'. Ele esta como 'FUP', e o NOME vai" -ForegroundColor Yellow
Write-Host "  para o titulo do evento que o CLIENTE le: '... | FUP Controller" -ForegroundColor Yellow
Write-Host "  MedSeg'. Se preferir algo que o cliente entenda, e um UPDATE:" -ForegroundColor Yellow
Write-Host "     UPDATE tipos_reuniao SET nome = 'Acompanhamento' WHERE slug = 'follow-up';" -ForegroundColor White
Write-Host ""
