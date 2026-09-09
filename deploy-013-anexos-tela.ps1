# =====================================================================
#  HIPO -- 013: a tela dos anexos
# =====================================================================
#
#  O QUE MUDA
#
#  O bloco de anexos aparece na tarefa, em dois lugares:
#    - modal da tarefa, no modulo de Tarefas
#    - drilldown da tarefa, na aba de Tarefas da oportunidade e do parceiro
#
#  Colar (Ctrl+V) e o gesto principal, nao o alternativo: print de
#  WhatsApp nasce no Ctrl+C, e obrigar a salvar em disco antes e atrito em
#  cima de um gesto que ja estava pronto. Arrastar-e-soltar e o botao de
#  escolher arquivo continuam existindo.
#
#  Imagem vira miniatura e abre ampliada; PDF vira icone e abre em aba
#  nova. Tarefa fechada MOSTRA os anexos e nao deixa mexer -- mesma
#  imutabilidade do resultado e do motivo de cancelamento.
#
#  SO FRONTEND. O backend subiu na 012: as quatro rotas ja estao no ar, a
#  tabela existe e o bucket esta configurado. Aqui nao ha migration, nao
#  ha passo de servidor e nao ha variavel de ambiente nova -- portanto
#  este script NAO precisa de SSH, e nao para se o seu IP tiver mudado.
#
#  FLUXO
#     0. pre-voo (arquivos no disco, escopo do commit)
#     1. testes locais (vitest + vite build)
#     2. push -> CI -> deploy CONFERIDO pelo nome do job
#     3. smoke
#
#  USO
#     .\deploy-013-anexos-tela.ps1
#     .\deploy-013-anexos-tela.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO. E nenhum argumento de comando nativo leva
#  aspas duplas -- ver a nota no rodape.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$Mensagem   = "feat(tarefas): tela de anexos -- colar, galeria e lightbox"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

$ESPERADOS = @(
    @{ Arquivo = "web\src\components\crm\AnexosTarefa.jsx"; Marcador = "onPaste" },
    @{ Arquivo = "web\src\components\crm\AnexosTarefa.jsx"; Marcador = "nivelLightbox" },
    @{ Arquivo = "web\src\components\crm\AbaTarefas.jsx";   Marcador = "AnexosTarefa" },
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";           Marcador = "AnexosTarefa" },
    @{ Arquivo = "web\src\tests\AnexosTarefa.test.jsx";     Marcador = "Ctrl+V" }
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

function EsperarRunNovo($ramoDoRun, $idAntes, $segundos = 60) {
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
        Abortar "arquivo da 013 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) marcadores da 013 conferem"

# A 013 depende da 012 estar NO AR: sem as rotas, a tela sobe e todo
# bloco de anexos mostra erro. Conferir pela API publica, e nao pelo
# codigo local, porque o que importa e o que esta rodando.
Passo "conferindo que o backend dos anexos ja esta em producao..."
try {
    # /api/openapi.json, e nao /openapi.json: a API vive atras do nginx
    # no prefixo /api -- o mesmo do /api/health logo abaixo. Na raiz o
    # nginx serve o index.html do front, que responde 200 sem `paths`, e
    # a checagem concluia que a rota nao existe. Falso negativo que
    # abortou um deploy bom.
    $doc = Invoke-RestMethod -Uri "$UrlPublica/api/openapi.json" -TimeoutSec 25

    if (-not $doc.paths) {
        # Distinguir "a API respondeu e nao tem a rota" de "isto nem e o
        # openapi". Sem esta separacao, qualquer resposta inesperada vira
        # a mesma mensagem, que manda rodar a 012 de novo a toa.
        Aviso "a resposta de /api/openapi.json nao parece o documento OpenAPI (sem 'paths')."
        Confirmar "Seguir sem essa conferencia?"
    }
    else {
        $rotas = $doc.paths.PSObject.Properties.Name
        $temRota = $rotas -contains '/crm/tarefas/{tarefa_id}/anexos'
        if (-not $temRota) {
            Abortar "a API em producao respondeu o OpenAPI, mas SEM a rota de anexos. Suba a 012 primeiro (.\deploy-012-anexos-backend.ps1)."
        }
        Bom "as rotas de anexo estao no ar"
    }
}
catch {
    Aviso "nao consegui ler o openapi: $($_.Exception.Message)"
    Confirmar "Seguir sem essa conferencia?"
}

# git status --porcelain: enxerga tracked E untracked. `git diff` nao ve
# arquivo novo, e foi assim que a 011 anunciou "so frontend" levando um
# .py a reboque.
$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }

    $pyMudado = @($sujos | Where-Object { $_ -match '\.py$' })
    if ($pyMudado.Count -gt 0) {
        Write-Host ""
        Aviso "ha .py no commit, e esta entrega deveria ser so frontend."
        Confirmar "Seguir mesmo assim?"
    }
    else { Bom "nenhum .py -- so frontend, como esperado" }
}
else { Aviso "arvore limpa -- nada novo para commitar." }

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

    # So frontend nesta entrega. O CI roda a suite de backend inteira de
    # qualquer jeito.
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
# 2. Push, CI e deploy
# =====================================================================

