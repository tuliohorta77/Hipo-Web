# =====================================================================
# HIPO -- deploy-008-drilldown-conta.ps1
#
# Entrega da 008:
#   1. dentro da oportunidade, a empresa vira botao no trilho e abre a
#      visao 360 da conta EM CIMA, editavel -- o mesmo ContaDetalhe da tela
#      de Contas, com as mesmas props
#   2. salvar a conta dali recarrega o funil e a oportunidade (a razao
#      social aparece nos dois; sem recarregar, renomear mostra o nome
#      antigo ao fechar e parece que nao salvou)
#   3. fix no Modal compartilhado: o Esc fechava TODOS os modais abertos de
#      uma vez, porque cada instancia escutava keydown na window. Com dois
#      empilhados, fechar o drilldown levava junto a oportunidade em edicao.
#      Agora ha uma pilha e so o modal do topo responde a tecla.
#
# ATENCAO AO ITEM 3: components/ui/Modal.jsx e usado por TODAS as telas.
# Por isso a suite inteira do vitest roda aqui, nao so os testes tocados.
#
# ESTA ENTREGA NAO TEM MIGRATION, e nao muda backend nenhum -- e frontend
# puro. O pre-voo confere as duas coisas.
#
# ---------------------------------------------------------------------
# PUSH NO RAMO NAO DEPLOYA -- a licao da 007.
#
# O job de deploy do ci-cd.yml e guardado por
#
#     if: github.ref == 'refs/heads/main'
#         AND (github.event_name == 'push' OR 'workflow_dispatch')
#
# Empurrando um ramo de feature, o Actions roda os jobs de teste e PULA o
# de deploy. Pulado NAO e falha: o run fecha como 'success' e o
# 'gh run watch --exit-status' devolve zero. Por isso a conclusao do job de
# deploy e lida pelo NOME, e nao pelo resultado global do run.
# ---------------------------------------------------------------------
#
# ORDEM:
#   0. pre-voo
#   1. testes locais (vitest completo + build)
#   2. push do ramo
#   3. CI do ramo
#   4. merge na main -> CI da main -> deploy de verdade
#   5. smoke test
#
# ---------------------------------------------------------------------
# ESTE ARQUIVO E ASCII PURO, DE PROPOSITO.
#
# O PowerShell 5.1 le .ps1 sem BOM como ANSI. Um unico caractere acentuado
# -- mesmo dentro de comentario -- desbalanceia string e derruba o parser
# do arquivo inteiro. Sem acento, sem e-comercial duplo, sem sinal de
# maior/menor solto. Nao "conserte" a grafia.
# ---------------------------------------------------------------------
#
# USO
#
#   .\deploy-008-drilldown-conta.ps1
#   .\deploy-008-drilldown-conta.ps1 -PularTestes
#   .\deploy-008-drilldown-conta.ps1 -SmokeEmail seu-email@dominio.com
#   .\deploy-008-drilldown-conta.ps1 -PararNoRamo
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,
    [switch]$PararNoRamo,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$SmokeEmail = "",
    [string]$Mensagem   = "feat(crm): drilldown editavel da conta dentro da oportunidade; fix(ui): Esc fecha so o modal do topo"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# Os arquivos da entrega, cada um com um marcador que prova que o conteudo
# novo esta no disco. Pasta de versao errada e o jeito mais facil de
# empurrar o codigo antigo achando que subiu o novo.
$ESPERADOS = @(
    @{ Arquivo = "web\src\pages\crm\Oportunidades.jsx";      Marcador = "acaoSalvarConta" },
    @{ Arquivo = "web\src\components\crm\OportunidadeDetalhe.jsx"; Marcador = "onAbrirConta" },
    @{ Arquivo = "web\src\components\ui\Modal.jsx";          Marcador = "pilhaDeModais" },
    @{ Arquivo = "web\src\tests\Oportunidades.test.jsx";     Marcador = "drilldown da conta" },
    @{ Arquivo = "web\src\tests\Modal.test.jsx";             Marcador = "Esc com modais empilhados" }
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

# Roda comando externo e aborta se o codigo de saida nao for zero. Existe
# porque $ErrorActionPreference NAO pega falha de .exe -- so de cmdlet.
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

# -- Helpers do gh ----------------------------------------------------

# O @() em volta e necessario: no PowerShell 5.1 um ConvertFrom-Json de
# array com UM elemento devolve o objeto solto, e ai [0] indexa o objeto em
# vez da lista.
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
    # Watch do run ESPECIFICO, nunca 'gh run watch' pelado: sem o id ele abre
    # menu para escolher quando ha mais de um run em andamento, e num script
    # isso trava esperando tecla que ninguem vai apertar.
    Passo "acompanhando o run $runId ($oQueEsperar)..."
    & gh run watch $runId --exit-status
    if ($LASTEXITCODE -ne 0) {
        Abortar "o CI ficou vermelho no run $runId. Nada foi para producao -- ela segue com o codigo anterior. Corrija e empurre de novo. Detalhes: $REPO_URL"
    }
}

