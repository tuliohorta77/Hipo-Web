# =====================================================================
#  HIPO -- 014: nao prospectar
# =====================================================================
#
#  O QUE MUDA
#
#  A conta ganha a marca "esta empresa ja e cliente da MedSeg, nao
#  prospecte". Nao e um terceiro estado de `ativo` nem parente de
#  `eh_finder`: e eixo proprio. A prova esta em producao -- a Oraculus
#  Contabil esta bloqueada E e a finder das 938 oportunidades da
#  carteira, ao mesmo tempo.
#
#    - contas: 5o KPI, filtro nos dois sentidos, badge na linha
#    - visao 360: banner com motivo e data, botao Liberar/Bloquear
#      (so gestao), painel inline para o motivo
#    - nova oportunidade: conta bloqueada aparece na lupa DESABILITADA
#    - POST /crm/oportunidades recusa com 422 estruturado
#    - PATCH /crm/contas/{id}/prospeccao, restrito a Franqueado e ADM
#
#  ATENCAO -- ESTA ENTREGA E O CONTRARIO DA 013
#
#  Na 013 os dados ja estavam no ar e faltava a tela. Aqui os DADOS JA
#  SUBIRAM (326 contas bloqueadas, 938 suspects da Oraculus, carga de
#  09/09/2026) e falta o CODIGO. Ou seja: neste exato momento a marca
#  existe no banco e NAO e respeitada -- um SDR consegue abrir
#  oportunidade numa conta bloqueada, porque o 422 ainda nao esta em
#  producao. Este deploy fecha essa janela.
#
#  A MIGRATION 010 JA FOI APLICADA (09/09/2026, pelo subir-carteira.ps1).
#  Este script NAO aplica DDL -- ele CONFERE que a coluna existe antes de
#  empurrar. Se o codigo subir sem a coluna, todo SELECT de /crm/contas
#  quebra, porque a lista passou a pedir c.nao_prospectar.
#
#  FLUXO
#     0. pre-voo (arquivos, marcadores, coluna em producao, escopo)
#     1. testes locais (vitest + vite build)
#     2. push -> CI -> deploy CONFERIDO pelo nome do job
#     3. smoke (health + a rota nova no openapi)
#
#  USO
#     .\deploy-014-nao-prospectar.ps1
#     .\deploy-014-nao-prospectar.ps1 -PularTestes
#     .\deploy-014-nao-prospectar.ps1 -PularConfereBanco   # se o SSH nao abrir
#
#  ESTE ARQUIVO E ASCII PURO. E nenhum argumento de comando nativo leva
#  aspas duplas -- o PowerShell 5.1 as remove ao montar a linha de
#  comando de um programa externo, e foi assim que a carga da Oraculus
#  quebrou na primeira tentativa.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,
    [switch]$PularConfereBanco,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$Chave      = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor   = "ec2-user@63.179.88.212",
    [string]$Mensagem   = "feat(crm): nao prospectar -- bloqueia oportunidade em conta ja cliente"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# Marcador por arquivo: prova que o arquivo no disco e a versao NOVA, e
