# =====================================================================
# HIPO -- deploy-007-retomar.ps1
#
# Retomada do deploy da 007 depois de um run cancelado.
#
# O QUE ACONTECEU
#
# O codigo foi mergeado na main (o 'No commits between main and
# feat/resumo-producao-tarefas' do gh e a prova: nao ha o que mergear
# porque a main JA TEM tudo). Mas o run da main -- o unico que deploya --
# foi cancelado antes de terminar. Resultado: repositorio em dia,
# producao na versao anterior.
#
# Deploy nao roda sozinho depois. O ci-cd.yml so libera o job com
#
#     if: github.ref == 'refs/heads/main'
#         AND (github.event_name == 'push' OR 'workflow_dispatch')
#
# Como nao vai haver push novo na main (nao ha o que empurrar), o caminho
# e o workflow_dispatch -- que a mesma condicao aceita. E o que este
# script faz: confere que a main tem mesmo o codigo, dispara o workflow
# nela, acompanha, e so canta vitoria se o job de Deploy ficar VERDE.
#
# Nao ha migration nesta entrega, entao repetir o deploy e seguro: o CI
# faz rsync dos arquivos e reinicia o servico, nada de DDL.
#
# ---------------------------------------------------------------------
# PLANO B, sem script: GitHub -> Actions -> HIPO CI/CD -> "Run workflow"
# -> escolher a branch main -> Run. Depois confira que o job
# "Deploy -> EC2" ficou verde, e nao pulado.
# ---------------------------------------------------------------------
#
# ESTE ARQUIVO E ASCII PURO -- ver o cabecalho do deploy-007 para o
# porque. Sem acento, sem e-comercial duplo, sem sinal de maior/menor.
#
# USO
#
#   .\deploy-007-retomar.ps1
#   .\deploy-007-retomar.ps1 -SmokeEmail seu-email@dominio.com
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularSmoke,

    # Dispara um run novo mesmo que o ultimo da main ja tenha Deploy verde.
    # Serve para o caso de aquele run verde ser ANTERIOR ao merge da 007.
    [switch]$Forcar,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$SmokeEmail = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# Marcador do codigo da 007 dentro de um dos arquivos. Serve para provar,
# lendo o que esta NA MAIN (nao no disco), que o merge realmente levou a
# entrega -- e nao so um commit qualquer.
$ARQUIVO_PROVA  = "api/routers/crm_oportunidades.py"
$MARCADOR_PROVA = "_MIN_DIGITOS_CNPJ"

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
    if ($LASTEXITCODE -ne 0) {
        Abortar "$descricao falhou (codigo $LASTEXITCODE)."
    }
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

# Conclusao do job de Deploy daquele run, lida PELO NOME. Devolve
# 'success', 'skipped', 'cancelled', 'failure', '' (ainda rodando) ou
# 'sem-job'. Nao aborta: quem decide o que fazer com a resposta e o
# chamador -- este script tanto exige o deploy quanto so pergunta se ele ja
# aconteceu, e sao decisoes diferentes.
function ConclusaoDoDeploy($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) { return "erro-de-leitura" }

    $jobs = @(($bruto | ConvertFrom-Json).jobs)
    $deploy = @($jobs | Where-Object { $_.name -like "Deploy*" })
    if ($deploy.Count -eq 0) { return "sem-job" }

    return [string]$deploy[0].conclusion
}

# A conferencia que nao pode faltar: 'gh run watch --exit-status' devolve o
# resultado do RUN, e job pulado nao deixa run vermelho. Um deploy que nunca
# rodou e um que rodou e funcionou sao iguais aos olhos do watch.
function ExigirDeployFeito($runId) {
    $conclusao = ConclusaoDoDeploy $runId

    if ($conclusao -eq "success") {
        Bom "job de Deploy concluido com sucesso"
        return
    }
    if ($conclusao -eq "erro-de-leitura") {
        Abortar "nao consegui ler os jobs do run $runId -- confira na mao em $REPO_URL"
    }
    if ($conclusao -eq "sem-job") {
        Abortar "o run $runId nao tem job de Deploy. O ci-cd.yml mudou? Confira em $REPO_URL"
    }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. Confira em $REPO_URL se o run saiu mesmo na branch $RamoAlvo."
    }
    Abortar "o job de Deploy terminou como '$conclusao' no run $runId. Veja o log em $REPO_URL"
}