Titulo "2. Push e deploy"

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

# O id ANTES do push. Sem ele, `RunMaisRecente` chamado logo depois
# devolve o run ANTERIOR -- que esta verde -- e o script anuncia deploy
# concluido com o codigo velho no ar. Foi o que derrubou a API na 012.
# A pista no log era "has ALREADY completed with 'success'".
$idAntesDoPush = ""
if ($temGh) {
    $anterior = RunMaisRecente $ramo
    if ($anterior) { $idAntesDoPush = [string]$anterior.databaseId }
}

Executar "git push" { git push origin $ramo }
$empurrouAlgo = ($aFrente -ne "0")
Bom "codigo no repositorio, no ramo $ramo"

if (-not $temGh) {
    Aviso "gh nao instalado -- confira o job Deploy em $REPO_URL"
}
elseif ($noAlvo) {
    if ($empurrouAlgo) {
        $runMain = EsperarRunNovo $RamoAlvo $idAntesDoPush 60
        if (-not $runMain) {
            Abortar "push feito mas nao vi run novo na $RamoAlvo. Confira em $REPO_URL"
        }
        AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
        ExigirDeployFeito ([string]$runMain.databaseId)
    }
    else { Aviso "nada empurrado -- pulando a conferencia do CI" }
}
else {
    if ($empurrouAlgo) {
        $atual = EsperarRunNovo $ramo $idAntesDoPush
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
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 013 -- tela dos anexos: colar do clipboard, arrastar-e-soltar, galeria com miniaturas e lightbox. So frontend; o backend subiu na 012."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se foi 'No commits between', use .\deploy-007-retomar.ps1."
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
# 3. Smoke
# =====================================================================

Titulo "3. Smoke"

if ($PularSmoke) {
    Aviso "smoke pulado"
}
else {
    Passo "API..."
    try {
        # `versao`, e nao `version`: e o nome do campo em /health. O
        # `$health.version` herdado do deploy-010 imprimia string vazia e
        # parecia confirmar a versao sem confirmar nada.
        $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
        if (-not $health.versao) { Abortar "/health respondeu sem 'versao'" }
        Bom "API viva -- versao $($health.versao)"
    }
    catch { Abortar "a API nao respondeu: $($_.Exception.Message)" }

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

Titulo "Anexos no ar"

Write-Host ""
Write-Host "  Recarregue com Ctrl+Shift+R -- e mudanca de assets." -ForegroundColor Green
Write-Host ""
Write-Host "  O roteiro que os testes NAO cobrem (jsdom nao tem clipboard" -ForegroundColor Yellow
Write-Host "  de verdade, nem z-index):" -ForegroundColor Yellow
Write-Host ""
Write-Host "    1. Tarefas -> abrir um cartao ABERTO. O bloco 'Anexos'" -ForegroundColor White
Write-Host "       aparece com o convite para colar." -ForegroundColor Gray
Write-Host "    2. Tire um print (Win+Shift+S), clique no bloco e Ctrl+V." -ForegroundColor White
Write-Host "       A miniatura tem de aparecer em segundos." -ForegroundColor Gray
Write-Host "    3. Clique na miniatura: a imagem abre AMPLIADA, na frente" -ForegroundColor White
Write-Host "       do modal da tarefa. Esc fecha so o lightbox." -ForegroundColor Gray
Write-Host "    4. Passe o mouse na miniatura: o X de remover aparece." -ForegroundColor White
Write-Host "       Remova e confirme que sumiu." -ForegroundColor Gray
Write-Host "    5. Abra uma tarefa CONCLUIDA que tenha anexo: a miniatura" -ForegroundColor White
Write-Host "       aparece, mas nao ha X nem botao Anexar." -ForegroundColor Gray
Write-Host "    6. Dentro da OPORTUNIDADE (aba Tarefas), repita o passo 3." -ForegroundColor White
Write-Host "       La a pilha e mais funda e o lightbox usa nivel 3 -- se" -ForegroundColor Gray
Write-Host "       abrir ATRAS, e esse numero que esta errado." -ForegroundColor Gray
Write-Host ""
Write-Host "  E confira que o arquivo chegou no bucket:" -ForegroundColor Gray
Write-Host "     aws s3 ls s3://hipo-anexos-520723705827/tarefas/ --recursive" -ForegroundColor White
Write-Host ""
