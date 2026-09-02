# =====================================================================
# HIPO -- deploy-007-tarefas-do-usuario-e-busca.ps1
#
# Entrega da 007:
#   1. a tela de Tarefas abre filtrada no responsavel logado
#   2. a busca do funil acha por numero, empresa, fantasia, contato e CNPJ
#   3. correcao de fuso em dois arquivos de teste: eles perguntavam "que dia
#      e hoje" ao relogio da maquina (UTC no runner) enquanto o codigo
#      recorta o dia em America/Sao_Paulo. Entre 21h e meia-noite de
#      Brasilia os dois discordam, e 9 testes ficavam vermelhos sem ninguem
#      ter mexido em nada. Nao ha mudanca de codigo de producao aqui.
#
# ESTA ENTREGA NAO TEM MIGRATION. Nenhuma coluna, nenhum indice, nenhum
# CHECK novo -- so codigo. O script CONFERE isso no pre-voo: se aparecer
# arquivo novo em api\migrations, ele aborta, porque ai a ordem correta
# seria outra (banco antes do push) e este script nao faz DDL.
#
# ORDEM:  testes locais -> push -> CI -> smoke test
#
# Nenhuma etapa continua se a anterior falhar.
#
# ---------------------------------------------------------------------
# ESTE ARQUIVO E ASCII PURO, DE PROPOSITO.
#
# O PowerShell 5.1 le .ps1 sem BOM como ANSI. Um unico caractere acentuado
# -- mesmo dentro de comentario -- desbalanceia string e derruba o parser
# do arquivo inteiro. Por isso nao ha acento, cedilha nem travessao aqui.
# Nao "conserte" a grafia.
#
# Tambem nao ha encadeamento com e-comercial duplo (nao existe no 5.1, e
# como e erro de parse NADA do bloco roda) nem sinais de maior/menor soltos
# (sao operadores de redirecionamento reservados).
# ---------------------------------------------------------------------
#
# USO
#
#   .\deploy-007-tarefas-do-usuario-e-busca.ps1
#   .\deploy-007-tarefas-do-usuario-e-busca.ps1 -PularTestes
#   .\deploy-007-tarefas-do-usuario-e-busca.ps1 -SmokeEmail voce@empresa.com
#
# O -SmokeEmail e o que vale a pena: ele bate na API de producao ja
# autenticado e exercita a consulta NOVA. Erro de SQL na busca so aparece
# em runtime -- HTTP 200 no /health nao prova nada sobre ela.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,

    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$SmokeEmail = "",
    [string]$Mensagem   = "feat(crm): tarefas abrem no responsavel logado; busca do funil por numero, empresa, fantasia, contato e CNPJ; fix(tests): dia de calendario no fuso da operacao"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# Os arquivos desta entrega, com um marcador que prova que o conteudo novo
# esta mesmo no disco. Pasta versionada errada (v1.3.x em vez de v1.4.0) e
# o jeito mais facil de empurrar o codigo antigo achando que subiu o novo.
$ESPERADOS = @(
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";            Marcador = "padraoResponsavel" },
    @{ Arquivo = "web\src\tests\Tarefas.test.jsx";           Marcador = "mockGetUser" },
    @{ Arquivo = "api\routers\crm_oportunidades.py";         Marcador = "_MIN_DIGITOS_CNPJ" },
    @{ Arquivo = "api\tests\test_crm_oportunidades.py";      Marcador = "TestMontagemDaBuscaTextual" },
    @{ Arquivo = "web\src\pages\crm\Oportunidades.jsx";      Marcador = "empresa, contato ou CNPJ" },

    # Correcao de fuso que veio junto. O CI de 00:49 UTC (21:49 em Brasilia)
    # derrubou 9 testes que nada tinham a ver com a 007: eles ancoravam o
    # "hoje" no relogio da maquina (UTC no runner) enquanto o codigo recorta
    # o dia em America/Sao_Paulo. Entre 21h e meia-noite os dois discordam.
    @{ Arquivo = "api\tests\test_crm_tarefas.py";            Marcador = "regras.FUSO_OPERACAO" },
    @{ Arquivo = "api\tests\test_telemetria.py";             Marcador = "hoje_operacao" }
)

# Guarda da correcao de fuso: se 'date.today()' reaparecer em test_telemetria,
# a suite volta a quebrar todo fim de tarde -- e so as vezes, que e o pior
# jeito de um teste falhar.
$SEM_TODAY = "api\tests\test_telemetria.py"

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
# porque $ErrorActionPreference NAO pega falha de .exe -- so de cmdlet. Sem
# isto um pytest vermelho passaria batido e o script seguiria para o push.
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
        Abortar "arquivo da 007 nao encontrado: $($item.Arquivo). Voce esta na pasta certa da versao?"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) existe mas nao tem '$($item.Marcador)' -- essa e a versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 007 estao no disco, com o conteudo novo"

