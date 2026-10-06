# =====================================================================
#  HIPO -- 016: a proxima tarefa vira regra do ALVO, nao da tarefa
# =====================================================================
#
#  O SINTOMA
#
#  Reportado logo depois da 015. A oportunidade tinha uma tarefa aberta,
#  alguem marcava uma apresentacao -- que E outra tarefa --, e ao fechar a
#  reuniao o sistema exigia criar mais uma. Duas tarefas abertas, sempre, e
#  o numero crescendo a cada volta.
#
#  A CAUSA
#
#  "Concluir exige a proxima" olhava so para a TAREFA que estava sendo
#  fechada: oportunidade viva -> exige, ponto. Fazia sentido quando havia
#  uma corrente unica de follow-up. Com a agenda, a reuniao passou a ser
#  uma segunda tarefa da mesma oportunidade, e a regra virou uma esteira.
#
#  A REGRA NOVA
#
#     Uma oportunidade nunca pode ficar sem um proximo passo aberto.
#
#  Dela sai a obrigacao: a proxima e cobrada de quem fecha a ULTIMA tarefa
#  aberta do alvo. Sobrando outra, concluir e livre -- o proximo passo
#  continua la. Vale igual para tarefa de parceiro.
#
#  O que NAO mudou: oportunidade finalizada nunca exige; cancelar nunca
#  exigiu; a corrente `tarefa_anterior_id` continua igual.
#
#  COMO ELA E APLICADA
#
#  `services/tarefa.exige_proxima` ganhou `outras_abertas`, keyword-only e
#  SEM DEFAULT -- com default, uma chamada nova que esquecesse de passa-lo
#  voltaria em silencio ao comportamento antigo. A contagem e feita dentro
#  da transacao que grava, depois de travar a linha do alvo
#  (`_travar_alvo`): contada fora, duas conclusoes simultaneas das duas
#  ultimas tarefas leriam "sobra uma" cada uma, as duas passariam, e a
#  oportunidade acabaria sem proximo passo.
#
#  A tela recebe o mesmo numero pronto (`outras_abertas` em TarefaOut e em
#  ReuniaoOut) e explica por escrito quando dispensa -- "esta oportunidade
#  ja tem outra tarefa em aberto". Sem a frase, o formulario pediria a
#  proxima as vezes sim e as vezes nao, sem dizer por que.
#
#  NENHUM PASSO FORA DO CI
#
#  Nao ha migration: `outras_abertas` e DERIVADO, calculado por
#  subconsulta no mesmo SELECT que ja existia. Nenhuma coluna nova, nenhum
#  indice novo (a subconsulta usa `idx_tarefas_abertas_por_opp`, que a 004
#  ja criou). Nada de .env, nada de pip. E so codigo: push, CI, deploy.
#
#  O CONSERTO DO WORKFLOW ANDA JUNTO (run #179)
#
#  O primeiro deploy da 016 ficou vermelho, e nao por causa do codigo. O
#  passo "Deploy do Backend" terminava com `sleep 5` e um `curl -sf` no
#  /health: se a API levasse 6 segundos para subir, o passo morria com
#  exit 1 e ZERO linha de log -- o curl e silencioso nos dois caminhos. O
#  unico texto na tela era um aviso do rsync ("cannot delete non-empty
#  directory: parsers") que nao tinha relacao nenhuma com a falha, e que
#  mandava quem investigasse para o lado errado.
#
#  Consequencia: o restart RODOU (o backend foi para a 016), mas o passo
#  "Deploy do Frontend", que vem depois, nunca chegou a rodar. Producao
#  ficou com backend novo e tela velha -- e a tela velha e justamente a
#  que ainda cobra a proxima tarefa.
#
#  .github/workflows/ci-cd.yml traz as duas correcoes: o health check
#  espera ate 60s e despeja o journal quando estoura, e o __pycache__ vira
#  filtro 'perishable' para o rsync poder apagar a pasta do legado. E o
#  smoke daqui parou de aprovar o front so por ele responder 200 -- agora
#  procura, dentro do bundle servido, uma frase que so existe na 016.
#
#  FLUXO
#     0. pre-voo (arquivos no disco, escopo do commit)
#     1. testes locais (pytest das regras puras + vitest + build)
#     2. push -> CI -> PR -> merge -> deploy CONFERIDO pelo nome do job
#     3. smoke (health + o campo novo aparecendo no contrato da API)
#
#  USO
#     .\deploy-016-proxima-tarefa.ps1
#     .\deploy-016-proxima-tarefa.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,

    [string]$RamoAlvo    = "main",
    [string]$UrlPublica  = "https://hipogestao.com.br",
    [string]$Mensagem    = "fix(tarefas): proxima tarefa so e exigida de quem fecha a ultima aberta do alvo"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# TODO MARCADOR AQUI E ASCII PURO. Get-Content -Raw de um arquivo UTF-8 no
