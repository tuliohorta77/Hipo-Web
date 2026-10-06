# =====================================================================
#  HIPO -- 010: acoes da tela no cabecalho do modal, ao lado do X
# =====================================================================
#
#  O QUE MUDA
#
#  Suspender / Finalizar / Fechar / Salvar saem do rodape do modal e vao
#  para a linha do titulo, encostados no X. Idem na tela de Conta (a
#  aberta pelo menu Contas e o drilldown de dentro da oportunidade):
#  Fechar / Salvar sobem junto.
#
#  Motivo: o modal 'full' tem 92vh. Com a barra embaixo, quem edita um
#  campo do topo tem de percorrer a tela inteira para achar o Salvar --
#  e em notebook de tela curta o rodape ainda disputa espaco com o
#  conteudo. Em cima, as saidas da tela ficam todas no mesmo canto, no
#  lugar onde o olho ja procura o X.
#
#  COMO FOI FEITO
#
#  Modal.jsx ganhou duas portas para o mesmo espaco no cabecalho:
#    - prop `acoes`      -> o PAI monta os botoes (usado nas Contas, onde
#                           o estado do salvamento chega por
#                           registrarSalvar);
#    - <AcoesDoModal>    -> o FILHO monta os botoes e eles aparecem em
#                           cima por portal (usado na oportunidade).
#
#  O portal e o ponto: o botao continua vizinho do estado que ele usa
#  (sujo / salvando / acaoEmCurso), sem canal nenhum com o pai. Canal de
#  estado entre pai e filho para desenhar botao ja causou loop de
#  renderizacao neste projeto uma vez.
#
#  SO FRONTEND. Sem migration, sem passo de servidor, sem dependencia
#  nova. O deploy do CI faz rsync + restart e isso basta -- ao contrario
#  da 009, que precisou de python-pptx instalado a mao (ver a secao 5 do
#  claude/armadilhas-deploy-e-fuso.md).
#
#  FLUXO
#     0. pre-voo (os arquivos no disco sao mesmo os novos?)
#     1. testes locais (vitest + vite build)
#     2. push do ramo
#     3. CI do ramo -> PR -> merge na main -> deploy CONFERIDO pelo nome
#        do job (job pulado nao e job vermelho)
#     4. smoke
#
#  USO
#     .\deploy-010-acoes-no-topo.ps1
#     .\deploy-010-acoes-no-topo.ps1 -PularTestes     # se ja rodou vitest
#
#  ESTE ARQUIVO E ASCII PURO. Sem acento, sem e-comercial duplo, sem
#  sinal de maior/menor solto, sem redirecionamento de stderr em comando
#  externo -- ver o cabecalho do deploy-008 para o porque de cada um.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$Mensagem   = "feat(ui): acoes do modal no cabecalho, ao lado do X"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# Marcador por arquivo: prova que o que esta no disco e a versao nova, e
# nao a antiga com o mesmo nome. Ja aconteceu de um arquivo nao ter sido
# salvo e o deploy subir feliz.
$ESPERADOS = @(
    @{ Arquivo = "web\src\components\ui\Modal.jsx";                  Marcador = "AcoesDoModal" },
    @{ Arquivo = "web\src\components\crm\OportunidadeDetalhe.jsx";   Marcador = "AcoesDoModal" },
    @{ Arquivo = "web\src\pages\crm\Oportunidades.jsx";              Marcador = "acoes={" },
    @{ Arquivo = "web\src\pages\crm\Contas.jsx";                     Marcador = "acoes={" },
    @{ Arquivo = "web\src\tests\Modal.test.jsx";                     Marcador = "AcoesDoModal" },
    @{ Arquivo = "web\src\tests\Oportunidades.test.jsx";             Marcador = "toContainElement(barra)" }
)

# Classe exata do rodape antigo da oportunidade. Marcador ASCII de
# proposito: o aria-label da barra tem acento, e uma regex ASCII contra
# texto acentuado nunca casa -- viraria uma checagem que aprova sempre.
$RODAPE_ANTIGO = "border-t border-hipo-border bg-hipo-bg/40"

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
        Abortar "o CI ficou vermelho no run $runId. Nada foi para producao -- a versao antiga continua no ar. $REPO_URL"
    }
}