# =====================================================================
# 0. Pre-voo -- onde a 007 esta de verdade
# =====================================================================

Titulo "0. Onde a 007 esta"

if (-not (Test-Path "api\main.py")) {
    Abortar "rode a partir da raiz do repositorio (a pasta que tem api\ e web\)."
}

if ($null -eq (Get-Command gh -ErrorAction SilentlyContinue)) {
    Abortar "gh nao instalado. Use o plano B: GitHub -> Actions -> HIPO CI/CD -> Run workflow -> branch $RamoAlvo."
}

Executar "git fetch" { git fetch origin --prune --quiet }

$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
$sha  = (& git rev-parse HEAD).Trim()
Passo "ramo local: $ramo  ($($sha.Substring(0,7)))"

# O commit local ja esta contido na main remota? E a pergunta que decide
# tudo: se sim, o merge aconteceu e falta so o deploy; se nao, ha entrega
# pendente e quem resolve e o deploy-007, nao este script.
& git merge-base --is-ancestor HEAD "origin/$RamoAlvo"
$naMain = ($LASTEXITCODE -eq 0)

if (-not $naMain) {
    Abortar "o commit local ainda NAO esta em origin/$RamoAlvo. Este script so retoma deploy de codigo ja mergeado -- rode o .\deploy-007-tarefas-do-usuario-e-busca.ps1 para abrir o PR e mergear."
}
Bom "o commit local ja esta em origin/$RamoAlvo -- o merge aconteceu"

Passo "topo da $RamoAlvo : $(& git log "origin/$RamoAlvo" -1 --oneline)"

# Prova de conteudo, nao de commit: le o arquivo COMO ESTA NA MAIN remota.
# Um merge pode existir e mesmo assim o codigo da entrega ter se perdido
# num conflito resolvido de qualquer jeito.
$naMainConteudo = & git show "origin/${RamoAlvo}:${ARQUIVO_PROVA}"
if ($naMainConteudo -match [regex]::Escape($MARCADOR_PROVA)) {
    Bom "o codigo da 007 esta no arquivo da $RamoAlvo (marcador $MARCADOR_PROVA)"
}
else {
    Abortar "$ARQUIVO_PROVA na $RamoAlvo nao tem '$MARCADOR_PROVA'. O merge entrou mas o codigo da 007 nao esta la -- pare e confira antes de deployar."
}

# =====================================================================
# 1. Estado do ultimo run da main
# =====================================================================

Titulo "1. Ultimo run da $RamoAlvo"

# Declarado antes de qualquer caminho que o leia: variavel nao inicializada
# no PowerShell vale $null e "funciona" por acidente ate alguem ligar o
# Set-StrictMode.
$jaFeito = $false

$ultimo = RunMaisRecente $RamoAlvo
if (-not $ultimo) {
    Aviso "nenhum run anterior na $RamoAlvo"
}
else {
    $idUltimo = [string]$ultimo.databaseId
    $situacao = [string]$ultimo.conclusion
    if (-not $situacao) { $situacao = [string]$ultimo.status }
    Passo "run $idUltimo -- evento $($ultimo.event), situacao '$situacao'"

    if ($situacao -eq "in_progress" -or $situacao -eq "queued") {
        # Vale para o re-run feito pela interface do GitHub: ele reaproveita
        # o run, entao nao nasce id novo -- quem disparasse outro workflow
        # aqui so faria o concurrency cancelar um dos dois.
        Aviso "ja ha um run rodando na $RamoAlvo (pode ser o seu re-run). Disparar outro agora faria o concurrency cancelar um deles."
        Confirmar "Acompanhar o run que JA esta rodando, em vez de disparar outro?"

        Passo "acompanhando o run $idUltimo..."
        & gh run watch $idUltimo --exit-status
        if ($LASTEXITCODE -ne 0) {
            Abortar "o run $idUltimo nao terminou verde. Veja $REPO_URL"
        }
        ExigirDeployFeito $idUltimo
        $jaFeito = $true
    }
    else {
        # Run ja concluido: a pergunta nao e "o run passou" (job pulado nao
        # deixa run vermelho) e sim "o job de Deploy passou".
        $conclusaoDeploy = ConclusaoDoDeploy $idUltimo
        Passo "job de Deploy nesse run: '$conclusaoDeploy'"

        if ($conclusaoDeploy -eq "success") {
            Bom "a $RamoAlvo ja tem um run com Deploy VERDE -- nao ha o que disparar"
            Aviso "se este run e anterior ao merge da 007, dispare mesmo assim: responda NAO na proxima pergunta e rode com -Forcar."
            $jaFeito = $true
        }
        elseif ($conclusaoDeploy -eq "cancelled") {
            Aviso "o Deploy desse run foi CANCELADO -- e o que deixou a producao para tras"
        }
        elseif ($conclusaoDeploy -eq "skipped") {
            Aviso "o Deploy foi pulado nesse run (provavelmente run de ramo ou de pull_request)"
        }
    }
}