# PowerShell 5.1 embaralha acento, e a checagem falharia num arquivo que
# esta CERTO. Use nome de simbolo, caminho de rota ou nome de constante --
# nunca texto de interface. (Custou uma execucao na 014.)
$ESPERADOS = @(
    @{ Arquivo = "api\services\tarefa.py";                   Marcador = "outras_abertas" },
    @{ Arquivo = "api\routers\crm_tarefas.py";               Marcador = "contar_outras_abertas" },
    @{ Arquivo = "api\routers\crm_tarefas.py";               Marcador = "_travar_alvo" },
    @{ Arquivo = "api\routers\crm_agenda.py";                Marcador = "contar_outras_abertas" },
    @{ Arquivo = "api\tests\test_tarefa_regras.py";          Marcador = "TestOutrasAbertasDispensamAProxima" },
    @{ Arquivo = "api\tests\test_crm_tarefas.py";            Marcador = "TestOutrasAbertasDispensamAProxima" },
    @{ Arquivo = "api\tests\test_crm_agenda.py";             Marcador = "test_com_outra_tarefa_aberta_nao_exige_a_proxima" },
    @{ Arquivo = "web\src\components\crm\tarefaComum.jsx";   Marcador = "exigeProximaAqui" },
    @{ Arquivo = "web\src\components\crm\AbaTarefas.jsx";    Marcador = "t.outras_abertas" },
    @{ Arquivo = "web\src\pages\crm\Tarefas.jsx";            Marcador = "t.outras_abertas" },
    @{ Arquivo = "web\src\components\crm\ModalReuniao.jsx";  Marcador = "reuniao.outras_abertas" },
    @{ Arquivo = "web\src\tests\Tarefas.test.jsx";           Marcador = "outras_abertas" },
    @{ Arquivo = "web\src\tests\ModalReuniao.test.jsx";      Marcador = "outras_abertas" }
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
        Abortar "arquivo da 016 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) marcadores da 016 conferem no disco"

# A 016 nao tem migration, e e importante que continue assim: se alguem
# acrescentar uma coluna aqui sem espelhar no schema.sql, o CI (que monta o
# banco de teste com `psql -f api/schema.sql`) derruba dezenas de testes.
if (Test-Path "api\migrations\013_*.sql") {
    Aviso "existe uma migration 013 no disco. A 016 nao previa nenhuma."
    Confirmar "Seguir mesmo assim?"
}
else { Bom "sem migration nesta entrega (outras_abertas e derivado)" }

# O indice de que a subconsulta depende. Ele vem da 004 e ja esta em
# producao -- esta checagem existe para o dia em que alguem o remover
# achando que nada usa: sem ele, a contagem vira seq scan em `tarefas` a
# cada linha de cada lista de tarefas.
$schema = Get-Content "api\schema.sql" -Raw
if ($schema -notmatch [regex]::Escape("idx_tarefas_abertas_por_opp")) {
    Abortar "api\schema.sql nao tem 'idx_tarefas_abertas_por_opp'. A contagem de tarefas abertas depende dele."
}
Bom "o indice parcial de tarefas abertas esta no schema"

# Asserts de igualdade exata em modulos_do_cargo quebram a cada modulo novo.
# A 016 nao cria modulo -- este aviso existe para o dia em que alguem mudar
# isso sem lembrar.
$asserts = @(Select-String -Path "api\tests\*.py" -Pattern 'modulos_do_cargo.*==|body\["modulos"\].*==' -ErrorAction SilentlyContinue)
Passo "asserts de modulos_do_cargo encontrados: $($asserts.Count) (a 016 nao cria modulo, entao nenhum deveria mudar)"

$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }
    $inesperados = @($sujos | Where-Object {
        $_ -notmatch 'api/(services/tarefa\.py|routers/(crm_tarefas|crm_agenda)\.py|tests/test_(tarefa_regras|crm_tarefas|crm_agenda)\.py)' -and
        $_ -notmatch 'web/src/(components/crm/(tarefaComum\.jsx|AbaTarefas\.jsx|ModalReuniao\.jsx)|pages/crm/Tarefas\.jsx|tests/(Tarefas|ModalReuniao)\.test\.jsx)' -and
        # O conserto do workflow anda junto: e ele que faz o deploy chegar
        # ao passo do frontend. Ver o cabecalho.
        $_ -notmatch '\.github/workflows/ci-cd\.yml' -and
        $_ -notmatch 'deploy-016-proxima-tarefa\.ps1'
    })
    if ($inesperados.Count -gt 0) {
        Write-Host ""
        Aviso "$($inesperados.Count) arquivo(s) fora do escopo desta entrega."
        Confirmar "Levar tudo isso junto mesmo assim?"
    }
    else { Bom "so os arquivos da 016" }
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

    # A regra mudada e PURA: sem banco, sem rede. Roda no Windows sem
    # Postgres, ao contrario dos testes de API, que so validam no CI.
    Push-Location "api"
    try {
        $env:PYTHONPATH = (Get-Location).Path
        Executar "pytest (regras de tarefa)" { python -m pytest tests/test_tarefa_regras.py -q }
        Bom "regras de tarefa verdes"
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
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 016 -- a proxima tarefa passa a ser regra do ALVO: uma oportunidade nunca fica sem um proximo passo aberto, e a proxima so e exigida de quem fecha a ULTIMA tarefa aberta. Conserta a esteira que a agenda criou (a reuniao e uma tarefa a mais, e fechar cada uma exigia criar outra). Sem migration: outras_abertas e derivado por subconsulta. A contagem e feita dentro da transacao, com o alvo travado."
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
# 3. Smoke
# =====================================================================

Titulo "3. Smoke"

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

    # A 016 nao cria rota nenhuma -- so um CAMPO. Entao a prova de que o
    # codigo novo chegou e o campo aparecer no schema do openapi, e nao uma
    # rota nova na lista de paths.
    Passo "campo novo no contrato da API..."
    try {
        $spec = Invoke-RestMethod -Uri "$UrlPublica/api/openapi.json" -TimeoutSec 20
        $tarefaOut = $spec.components.schemas.TarefaOut
        if (-not $tarefaOut) { Abortar "nao achei o schema TarefaOut no openapi." }
        $campos = $tarefaOut.properties.PSObject.Properties.Name
        if ($campos -notcontains "outras_abertas") {
            Abortar "TarefaOut ainda nao tem 'outras_abertas'. O deploy do codigo novo nao chegou."
        }
        Bom "TarefaOut.outras_abertas esta no ar"

        $reuniaoOut = $spec.components.schemas.ReuniaoOut
        if ($reuniaoOut) {
            $camposR = $reuniaoOut.properties.PSObject.Properties.Name
            if ($camposR -notcontains "outras_abertas") {
                Abortar "ReuniaoOut ainda nao tem 'outras_abertas'. O painel de desfecho voltaria a cobrar a proxima sempre."
            }
            Bom "ReuniaoOut.outras_abertas esta no ar"
        }
    }
    catch {
        Abortar "nao consegui ler o openapi: $($_.Exception.Message)"
    }

    # O FRONT PRECISA PROVAR A VERSAO, e nao so responder 200.
    #
    # Um HTTP 200 aqui e o mesmo 200 de tres meses atras: diz que o nginx
    # esta de pe, nao que o bundle novo chegou. E foi exatamente isso que
    # escondeu o problema no run #179 -- o passo "Deploy do Backend" morreu
    # no health check, o "Deploy do Frontend" (que vem DEPOIS) nunca rodou,
    # e o smoke aprovou o front mesmo assim. Ficou backend novo com tela
    # velha, e a tela velha e justamente a que ainda cobrava a proxima
    # tarefa -- o bug parecia nao ter sido corrigido.
    #
    # A prova e uma FRASE que so existe na 016, procurada dentro do bundle
    # servido. Nao serve comparar o hash do arquivo com o do build local: o
    # bundle de producao e compilado pelo runner, e qualquer diferenca de
    # versao de node mudaria o hash sem mudar o conteudo -- alarme falso
    # numa checagem que precisa ser confiavel.
    #
    # A frase e ASCII pura de proposito. Com acento, dependeria de como o
    # PowerShell decodificou a resposta, e um mismatch de encoding
    # reprovaria um deploy que esta certo.
    Passo "front (bundle servido, nao so HTTP 200)..."
    try {
        $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
        if ($front.StatusCode -ne 200) { Abortar "o front respondeu HTTP $($front.StatusCode)" }

        $achou = [regex]::Match($front.Content, 'assets/(index-[A-Za-z0-9_-]+\.js)')
        if (-not $achou.Success) {
            Abortar "nao achei a tag do bundle no index.html servido. O /var/www/hipo esta com outra coisa."
        }
        $bundle = $achou.Groups[1].Value
        Bom "bundle servido: $bundle"

        $js = Invoke-WebRequest -Uri "$UrlPublica/assets/$bundle" -TimeoutSec 40 -UseBasicParsing
        if ($js.Content -notmatch 'outra tarefa em aberto') {
            Abortar @"
o bundle em producao ($bundle) e ANTERIOR a 016.
    O backend ja esta novo, mas a tela velha nao conhece 'outras_abertas' --
    ela cai no padrao estrito e continua cobrando a proxima tarefa. Nada
    quebra, mas o bug relatado ainda aparece.
    O passo 'Deploy do Frontend' do CI nao rodou. Confira o run em $REPO_URL
"@
        }
        Bom "a tela em producao e a da 016"
    }
    catch { Abortar "o front nao respondeu: $($_.Exception.Message)" }
}