# Job pulado nao deixa run vermelho: um deploy que nunca rodou e um que
# funcionou sao iguais aos olhos do 'gh run watch'. Por isso, pelo nome.
function ExigirDeployFeito($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler os jobs do run $runId. $REPO_URL" }
    $deploy = @((($bruto | ConvertFrom-Json).jobs) | Where-Object { $_.name -like "Deploy*" })
    if ($deploy.Count -eq 0) { Abortar "o run $runId nao tem job de Deploy. $REPO_URL" }

    $conclusao = [string]$deploy[0].conclusion
    if ($conclusao -eq "success") { Bom "job de Deploy concluido com sucesso"; return }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. O ci-cd.yml so deploya em push na '$RamoAlvo'. O codigo esta no repositorio, mas NAO em producao."
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
        Abortar "arquivo da 010 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 010 estao no disco"

# Se a barra velha sobreviveu, a tela fica com DUAS barras de acao -- uma
# em cima e uma embaixo -- e o vitest nao reclama, porque as duas tem os
# mesmos botoes e o teste so procura pelo aria-label.
$detalhe = Get-Content "web\src\components\crm\OportunidadeDetalhe.jsx" -Raw
if ($detalhe -match [regex]::Escape($RODAPE_ANTIGO)) {
    Abortar "OportunidadeDetalhe.jsx ainda tem o rodape antigo ('$RODAPE_ANTIGO')."
}
Bom "o rodape antigo da oportunidade saiu"

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
$ramo  = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"
$noAlvo = ($ramo -eq $RamoAlvo)
if (-not $noAlvo) {
    Aviso "push em '$ramo' NAO deploya: o deploy so roda na '$RamoAlvo'. O script oferece o merge depois do CI."
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "o CI ainda vai rodar tudo. Isso so adianta a descoberta de erro."
}
else {
    Titulo "1. Testes locais"

    # So frontend: nenhuma linha de Python mudou nesta entrega. O CI roda
    # a suite do backend inteira de qualquer jeito.
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
# 2. Push
# =====================================================================

Titulo "2. Push do ramo"

$sujos = & git status --porcelain
if ($sujos) {
    Write-Host ""
    & git status --short
    Confirmar "Commitar e empurrar estes arquivos?"
    Executar "git add"    { git add -A }
    Executar "git commit" { git commit -m $Mensagem }
    Bom "commit criado"
}
else {
    Aviso "arvore limpa -- nada novo para commitar."
}

$aFrente = "0"
try   { $aFrente = (& git rev-list --count "origin/$ramo..$ramo").Trim() }
catch { $aFrente = "?" }

Executar "git push" { git push origin $ramo }
$empurrouAlgo = ($aFrente -ne "0")
Bom "codigo no repositorio, no ramo $ramo"

# =====================================================================
# 3. CI, merge e deploy
# =====================================================================

Titulo "3. CI e deploy"

if (-not $temGh) {
    Aviso "gh nao instalado -- abra o PR, mergeie e confira o job Deploy em $REPO_URL"
}
elseif ($noAlvo) {
    if ($empurrouAlgo) {
        $runMain = RunMaisRecente $RamoAlvo
        if ($runMain) {
            AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
            ExigirDeployFeito ([string]$runMain.databaseId)
        }
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
        else {
            Aviso "nenhum run novo no ramo -- pode ter rodado no evento de pull_request. $REPO_URL"
        }
    }

    $numeroPr = ""
    $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number
    if ($LASTEXITCODE -eq 0) {
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -gt 0) { $numeroPr = [string]$prs[0].number }
    }

    if (-not $numeroPr) {
        Passo "nenhum PR aberto -- criando"
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 010 -- acoes da tela no cabecalho do modal. So frontend: sem migration e sem passo de servidor."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se a mensagem foi 'No commits between $RamoAlvo and $ramo', o merge ja aconteceu e falta so o deploy: use o .\deploy-007-retomar.ps1."
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
        Abortar "merge feito mas nao vi run novo na $RamoAlvo. Confira em $REPO_URL antes de considerar entregue."
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
        Bom "API viva -- versao $($health.version)"
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

Titulo "Entregue"

Write-Host ""
Write-Host "  Recarregue com Ctrl+Shift+R -- e mudanca de assets." -ForegroundColor Green
Write-Host ""
Write-Host "  Confira nas tres telas que usam a barra:" -ForegroundColor Yellow
Write-Host "    1. Oportunidades -> abrir uma oportunidade" -ForegroundColor White
Write-Host "       Suspender / Finalizar / Fechar / Salvar em cima, junto do X." -ForegroundColor Gray
Write-Host "       Mexa num campo: o 'Tudo salvo' vira 'Alteracoes nao salvas'" -ForegroundColor Gray
Write-Host "       e o Salvar acende -- tudo isso no cabecalho agora." -ForegroundColor Gray
Write-Host "    2. Dentro dela, o predinho da conta abre o drilldown:" -ForegroundColor White
Write-Host "       'Voltar a oportunidade' e 'Salvar' tambem em cima, e o Esc" -ForegroundColor Gray
Write-Host "       continua fechando SO o drilldown." -ForegroundColor Gray
Write-Host "    3. Menu Contas -> abrir uma conta: Fechar / Salvar em cima." -ForegroundColor White
Write-Host ""
Write-Host "  Se em alguma tela sobrar uma barra embaixo TAMBEM, e rodape" -ForegroundColor Gray
Write-Host "  antigo que escapou -- me diga qual tela." -ForegroundColor Gray
Write-Host ""