$telemetria = Get-Content $SEM_TODAY -Raw
if ($telemetria -match [regex]::Escape("date.today()")) {
    Abortar "$SEM_TODAY voltou a usar date.today(). Use hoje_operacao() -- o dia tem que ser o do fuso da operacao, nao o do relogio do runner."
}
Bom "telemetria sem date.today() -- o dia vem do fuso da operacao"

# Guarda de escopo: se alguem juntou uma migration nesta leva, a ordem
# correta muda (DDL em producao ANTES do push) e este script nao faz DDL.
$migracoesNovas = @(& git status --porcelain -- "api/migrations")
if ($migracoesNovas.Count -gt 0) {
    Write-Host ""
    $migracoesNovas | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Abortar "ha migration pendente no git status. A 007 e so codigo. Aplique o DDL em producao ANTES do push, com um script proprio -- este aqui nao faz banco."
}
Bom "nenhuma migration pendente -- entrega so de codigo"

$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"

$sujos = & git status --porcelain
if (-not $sujos) {
    Aviso "arvore limpa -- ou voce ja commitou, ou os arquivos nao foram salvos na pasta do repositorio."
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "voce escolheu pular. A suite completa ainda roda no CI, com Postgres."
}
else {
    Titulo "1. Testes locais"

    # Pytest local no Windows sem Postgres falha nos testes de banco. Os de
    # logica pura (sem a fixture db_conn) rodam aqui; o resto valida no CI.
    #
    # A DATABASE_URL e forcada para localhost ANTES do pytest: com a de
    # producao no ambiente, o safeguard do conftest aborta a sessao inteira
    # -- que e ele funcionando, mas nao e o que queremos aqui.
    Push-Location "api"
    try {
        $env:PYTHONPATH   = (Get-Location).Path
        $env:DATABASE_URL = "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test"

        Executar "pytest -- regras puras" {
            python -m pytest -q --no-cov `
                tests\test_tarefa_regras.py `
                tests\test_parceiro_regras.py `
                tests\test_oportunidade_regras.py `
                tests\test_cnpj.py `
                tests\test_texto.py `
                tests\test_dias_uteis.py
        }
        Bom "regras puras verdes"

        # A montagem do WHERE da busca e funcao pura: da para validar aqui
        # que o CNPJ vira digitos, que termo curto nao vira varredura de
        # documento e que os seis caminhos entram numa clausula so (em OR --
        # quebrada em varias viraria AND e a busca nao acharia nada).
        Executar "pytest -- montagem da busca textual" {
            python -m pytest -q --no-cov `
                tests\test_crm_oportunidades.py -k "TestMontagemDaBuscaTextual"
        }
        Bom "busca textual: montagem do filtro verde"
    }
    finally { Pop-Location }

    Push-Location "web"
    try {
        Executar "vitest"     { npx vitest run }
        Bom "frontend verde"
        Executar "vite build" { npx vite build }
        Bom "build verde"
    }
    finally { Pop-Location }
}

# =====================================================================
# 2. Push
# =====================================================================

Titulo "2. Push"

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
    Aviso "arvore limpa -- nada novo para commitar, seguindo para o push."
}

Executar "git push" { git push origin $ramo }
Bom "codigo no repositorio"

# =====================================================================
# 3. CI
# =====================================================================

Titulo "3. CI"

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
if (-not $temGh) {
    Aviso "gh nao instalado -- acompanhe em https://github.com/tuliohorta77/Hipo-Web/actions"
}
else {
    # Devolve o run mais recente, ou $null. O @() em volta e necessario: no
    # PowerShell 5.1 um ConvertFrom-Json de array com UM elemento devolve o
    # objeto solto, e ai [0] indexa o objeto em vez da lista.
    function RunMaisRecente {
        $bruto = & gh run list --workflow=ci-cd.yml --limit 1 --json databaseId,createdAt
        if ($LASTEXITCODE -ne 0) { return $null }
        $lista = @($bruto | ConvertFrom-Json)
        if ($lista.Count -eq 0) { return $null }
        return $lista[0]
    }

    $antes = RunMaisRecente
    $idAntes = ""
    if ($antes) { $idAntes = [string]$antes.databaseId }

    # O gatilho 'push' do Actions as vezes adormece. A saida e o
    # workflow_dispatch -- MAS nunca junto com o push: dois runs simultaneos
    # colidem no deploy e o concurrency cancela um deles no meio.
    Passo "esperando 45s para ver se o push acordou o workflow..."
    Start-Sleep -Seconds 45

    $atual = RunMaisRecente
    $nasceu = $false
    if ($atual) {
        $ehNovo = ([string]$atual.databaseId) -ne $idAntes
        $idade  = (Get-Date) - [datetime]$atual.createdAt
        if ($ehNovo -or $idade.TotalMinutes -lt 3) { $nasceu = $true }
    }

    if (-not $nasceu) {
        Aviso "o gatilho push parece ter adormecido -- disparando manualmente"
        Executar "gh workflow run" { gh workflow run ci-cd.yml --ref $ramo }
        Start-Sleep -Seconds 15
        $atual = RunMaisRecente
    }
    else {
        Bom "run criado pelo push"
    }

    if (-not $atual) {
        Aviso "nao consegui identificar o run -- acompanhe em https://github.com/tuliohorta77/Hipo-Web/actions"
    }
    else {
        # Watch do run ESPECIFICO, nunca 'gh run watch' pelado: sem o id ele
        # abre menu para escolher quando ha mais de um run em andamento, e
        # num script isso trava esperando tecla que ninguem vai apertar.
        $runId = [string]$atual.databaseId
        Passo "acompanhando o run $runId (os 3 jobs precisam ficar verdes)..."
        & gh run watch $runId --exit-status
        if ($LASTEXITCODE -ne 0) {
            Abortar "o CI ficou vermelho no run $runId. Nada foi aplicado no banco -- a producao segue com o codigo anterior. Corrija e empurre de novo."
        }
        Bom "Backend Tests + Frontend Tests + Deploy verdes"
    }
}

# =====================================================================
# 4. Smoke test
# =====================================================================

Titulo "4. Smoke test"

# O passo "Verificar deploy" do CI roda
#     curl -sf http://localhost/health || echo 'Frontend OK'
# e depois do Certbot o localhost cai no bloco default do nginx e devolve
# 404 -- que o '||' engole. Aquele passo passa SEMPRE, inclusive com o
# front quebrado. Este aqui bate na URL publica e falha alto.

# O PowerShell 5.1 ainda negocia TLS 1.0 por padrao, e o nginx com
# certificado Let's Encrypt so aceita 1.2 para cima. Sem esta linha o smoke
# test morre com "Could not create SSL/TLS secure channel" -- erro que
# parece problema do servidor e nao e. Vale so para este processo.
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

# ---------------------------------------------------------------------
# Smoke autenticado: exercita a consulta NOVA contra o banco de producao.
#
# Este e o unico passo que prova que a busca ampliada funciona LA. Os
# testes do CI rodam contra o Postgres do runner, criado a partir do
# schema.sql; se producao divergir em alguma coluna, o erro so aparece
# aqui. Resultado vazio e sucesso -- o que se mede e a consulta responder
# 200, nao ela achar algo.
# ---------------------------------------------------------------------
if ($PularSmoke) {
    Aviso "smoke autenticado pulado por -PularSmoke"
}
elseif (-not $SmokeEmail) {
    Aviso "smoke autenticado nao rodou. Para exercitar a busca nova em producao, rode de novo com -SmokeEmail voce@empresa.com"
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

        # 1. Tarefas filtradas pelo proprio responsavel: e a chamada exata
        #    que a tela passa a fazer sozinha ao abrir.
        $kanban = Invoke-RestMethod -Headers $cabecalho -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/tarefas/kanban?responsavel_id=$($eu.id)"
        $minhas = 0
        foreach ($col in $kanban) { $minhas = $minhas + $col.quantidade }
        Bom "kanban por responsavel respondeu -- $minhas tarefa(s) suas"

        # 2. Os caminhos novos da busca, um a um. Cada um so precisa
        #    devolver 200: o que quebraria seria SQL invalido.
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
    Abortar "o deploy subiu mas o smoke test nao passou. Olhe o servico: ssh e 'sudo systemctl status hipo'."
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Entregue"

Write-Host ""
Write-Host "  A 007 esta no ar." -ForegroundColor Green
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
Write-Host "    - depois de trocar, o X volta e devolve o filtro para voce" -ForegroundColor Gray
Write-Host "    - o KPI 'Realizadas no mes' acompanha o mesmo recorte" -ForegroundColor Gray
Write-Host ""
Write-Host "  Confira em Oportunidades, na mesma caixa de busca:" -ForegroundColor Gray
Write-Host "    - o numero da oportunidade" -ForegroundColor Gray
Write-Host "    - a razao social e tambem o nome fantasia" -ForegroundColor Gray
Write-Host "    - o CNPJ, colado com pontuacao e so a raiz sem filial" -ForegroundColor Gray
Write-Host "    - o nome de um contato da empresa" -ForegroundColor Gray
Write-Host "    - os KPIs do topo acompanham o resultado da busca" -ForegroundColor Gray
Write-Host ""