# =====================================================================
# Fim
# =====================================================================

Titulo "A esteira parou"

Write-Host ""
Write-Host "  RELOGUE ANTES DE CONFERIR -- o bundle e novo." -ForegroundColor Yellow
Write-Host ""
Write-Host "  O passeio de conferencia (o caso exato que foi relatado):" -ForegroundColor Gray
Write-Host "     1. numa oportunidade com uma tarefa em aberto, clique" -ForegroundColor White
Write-Host "        'Agendar Reuniao' e marque uma apresentacao" -ForegroundColor White
Write-Host "     2. abra a reuniao na Agenda e registre 'Realizada'" -ForegroundColor White
Write-Host "     3. o painel NAO pede a proxima, e diz por que:" -ForegroundColor White
Write-Host "        'esta oportunidade ja tem outra tarefa em aberto'" -ForegroundColor White
Write-Host "     4. a oportunidade volta a UMA tarefa aberta -- e fica nela" -ForegroundColor White
Write-Host "     5. ao fechar essa ultima, a proxima volta a ser exigida" -ForegroundColor White
Write-Host ""
Write-Host "  O QUE ISSO NAO FAZ, e vale saber:" -ForegroundColor Yellow
Write-Host "     - nao impede duas tarefas abertas. Agendar uma reuniao" -ForegroundColor Gray
Write-Host "       numa oportunidade que ja tem tarefa continua criando a" -ForegroundColor Gray
Write-Host "       segunda; o que mudou e que fechar qualquer uma delas nao" -ForegroundColor Gray
Write-Host "       gera mais uma. O acumulo para de crescer." -ForegroundColor Gray
Write-Host "     - nao mexe no passivo. Oportunidades que ja estao com duas" -ForegroundColor Gray
Write-Host "       ou mais abertas continuam assim, e agora da para fechar" -ForegroundColor Gray
Write-Host "       as sobrando sem criar nada no lugar." -ForegroundColor Gray
Write-Host ""
Write-Host "  Para levantar o passivo (so leitura, nao muda nada):" -ForegroundColor Gray
Write-Host "     SELECT o.numero, count(*) AS abertas" -ForegroundColor DarkGray
Write-Host "       FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id" -ForegroundColor DarkGray
Write-Host "      WHERE t.concluida_em IS NULL AND t.cancelada_em IS NULL" -ForegroundColor DarkGray
Write-Host "      GROUP BY o.numero HAVING count(*) > 1 ORDER BY 2 DESC;" -ForegroundColor DarkGray
Write-Host ""