if ($Forcar -and $jaFeito) {
    Aviso "-Forcar: vou disparar um run novo mesmo com o anterior verde"
    $jaFeito = $false
}

# =====================================================================
# 2. Disparar o deploy
# =====================================================================

if (-not $jaFeito) {
    Titulo "2. Disparar o deploy na $RamoAlvo"

    Write-Host ""
    Write-Host "  Vai rodar o HIPO CI/CD na branch $RamoAlvo via workflow_dispatch." -ForegroundColor White
    Write-Host "  E o mesmo gatilho que o push da main usaria -- a condicao do job" -ForegroundColor Gray
    Write-Host "  de deploy aceita os dois. Sem migration, repetir e seguro." -ForegroundColor Gray
    Confirmar "Disparar agora?"

    $idAntes = ""
    if ($ultimo) { $idAntes = [string]$ultimo.databaseId }

    Executar "gh workflow run" { gh workflow run ci-cd.yml --ref $RamoAlvo }

    # O run nao aparece na listagem no mesmo instante. Tenta algumas vezes
    # em vez de dormir um numero magico de segundos e torcer.
    $novo = $null
    for ($i = 1; $i -le 12; $i++) {
        Start-Sleep -Seconds 10
        $candidato = RunMaisRecente $RamoAlvo
        if ($candidato -and ([string]$candidato.databaseId) -ne $idAntes) {
            $novo = $candidato
            break
        }
        Passo "aguardando o run nascer... ($i de 12)"
    }

    if (-not $novo) {
        Abortar "disparei o workflow mas nao vi run novo na $RamoAlvo em 2 minutos. Confira em $REPO_URL"
    }

    Bom "run $($novo.databaseId) criado por $($novo.event)"
    Passo "acompanhando (os 3 jobs, deploy incluido)..."
    & gh run watch ([string]$novo.databaseId) --exit-status
    if ($LASTEXITCODE -ne 0) {
        Abortar "o CI ficou vermelho no run $($novo.databaseId). Nada de banco foi tocado; a producao segue no codigo anterior. Veja $REPO_URL"
    }
    ExigirDeployFeito ([string]$novo.databaseId)
}

# =====================================================================
# 3. Smoke test
# =====================================================================

Titulo "3. Smoke test"

# O passo "Verificar deploy" do CI roda
#     curl -sf http://localhost/health || echo 'Frontend OK'
# e depois do Certbot o localhost cai no bloco default do nginx e devolve
# 404 -- que o '||' engole. Aquele passo passa SEMPRE. Este bate na URL
# publica e falha alto.

# PowerShell 5.1 ainda negocia TLS 1.0 por padrao e o nginx so aceita 1.2
# para cima -- sem esta linha o erro parece problema de servidor, e nao e.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$falhou = $false

try {
    $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
    if ($health.status -eq "ok") { Bom "API viva -- versao $($health.versao)" }
    else { Aviso "API respondeu algo estranho: $($health | ConvertTo-Json -Compress)"; $falhou = $true }
}
catch {
    Aviso "API nao respondeu em $UrlPublica/api/health : $($_.Exception.Message)"
    $falhou = $true
}

try {
    $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
    if ($front.StatusCode -eq 200) { Bom "front servido (HTTP 200)" }
    else { Aviso "front devolveu HTTP $($front.StatusCode)"; $falhou = $true }
}
catch {
    Aviso "front nao respondeu: $($_.Exception.Message)"
    $falhou = $true
}