# 'gh run watch --exit-status' devolve o resultado do RUN, e job pulado nao
# deixa run vermelho. Um deploy que nunca rodou e um que rodou e funcionou
# sao iguais aos olhos do watch -- por isso a leitura por nome.
function ExigirDeployFeito($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) {
        Abortar "nao consegui ler os jobs do run $runId -- confira na mao em $REPO_URL"
    }
    $jobs = @(($bruto | ConvertFrom-Json).jobs)
    $deploy = @($jobs | Where-Object { $_.name -like "Deploy*" })

    if ($deploy.Count -eq 0) {
        Abortar "o run $runId nao tem job de Deploy. O ci-cd.yml mudou? Confira em $REPO_URL"
    }

    $conclusao = [string]$deploy[0].conclusion
    if ($conclusao -eq "success") {
        Bom "job de Deploy concluido com sucesso"
        return
    }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. O ci-cd.yml so deploya em push na '$RamoAlvo'. O codigo esta no repositorio, mas NAO esta em producao."
    }
    Abortar "o job de Deploy terminou como '$conclusao' no run $runId. Veja o log em $REPO_URL"
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
        Abortar "arquivo da 008 nao encontrado: $($item.Arquivo). Voce esta na pasta certa da versao?"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) existe mas nao tem '$($item.Marcador)' -- essa e a versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 008 estao no disco, com o conteudo novo"

# Guarda de escopo: migration muda a ordem correta (DDL em producao ANTES do
# push) e este script nao faz DDL.
$migracoesNovas = @(& git status --porcelain -- "api/migrations")
if ($migracoesNovas.Count -gt 0) {
    Write-Host ""
    $migracoesNovas | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Abortar "ha migration pendente no git status. A 008 e frontend puro. Aplique o DDL em producao ANTES do push, com um script proprio."
}
Bom "nenhuma migration pendente"

# A 008 nao toca backend. Se aparecer arquivo de api\ modificado, ou a
# entrega cresceu sem querer, ou o script errado esta sendo usado.
$backendSujo = @(& git status --porcelain -- "api")
if ($backendSujo.Count -gt 0) {
    Write-Host ""
    $backendSujo | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Aviso "ha mudanca em api\ nesta leva -- a 008 deveria ser so frontend. Confira antes de seguir."
    Confirmar "Seguir mesmo assim?"
}
else {
    Bom "api\ intacta -- entrega de frontend, como esperado"
}

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
if (-not $temGh) {
    Aviso "gh nao instalado -- o script empurra o codigo, mas o PR, o merge e a conferencia do deploy ficam por sua conta em $REPO_URL"
}

$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"

$noAlvo = ($ramo -eq $RamoAlvo)
if ($noAlvo) {
    Bom "voce ja esta na '$RamoAlvo' -- o push daqui deploya direto"
}
else {
    Aviso "push em '$ramo' NAO deploya: o deploy so roda na '$RamoAlvo'. Depois do CI verde, o script oferece o merge."
}