# nao a que estava la antes. Test-Path sozinho nao distingue as duas.
$ESPERADOS = @(
    @{ Arquivo = "api\migrations\010_nao_prospectar.sql";      Marcador = "ck_contas_nao_prospectar" },
    @{ Arquivo = "api\schema.sql";                             Marcador = "ck_contas_nao_prospectar" },
    @{ Arquivo = "api\routers\crm_contas.py";                  Marcador = "prospeccao" },
    @{ Arquivo = "api\routers\crm_contas.py";                  Marcador = "CARGOS_GESTAO" },
    @{ Arquivo = "api\routers\crm_oportunidades.py";           Marcador = "_validar_prospeccao" },
    @{ Arquivo = "api\tests\test_crm_contas.py";               Marcador = "TestNaoProspectar" },
    @{ Arquivo = "api\tests\test_crm_oportunidades.py";        Marcador = "TestContaNaoProspectar" },
    @{ Arquivo = "web\src\pages\crm\Contas.jsx";               Marcador = "nao-prospectar" },
    @{ Arquivo = "web\src\components\crm\ContaDetalhe.jsx";    Marcador = "mudarProspeccao" },
    @{ Arquivo = "web\src\pages\crm\Oportunidades.jsx";        Marcador = "tomDesabilitado" },
    @{ Arquivo = "web\src\components\EntityPicker.jsx";        Marcador = "tomDesabilitado" },
    @{ Arquivo = "web\src\tests\ContaDetalhe.test.jsx";        Marcador = "nao prospectar" }
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
        Abortar "arquivo da 014 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) marcadores da 014 conferem"

# O CI monta o banco de teste com `psql -f api/schema.sql`, NAO com as
# migrations. Migration nova sem espelhar no schema.sql passa na maquina
# de quem migrou a mao e derruba dezenas de testes no runner -- ja
# custou 45 de uma vez, com a fase 'suspect'.
$schema = Get-Content "api\schema.sql" -Raw
foreach ($coluna in @("nao_prospectar", "nao_prospectar_motivo", "nao_prospectar_em", "nao_prospectar_por")) {
    if ($schema -notmatch [regex]::Escape($coluna)) {
        Abortar "api\schema.sql nao tem a coluna '$coluna'. O CI cria o banco de teste a partir dele."
    }
}
if ($schema -notmatch [regex]::Escape("idx_contas_nao_prospectar")) {
    Abortar "api\schema.sql nao tem o indice idx_contas_nao_prospectar."
}
Bom "schema.sql espelha a migration 010"

# A ORDEM QUE IMPORTA: a coluna precisa existir em producao ANTES do
# codigo subir. /crm/contas passou a pedir c.nao_prospectar no SELECT --
# sem a coluna, a tela de Contas inteira devolve 500. A migration ja
# rodou em 09/09/2026, mas conferir e barato e o custo de nao conferir e
# a tela principal fora do ar.
if ($PularConfereBanco) {
    Titulo "0b. Coluna em producao -- PULADA"
    Aviso "voce assumiu que a migration 010 ja esta aplicada."
}
else {
    Passo "conferindo pelo SSH se a coluna ja existe em producao..."
    $shColuna = "scripts\conferir_coluna_remoto.sh"
    if (-not (Test-Path $shColuna)) { Abortar "nao encontrei $shColuna" }
    if (-not (Test-Path $Chave))    { Abortar "nao encontrei a chave SSH: $Chave" }

    $respostaBanco = ""
    try {
        scp -i $Chave $shColuna "${Servidor}:/tmp/conferir_coluna_remoto.sh" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "scp falhou" }
        $respostaBanco = ssh -i $Chave $Servidor "tr -d '\r' < /tmp/conferir_coluna_remoto.sh > /tmp/conferir-coluna.sh && bash /tmp/conferir-coluna.sh contas nao_prospectar | tail -1"
        if ($LASTEXITCODE -ne 0) { throw "ssh falhou" }
    }
    catch {
        # SSH fechado por IP novo e o caso comum, e nao e motivo para
        # abortar um deploy bom -- por isso pergunta em vez de morrer.
        Aviso "nao consegui falar com a EC2: $($_.Exception.Message)"
        Aviso "se for o IP, rode .\liberar-meu-ip-ssh.ps1 e tente de novo."
        Confirmar "Seguir SEM conferir a coluna? (se ela nao existir, /crm/contas quebra)"
        $respostaBanco = "SIM"
    }

    if ("$respostaBanco".Trim() -ne "SIM") {
        Abortar @"
A coluna nao_prospectar NAO existe em producao.

NAO empurre este codigo: /crm/contas pede c.nao_prospectar no SELECT e a
tela de Contas devolveria 500 para todo mundo.

Aplique a migration primeiro:

  .\scripts\subir-carteira.ps1 -FinderCnpj 15435766000176 -AplicarMigration -PularMedseg -PularOraculus
"@
    }
    Bom "coluna nao_prospectar presente em producao"
}