# Smoke autenticado: o unico passo que prova que a busca ampliada funciona
# CONTRA O BANCO DE PRODUCAO. O CI testa contra o Postgres do runner, criado
# do schema.sql; divergencia de coluna em producao so aparece aqui.
# Resultado vazio e sucesso -- o que se mede e responder 200.
if ($PularSmoke) {
    Aviso "smoke autenticado pulado por -PularSmoke"
}
elseif (-not $SmokeEmail) {
    Aviso "smoke autenticado nao rodou. Rode de novo com -SmokeEmail seu-email@dominio.com para exercitar a busca nova em producao."
}
elseif ($SmokeEmail -like "*@empresa.com" -or $SmokeEmail -like "seu-email*") {
    Aviso "'$SmokeEmail' e placeholder de exemplo, nao um login. Rode de novo com o seu e-mail de verdade."
}
else {
    $segura = Read-Host "  Senha de $SmokeEmail (nao aparece na tela)" -AsSecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    $senha  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

    try {
        $login = Invoke-RestMethod -Uri "$UrlPublica/api/auth/login" -Method Post `
            -Body @{ username = $SmokeEmail; password = $senha } `
            -ContentType "application/x-www-form-urlencoded" -TimeoutSec 20
        $cabecalho = @{ Authorization = "Bearer $($login.access_token)" }
        Bom "login em producao"

        $eu = Invoke-RestMethod -Uri "$UrlPublica/api/auth/me" -Headers $cabecalho -TimeoutSec 20
        Bom "sou $($eu.nome) -- id $($eu.id)"

        $kanban = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/tarefas/kanban?responsavel_id=$($eu.id)"
        $minhas = 0
        foreach ($col in $kanban) { $minhas = $minhas + $col.quantidade }
        Bom "kanban por responsavel respondeu -- $minhas tarefa(s) suas"

        $termos = @(
            @{ Rotulo = "CNPJ formatado"; Termo = "11.222.333/0001-81" },
            @{ Rotulo = "CNPJ parcial";   Termo = "11222333" },
            @{ Rotulo = "nome de pessoa"; Termo = "maria" },
            @{ Rotulo = "termo curto";    Termo = "22" }
        )
        foreach ($t in $termos) {
            $q = [uri]::EscapeDataString($t.Termo)
            $lista = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
                -Uri "$UrlPublica/api/crm/oportunidades?q=$q&limit=5"
            $resumo = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
                -Uri "$UrlPublica/api/crm/oportunidades/resumo?q=$q"
            Bom "busca por $($t.Rotulo): lista $($lista.total), resumo $($resumo.abertas) em aberto"
        }

        Bom "a busca ampliada responde em producao"
    }
    catch {
        Aviso "smoke autenticado falhou: $($_.Exception.Message)"
        $falhou = $true
    }
    finally {
        $senha = $null
    }
}

if ($falhou) {
    Abortar "o deploy rodou mas o smoke test nao passou. Olhe o servico: ssh e 'sudo systemctl status hipo'."
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Entregue"

Write-Host ""
Write-Host "  A 007 esta em producao." -ForegroundColor Green
Write-Host ""
Write-Host "  FACA LOGOUT E LOGIN em $UrlPublica -- e nao pule este passo." -ForegroundColor Yellow
Write-Host ""
Write-Host "  A tela de Tarefas descobre quem voce e pelo localStorage.hipo_user," -ForegroundColor Gray
Write-Host "  gravado no login. Sessao antiga pode nao ter o id gravado, e ai a" -ForegroundColor Gray
Write-Host "  tela abre em 'Todos os responsaveis' como antes -- parece que o" -ForegroundColor Gray
Write-Host "  deploy nao pegou, e pegou. Ctrl+Shift+R recarrega os assets mas NAO" -ForegroundColor Gray
Write-Host "  zera o localStorage." -ForegroundColor Gray
Write-Host ""
Write-Host "  Confira em Tarefas:" -ForegroundColor Gray
Write-Host "    - abre ja filtrada em voce, com '(voce)' no seletor" -ForegroundColor Gray
Write-Host "    - o X de limpar filtros NAO aparece nesse estado" -ForegroundColor Gray
Write-Host "    - trocar para 'Todos os responsaveis' mostra a equipe" -ForegroundColor Gray
Write-Host ""
Write-Host "  Confira em Oportunidades, na mesma caixa de busca:" -ForegroundColor Gray
Write-Host "    - numero, razao social, nome fantasia, CNPJ e nome de contato" -ForegroundColor Gray
Write-Host ""