$sujos = & git status --porcelain
if (-not $sujos) {
    Aviso "arvore limpa -- ou voce ja commitou, ou os arquivos nao foram salvos na pasta do repositorio."
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "voce escolheu pular. A suite ainda roda no CI."
}
else {
    Titulo "1. Testes locais"

    # A suite INTEIRA do vitest, nao so os arquivos tocados: o Modal.jsx e
    # compartilhado por todas as telas, e a mudanca do Esc afeta qualquer uma
    # que abra modal.
    Push-Location "web"
    try {
        Executar "vitest (suite completa)" { npx vitest run }
        Bom "frontend verde"
        Executar "vite build" { npx vite build }
        Bom "build verde"
    }
    finally { Pop-Location }

    # Backend nao foi tocado, mas as regras puras custam segundos e pegam
    # qualquer coisa que tenha entrado na leva sem querer.
    Push-Location "api"
    try {
        $env:PYTHONPATH   = (Get-Location).Path
        $env:DATABASE_URL = "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test"
        Executar "pytest -- regras puras" {
            python -m pytest -q --no-cov `
                tests\test_tarefa_regras.py `
                tests\test_oportunidade_regras.py `
                tests\test_cnpj.py
        }
        Bom "regras puras verdes"
    }
    finally { Pop-Location }
}

# =====================================================================
# 2. Push do ramo
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

# Quantos commits o ramo tem a frente do GitHub. Sem isso, rodar o script de
# novo com tudo empurrado faria o passo 3 esperar um run que nunca nasce.
$aFrente = "0"
try   { $aFrente = (& git rev-list --count "origin/$ramo..$ramo").Trim() }
catch { $aFrente = "?" }

Executar "git push" { git push origin $ramo }
Bom "codigo no repositorio, no ramo $ramo"

$empurrouAlgo = ($aFrente -ne "0")

# =====================================================================
# 3. CI do ramo
# =====================================================================

Titulo "3. CI do ramo"

if (-not $temGh) {
    Aviso "sem gh -- acompanhe em $REPO_URL e depois mergeie na $RamoAlvo na mao"
}
elseif (-not $empurrouAlgo) {
    Aviso "nada novo foi empurrado -- nao vai nascer run novo neste ramo. Seguindo para o merge."
}
else {
    $antes = RunMaisRecente $ramo
    $idAntes = ""
    if ($antes) { $idAntes = [string]$antes.databaseId }

    $atual = EsperarRunNovo $ramo $idAntes

    if (-not $atual) {
        # Nao dispara workflow_dispatch aqui de proposito: no ramo ele so
        # repetiria os testes, e dois runs simultaneos colidem no concurrency.
        Aviso "nenhum run novo apareceu no ramo. Se ha PR aberto, o Actions pode ter rodado no evento de pull_request -- confira em $REPO_URL"
    }
    else {
        AcompanharRun ([string]$atual.databaseId) "Backend Tests + Frontend Tests"
        Bom "testes verdes no ramo $ramo"
        # Sem ExigirDeployFeito aqui: neste run o deploy e pulado por projeto.
    }
}

if ($PararNoRamo) {
    Titulo "Fim -- parado no ramo, como voce pediu"
    Write-Host "  O codigo esta no GitHub e passou nos testes." -ForegroundColor Gray
    Write-Host "  NAO esta em producao: falta o merge na $RamoAlvo." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# =====================================================================
# 4. Merge na main -- o deploy de verdade
# =====================================================================

Titulo "4. Merge na $RamoAlvo e deploy"

if ($noAlvo) {
    Bom "ja estamos na $RamoAlvo -- o push do passo 2 e o gatilho do deploy"

    if ($temGh -and $empurrouAlgo) {
        $runMain = RunMaisRecente $RamoAlvo
        if ($runMain) {
            AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
            ExigirDeployFeito ([string]$runMain.databaseId)
        }
        else {
            Aviso "nao identifiquei o run da $RamoAlvo -- confira em $REPO_URL"
        }
    }
}
elseif (-not $temGh) {
    Abortar "sem o gh nao da para mergear daqui. Abra o PR de '$ramo' para '$RamoAlvo', mergeie, e confira em $REPO_URL que o job 'Deploy' ficou VERDE (nao pulado)."
}
else {
    $numeroPr = ""
    $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number,title
    if ($LASTEXITCODE -eq 0) {
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -gt 0) { $numeroPr = [string]$prs[0].number }
    }

    if ($numeroPr) {
        Passo "PR #$numeroPr ja aberto para $RamoAlvo"
    }
    else {
        Passo "nenhum PR aberto -- criando"
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 008. Deploy pelo deploy-008-drilldown-conta.ps1."
        if ($LASTEXITCODE -ne 0) {
            # O erro 'No commits between main and o-seu-ramo' cai aqui, e
            # quase sempre significa que o merge JA aconteceu -- nao que deu
            # errado.
            Abortar "nao consegui criar o PR. Se a mensagem foi 'No commits between $RamoAlvo and $ramo', o merge ja foi feito e falta so o deploy: use o .\deploy-007-retomar.ps1, que dispara o workflow na $RamoAlvo."
        }
        $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -eq 0) { Abortar "PR criado mas nao encontrado na listagem. Confira em $REPO_URL" }
        $numeroPr = [string]$prs[0].number
        Bom "PR #$numeroPr criado"
    }

    Write-Host ""
    Write-Host "  O merge do PR #$numeroPr e o que coloca a 008 em producao." -ForegroundColor White
    Confirmar "Mergear o PR #$numeroPr em $RamoAlvo agora?"

    # Guarda o id do run atual da main ANTES do merge: sem isso, um run antigo
    # passaria por novo e o script anunciaria um deploy que nao aconteceu.
    $antesMain = RunMaisRecente $RamoAlvo
    $idAntesMain = ""
    if ($antesMain) { $idAntesMain = [string]$antesMain.databaseId }

    Executar "gh pr merge" { gh pr merge $numeroPr --merge }
    Bom "PR #$numeroPr mergeado na $RamoAlvo"

    $runMain = EsperarRunNovo $RamoAlvo $idAntesMain 60
    if (-not $runMain) {
        Abortar "o merge foi feito mas nao vi run novo na $RamoAlvo. Confira em $REPO_URL antes de considerar entregue."
    }

    AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
    ExigirDeployFeito ([string]$runMain.databaseId)
}

# =====================================================================
# 5. Smoke test
# =====================================================================

Titulo "5. Smoke test"

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

# Smoke autenticado: exercita os endpoints que o drilldown passa a chamar.
# Nenhum deles e novo, mas e barato provar que respondem em producao antes
# de descobrir pelo usuario que o botao abre um modal vazio.
if ($PularSmoke) {
    Aviso "smoke autenticado pulado por -PularSmoke"
}
elseif (-not $SmokeEmail) {
    Aviso "smoke autenticado nao rodou. Rode de novo com -SmokeEmail seu-email@dominio.com"
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

        # As verticais alimentam o seletor do ContaDetalhe -- o drilldown as
        # busca na primeira abertura.
        $verticais = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/dominio/verticais"
        Bom "verticais respondeu -- $(@($verticais).Count) item(ns)"

        # Pega uma oportunidade real e abre a conta dela pelo mesmo caminho
        # que o botao do trilho usa: conta_id da oportunidade -> /crm/contas/{id}.
        $lista = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/oportunidades?limit=1"
        if ($lista.total -eq 0) {
            Aviso "nao ha oportunidade em producao para exercitar o drilldown -- pulei essa parte"
        }
        else {
            $opp = $lista.itens[0]
            Bom "oportunidade de amostra: $($opp.numero) -- $($opp.conta_razao_social)"

            $conta = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
                -Uri "$UrlPublica/api/crm/contas/$($opp.conta_id)"
            if ($conta.razao_social) {
                Bom "drilldown da conta responde -- $($conta.razao_social), $(@($conta.contatos).Count) contato(s), $(@($conta.oportunidades).Count) oportunidade(s)"
            }
            else {
                Aviso "a conta respondeu sem razao_social -- payload estranho"
                $falhou = $true
            }
        }
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
    Abortar "o deploy subiu mas o smoke test nao passou. Olhe o servico: ssh e 'sudo systemctl status hipo'."
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Entregue"

Write-Host ""
Write-Host "  A 008 esta em producao." -ForegroundColor Green
Write-Host ""
Write-Host "  Recarregue a pagina (Ctrl+Shift+R) -- e frontend, nao precisa" -ForegroundColor Gray
Write-Host "  de logout desta vez." -ForegroundColor Gray
Write-Host ""
Write-Host "  Confira, abrindo uma oportunidade:" -ForegroundColor Gray
Write-Host "    - no topo do trilho, a empresa virou botao" -ForegroundColor Gray
Write-Host "    - clicar abre a conta POR CIMA, com os campos editaveis" -ForegroundColor Gray
Write-Host "    - as abas da conta funcionam: Oportunidades, Contatos," -ForegroundColor Gray
Write-Host "      Endereco, Telefones, Observacoes, Historico" -ForegroundColor Gray
Write-Host "    - 'Voltar a oportunidade' devolve a tela de tras intacta" -ForegroundColor Gray
Write-Host "    - digite algo na Descricao ANTES de abrir a conta: ao voltar," -ForegroundColor Gray
Write-Host "      o texto tem que continuar la" -ForegroundColor Gray
Write-Host "    - renomear a empresa e salvar muda o nome no cartao do funil" -ForegroundColor Gray
Write-Host ""
Write-Host "  E o teste do Esc, que e o fix compartilhado:" -ForegroundColor Yellow
Write-Host "    - com a conta aberta por cima, Esc fecha SO a conta" -ForegroundColor Gray
Write-Host "    - Esc de novo fecha a oportunidade" -ForegroundColor Gray
Write-Host "    - em qualquer outra tela, Esc continua fechando o modal" -ForegroundColor Gray
Write-Host ""
