# =====================================================================
#  HIPO -- 011: da tarefa para a oportunidade (e dali para a conta)
# =====================================================================
#
#  O QUE MUDA
#
#  O modal da tarefa, no modulo de Tarefas, ganhou um botao que abre a
#  oportunidade EM CIMA dela -- a mesma visao 360 do funil, editavel. De
#  dentro dela o predinho da conta continua funcionando, entao a pilha
#  vai a tres degraus:
#
#      nivel 1  detalhe da tarefa  (kanban de Tarefas)
#      nivel 2  OportunidadeDetalhe
#      nivel 3  ContaDetalhe  /  ModalDesfecho
#
#  Motivo: a tarefa e sempre sobre ALGUMA COISA, e essa coisa e a
#  oportunidade. Quem abria "Cobrar proposta" precisava, no mesmo minuto,
#  da fase, do valor e do que foi conversado antes -- e isso custava
#  fechar tudo, ir ao funil e buscar o numero na mao, voltando para ca
#  sem lembrar em que cartao estava.
#
#  Empilha em vez de navegar: fechar o drilldown devolve o cartao
#  exatamente como estava, inclusive com o painel de concluir aberto e o
#  titulo da proxima tarefa ja digitado. Tem teste segurando isso.
#
#  COMO FOI FEITO
#
#  Sem backend. O TarefaOut ja entregava alvo, oportunidade_id,
#  oportunidade_numero, status_oportunidade, conta_id e
#  conta_razao_social -- os LEFT JOIN do _SELECT_BASE em
#  api/routers/crm_tarefas.py ja estavam la desde a 006. Nenhuma linha de
#  Python muda, nenhuma migration.
#
#  O unico ajuste fora de Tarefas.jsx foi no ModalDesfecho: o `nivel`
#  virou prop com padrao 2. No funil a oportunidade e o modal de nivel 1
#  e o desfecho e o 2; aqui a oportunidade JA e o 2 e o desfecho precisa
#  ser o 3. Com o 2 cravado no codigo, o formulario de Finalizar abriria
#  ATRAS da oportunidade -- exatamente o sintoma que o `nivel` foi criado
#  para matar, uma camada acima.
#
#  Tarefa de PARCEIRO nao tem oportunidade e por isso nao tem o botao.
#  Quem decide e alvo/oportunidade_id vindos do servidor, nao inferencia
#  de campo nulo.
#
#  SO FRONTEND. Sem migration, sem passo de servidor, sem dependencia
#  nova. O deploy do CI faz rsync + restart e isso basta.
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
#     .\deploy-011-drilldown-tarefa-oportunidade.ps1
#     .\deploy-011-drilldown-tarefa-oportunidade.ps1 -PularTestes
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
    [string]$Mensagem   = "feat(tarefas): drilldown da tarefa para a oportunidade e a conta"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# Marcador por arquivo: prova que o que esta no disco e a versao nova, e
# nao a antiga com o mesmo nome. Ja aconteceu de um arquivo nao ter sido
# salvo e o deploy subir feliz.
#
# Todos os marcadores sao ASCII de proposito: regex ASCII contra texto
# acentuado nunca casa, e viraria uma checagem que aprova sempre.
$ESPERADOS = @(
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";               Marcador = "abrirOportunidade" },
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";               Marcador = "components/crm/OportunidadeDetalhe" },
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";               Marcador = "nivel={3}" },
    @{ Arquivo = "web\src\components\crm\ModalDesfecho.jsx";    Marcador = "nivel={nivel}" },
    @{ Arquivo = "web\src\tests\Tarefas.test.jsx";              Marcador = "drilldown da oportunidade" }
)

# O nivel do desfecho tinha que sair de literal para prop. Se a linha
# antiga sobreviveu, o `nivel={3}` de Tarefas.jsx e decorativo e o
# formulario de Finalizar volta a abrir atras da oportunidade. O vitest
# do modulo de Tarefas nao pega isso: z-index nao existe no jsdom.
$NIVEL_CRAVADO = "nivel={2}"

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
        Abortar "arquivo da 011 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) marcadores da 011 conferem no disco"