# git status --porcelain enxerga tracked E untracked. `git diff` nao ve
# arquivo novo, e foi assim que a 011 anunciou "so frontend" levando um
# .py a reboque.
$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }

    # Ao contrario da 013: aqui .py e ESPERADO. A ausencia dele e que e
    # suspeita -- significaria que os routers ficaram para tras e a tela
    # subiria chamando uma rota que nao existe.
    $pyMudado = @($sujos | Where-Object { $_ -match '\.py$' })
    if ($pyMudado.Count -eq 0) {
        Write-Host ""
        Aviso "NENHUM .py no commit. Esta entrega mexe nos routers -- sem eles"
        Aviso "a tela chama PATCH /prospeccao e leva 404."
        Confirmar "Seguir mesmo assim?"
    }
    else { Bom "$($pyMudado.Count) arquivo(s) .py no commit -- backend junto, como esperado" }
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

    # So o front roda aqui. O pytest local no Windows sem Postgres
    # quebra em todo teste com db_conn -- e os 21 testes novos da 014
    # sao todos de banco. Quem valida o backend e o CI, que sobe o
    # servico de Postgres e monta o schema.
    Aviso "backend so no CI (pytest local sem Postgres quebra nos testes de db)"

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
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 014 -- nao prospectar: marca em contas, endpoint restrito a gestao, 422 na criacao de oportunidade e a tela. Os dados ja subiram em 09/09/2026; a migration 010 ja esta aplicada."
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
        # `versao`, e nao `version`: e o nome do campo em /health.
        $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
        if (-not $health.versao) { Abortar "/health respondeu sem 'versao'" }
        Bom "API viva -- versao $($health.versao)"
    }
    catch { Abortar "a API nao respondeu: $($_.Exception.Message)" }

    # /api/openapi.json, e nao /openapi.json: a API vive atras do nginx
    # no prefixo /api. Na raiz o nginx serve o index.html do front, que
    # responde 200 sem `paths` -- falso negativo que ja abortou um
    # deploy bom na 013.
    Passo "a rota nova esta servindo?"
    try {
        $doc = Invoke-RestMethod -Uri "$UrlPublica/api/openapi.json" -TimeoutSec 25
        if (-not $doc.paths) {
            Aviso "a resposta nao parece o documento OpenAPI (sem 'paths')."
            Confirmar "Seguir sem essa conferencia?"
        }
        else {
            $rotas = $doc.paths.PSObject.Properties.Name
            if ($rotas -notcontains '/crm/contas/{conta_id}/prospeccao') {
                Abortar "o deploy passou mas a API NAO tem /crm/contas/{conta_id}/prospeccao. O codigo velho ainda esta servindo."
            }
            Bom "PATCH /crm/contas/{conta_id}/prospeccao no ar"
        }
    }
    catch {
        Aviso "nao consegui ler o openapi: $($_.Exception.Message)"
        Confirmar "Seguir sem essa conferencia?"
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

Titulo "Nao prospectar no ar"

Write-Host ""
Write-Host "  FACA LOGOUT E LOGIN -- nao basta Ctrl+Shift+R." -ForegroundColor Green
Write-Host "  O front le o cargo do localStorage.hipo_user, gravado no login," -ForegroundColor Gray
Write-Host "  e e o cargo que decide se os botoes de bloqueio aparecem." -ForegroundColor Gray
Write-Host ""
Write-Host "  O roteiro que os testes NAO cobrem:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    1. Contas -> o KPI 'Nao prospectar' deve mostrar 326." -ForegroundColor White
Write-Host "       Clique nele: a lista filtra. Clique de novo: desfaz." -ForegroundColor Gray
Write-Host "    2. Abra uma dessas contas. Banner vermelho com o motivo" -ForegroundColor White
Write-Host "       'Cliente da Controller MedSeg' e a data." -ForegroundColor Gray
Write-Host "    3. O badge 'Nao prospectar' aparece na linha AO LADO do de" -ForegroundColor White
Write-Host "       'Ativa', nao no lugar dele -- sao eixos diferentes." -ForegroundColor Gray
Write-Host "    4. Nova oportunidade -> lupa da conta -> busque uma" -ForegroundColor White
Write-Host "       bloqueada. Ela aparece cinza, com badge vermelho, e o" -ForegroundColor Gray
Write-Host "       clique NAO seleciona." -ForegroundColor Gray
Write-Host "    5. O TESTE QUE VALE: entre com um SDR e tente criar" -ForegroundColor White
Write-Host "       oportunidade numa conta bloqueada. Tem de vir 422 com o" -ForegroundColor Gray
Write-Host "       motivo. Ate este deploy, isso PASSAVA." -ForegroundColor Gray
Write-Host "    6. Ainda como SDR: o banner aparece, o botao Liberar NAO." -ForegroundColor White
Write-Host "       Com Franqueado ou ADM, os dois aparecem." -ForegroundColor Gray
Write-Host "    7. Parceiros -> a Oraculus Contabil deve estar la, com 943" -ForegroundColor White
Write-Host "       indicacoes e conversao '--' (ainda nao ha denominador)." -ForegroundColor Gray
Write-Host "       Ela esta bloqueada E e parceira: e proposital." -ForegroundColor Gray
Write-Host ""
Write-Host "  Pendencias que este deploy NAO resolve:" -ForegroundColor Yellow
Write-Host "    - AERO PALETES: encerrar o negocio e bloquear pela tela" -ForegroundColor Gray
Write-Host "      (esta em api\scripts\dados\medseg_fora.csv)" -ForegroundColor Gray
Write-Host "    - 7 CNPJ com digito verificador errado na planilha" -ForegroundColor Gray
Write-Host "    - divisao 467/471 entre Gabriel e Kethlleen" -ForegroundColor Gray
Write-Host ""