$desfecho = Get-Content "web\src\components\crm\ModalDesfecho.jsx" -Raw
if ($desfecho -match [regex]::Escape($NIVEL_CRAVADO)) {
    Abortar "ModalDesfecho.jsx ainda tem '$NIVEL_CRAVADO' cravado. O nivel virou prop nesta entrega; com o literal de volta, Finalizar abre ATRAS da oportunidade no modulo de Tarefas."
}
Bom "o nivel do desfecho e prop, nao literal"

# Backend intocado nesta entrega. Se aparecer Python no diff, ou o
# escopo cresceu sem ninguem contar, ou veio arquivo a reboque -- e o
# texto do PR abaixo, que promete 'so frontend', vira mentira.
$pyMudado = @(& git diff --name-only HEAD -- "api/*.py")
if ($pyMudado.Count -gt 0) {
    Aviso "ha .py modificado no diff, e esta entrega deveria ser so frontend:"
    foreach ($f in $pyMudado) { Write-Host "       $f" -ForegroundColor Yellow }
    Confirmar "Seguir mesmo assim?"
}
else {
    Bom "nenhum .py tocado -- so frontend, como esperado"
}

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
    #
    # A suite de Oportunidades entra junto de proposito: ela e quem prova
    # que o ModalDesfecho continua abrindo no nivel 2 no funil depois de o
    # nivel virar prop.
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
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 011 -- drilldown da tarefa para a oportunidade e dali para a conta. O ModalDesfecho passa a receber o nivel por prop (padrao 2) para poder abrir no 3 quando a oportunidade ja e o 2. So frontend: sem migration e sem passo de servidor."
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
Write-Host "  Confira a pilha inteira, no modulo Tarefas:" -ForegroundColor Yellow
Write-Host "    1. Abra um cartao de tarefa DE OPORTUNIDADE." -ForegroundColor White
Write-Host "       No topo do modal tem a maleta com o numero e a empresa." -ForegroundColor Gray
Write-Host "    2. Clique: a oportunidade abre por cima, editavel, e o cartao" -ForegroundColor White
Write-Host "       da tarefa continua atras. Esc fecha SO a oportunidade." -ForegroundColor Gray
Write-Host "    3. Dentro dela, o predinho da conta abre o terceiro degrau." -ForegroundColor White
Write-Host "       'Voltar a oportunidade' devolve o degrau 2 intacto." -ForegroundColor Gray
Write-Host "    4. Ainda no degrau 2, clique em Finalizar: o formulario de" -ForegroundColor White
Write-Host "       desfecho tem de aparecer NA FRENTE da oportunidade." -ForegroundColor Gray
Write-Host "       Se abrir atras, o nivel={3} nao chegou -- me diga." -ForegroundColor Gray
Write-Host "    5. Abra um cartao de tarefa DE PARCEIRO: nao ha maleta." -ForegroundColor White
Write-Host "       Parceiro nao tem oportunidade; botao que abre nada seria" -ForegroundColor Gray
Write-Host "       pior que a ausencia dele." -ForegroundColor Gray
Write-Host ""
Write-Host "  E no funil (nada pode ter mudado la):" -ForegroundColor Yellow
Write-Host "    6. Oportunidades -> abrir uma -> Finalizar continua abrindo" -ForegroundColor White
Write-Host "       na frente, como sempre." -ForegroundColor Gray
Write-Host ""
Write-Host "  Teste ida e volta: abra o painel de concluir da tarefa, digite" -ForegroundColor Gray
Write-Host "  o titulo da proxima, abra a oportunidade e feche. O que voce" -ForegroundColor Gray
Write-Host "  digitou tem de estar la." -ForegroundColor Gray
Write-Host ""
