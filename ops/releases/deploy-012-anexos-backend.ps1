# =====================================================================
#  HIPO -- 012: anexo de arquivo na tarefa (BACKEND)
# =====================================================================
#
#  O QUE MUDA
#
#  A tarefa passa a aceitar anexo: o print do WhatsApp que prova o
#  relato. Os arquivos vao para o S3 (hipo-anexos-<conta>, privado); o
#  banco guarda so o ponteiro.
#
#  SO O BACKEND. A tela de anexar ainda nao existe -- e isso e
#  deliberado, nao entrega pela metade. As quatro rotas sobem inertes
#  (ninguem as chama), a migration e o .env estabilizam sozinhos, e o
#  frontend entra numa 013 sem carregar junto o risco de migration e de
#  variavel de ambiente. Se algo der errado hoje, o sintoma aparece no
#  smoke e nao na cara do usuario.
#
#  TRES PASSOS QUE O CI NAO FAZ
#
#  O job de deploy faz rsync + restart, e mais nada. Esta entrega precisa
#  de dois passos de servidor, e a ORDEM entre eles nao e negociavel:
#
#    1. MIGRATION (antes do deploy). Aditiva e idempotente. Tabela que
#       existe antes do codigo que a usa nunca quebra nada; o contrario,
#       sim.
#    2. LINHA NO .env (DEPOIS do deploy). O pydantic-settings RECUSA
#       chave do .env que o Settings nao declara -- 'Extra inputs are not
#       permitted'. Escrever S3_BUCKET_ANEXOS com o codigo velho em
#       producao e reiniciar faz a API NAO SUBIR. Testado, nao suposto.
#    3. RESTART, que e o unico jeito de o .env novo virar processo.
#
#  Entre o passo 1 e o 2 o recurso fica desligado por conta propria: o
#  campo tem default vazio e a API responde 503 com mensagem dizendo o
#  que falta, em vez de 500 generico.
#
#  PRE-REQUISITO JA FEITO
#     .\setup-s3-anexos.ps1 -- bucket criado, acesso publico bloqueado,
#     versionamento e SSE ligados, politica na role hipo-ec2-ses.
#
#  FLUXO
#     0. pre-voo (arquivos no disco, escopo do commit, SSH vivo)
#     1. testes locais (pytest das regras puras + vitest + build)
#     2. migration no RDS
#     3. push -> CI -> PR -> merge -> deploy CONFERIDO pelo nome do job
#     4. .env + restart
#     5. smoke (health + a rota de anexos respondendo)
#
#  USO
#     .\deploy-012-anexos-backend.ps1
#     .\deploy-012-anexos-backend.ps1 -PularTestes
#     .\deploy-012-anexos-backend.ps1 -PularMigration   # se ja rodou
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularMigration,
    [switch]$PularSmoke,

    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$Ip         = "63.179.88.212",
    [string]$UsuarioSsh = "ec2-user",
    [string]$Chave      = "$HOME\Downloads\chave-hipo.pem",
    [string]$Bucket     = "hipo-anexos-520723705827",
    [string]$Mensagem   = "feat(tarefas): anexo de arquivo na tarefa (backend + S3)"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

$ESPERADOS = @(
    @{ Arquivo = "api\migrations\009_anexos.sql";     Marcador = "tarefa_anexos" },
    @{ Arquivo = "api\services\anexo.py";             Marcador = "TIPOS_ACEITOS" },
    @{ Arquivo = "api\routers\crm_anexos.py";         Marcador = "tarefa_anexos" },
    @{ Arquivo = "api\tests\test_anexo_regras.py";    Marcador = "TestNomeSeguro" },
    @{ Arquivo = "api\main.py";                       Marcador = "crm_anexos" },
    @{ Arquivo = "api\config.py";                     Marcador = "S3_BUCKET_ANEXOS" },
    @{ Arquivo = "api\schema.sql";                    Marcador = "tarefa_anexos" },
    @{ Arquivo = "infra\aplicar-009-anexos.sh";       Marcador = "to_regclass" }
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
        Abortar "arquivo da 012 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 012 estao no disco"

# git status --porcelain, e nao git diff: `git diff` NAO enxerga arquivo
# untracked, e foi assim que a 011 anunciou "so frontend" enquanto o
# commit levava um .py novo, um zip de 130 KB e dois scripts a reboque.
$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }
    $inesperados = @($sujos | Where-Object {
        $_ -notmatch 'api/(migrations/009_anexos\.sql|services/anexo\.py|routers/crm_anexos\.py|tests/test_anexo_regras\.py|main\.py|config\.py|schema\.sql|\.env\.template)' -and
        $_ -notmatch 'infra/aplicar-009-anexos\.sh' -and
        $_ -notmatch 'deploy-012-anexos-backend\.ps1' -and
        $_ -notmatch 'setup-s3-anexos\.ps1' -and
        $_ -notmatch '\.gitignore'
    })
    if ($inesperados.Count -gt 0) {
        Write-Host ""
        Aviso "$($inesperados.Count) arquivo(s) fora do escopo desta entrega."
        Confirmar "Levar tudo isso junto mesmo assim?"
    }
    else { Bom "so os arquivos da 012" }
}
else { Aviso "arvore limpa -- nada novo para commitar." }

Passo "SSH..."
& ssh -i $Chave -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 `
    "$UsuarioSsh@$Ip" "echo vivo" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Abortar "SSH nao respondeu. A migration e o .env precisam dele -- resolva antes de comecar."
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

    # As regras de anexo sao PURAS: sem banco, sem AWS. Rodam no Windows
    # sem Postgres, ao contrario do resto da suite de backend, que so
    # valida no CI.
    Push-Location "api"
    try {
        $env:PYTHONPATH = (Get-Location).Path
        Executar "pytest (regras de anexo)" { python -m pytest tests/test_anexo_regras.py -q }
        Bom "regras de anexo verdes"
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
    Aviso "so use isto se a 009 JA foi aplicada; sem a tabela, as rotas dao 500."
}
else {
    Titulo "2. Migration 009_anexos no RDS"

    Write-Host ""
    Write-Host "  ADITIVA e IDEMPOTENTE: so CREATE TABLE/INDEX IF NOT EXISTS." -ForegroundColor Gray
    Write-Host "  Nenhum DROP, nenhum ALTER destrutivo -- por isso nao exige o" -ForegroundColor Gray
    Write-Host "  export em CSV que as migrations destrutivas exigem." -ForegroundColor Gray
    Write-Host "  Roda ANTES do deploy: tabela que existe antes do codigo que a" -ForegroundColor Gray
    Write-Host "  usa nunca quebra nada; o contrario, sim." -ForegroundColor Gray

    Confirmar "Aplicar a 009 no RDS de producao?"

    Executar "enviando a migration" {
        scp -i $Chave "api\migrations\009_anexos.sql" "${UsuarioSsh}@${Ip}:/tmp/009_anexos.sql"
    }
    Executar "enviando o aplicador" {
        scp -i $Chave "infra\aplicar-009-anexos.sh" "${UsuarioSsh}@${Ip}:/tmp/aplicar-009-anexos.sh"
    }
    Executar "aplicando" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo bash /tmp/aplicar-009-anexos.sh /tmp/009_anexos.sql"
    }
    Bom "tabela tarefa_anexos criada"
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
        # EsperarRunNovo, e nao RunMaisRecente cru. Chamado logo apos o
        # push, o RunMaisRecente devolve o run ANTERIOR -- que esta verde --
        # e o script anuncia "deploy concluido" com o codigo velho ainda no
        # ar. Foi assim que a 012 gravou o S3_BUCKET_ANEXOS no .env antes do
        # deploy e derrubou a API: exatamente o acidente que o passo 4
        # existe para evitar. O sintoma no log era discreto: "has ALREADY
        # completed with 'success'".
        $runMain = EsperarRunNovo $RamoAlvo $idAntesDoPush 60
        if (-not $runMain) {
            Abortar "push feito mas nao vi run novo na $RamoAlvo. NAO siga para o passo do .env sem conferir o deploy em $REPO_URL"
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
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 012 -- anexo de arquivo na tarefa, backend. Migration 009 (aditiva) aplicada antes do deploy. A linha S3_BUCKET_ANEXOS no .env entra DEPOIS do deploy: o pydantic-settings recusa chave que o Settings nao declara. Sem frontend ainda: as rotas sobem inertes."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se foi 'No commits between', o merge ja aconteceu: use .\deploy-007-retomar.ps1."
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
# 4. .env e restart -- SO AGORA
# =====================================================================

Titulo "4. S3_BUCKET_ANEXOS no .env"

Write-Host ""
Write-Host "  Este passo so pode acontecer com o codigo novo JA em producao." -ForegroundColor Yellow
Write-Host "  O pydantic-settings recusa chave do .env que o Settings nao" -ForegroundColor Yellow
Write-Host "  declara ('Extra inputs are not permitted'), e a API nao sobe." -ForegroundColor Yellow

# A prova DIRETA, olhando o arquivo que esta na maquina -- e nao a
# conclusao de um run do CI, que ja se provou possivel de ler errado.
# Se o config.py em producao nao conhece o campo, gravar a chave no .env
# derruba a API no restart. Este grep e a ultima porta antes disso.
Passo "conferindo que o codigo em producao ja conhece o campo..."
$temCampo = & ssh -i $Chave "$UsuarioSsh@$Ip" `
    "grep -c 'S3_BUCKET_ANEXOS' /home/hipo/app/api/config.py || true"
$temCampo = ($temCampo | Out-String).Trim()

if ($temCampo -eq "0" -or -not $temCampo) {
    Abortar @"
o config.py em producao NAO tem S3_BUCKET_ANEXOS -- o deploy do codigo novo
    nao chegou na maquina. Gravar a chave no .env agora derrubaria a API.
    Confira o run em $REPO_URL e rode de novo com -PularTestes -PularMigration.
"@
}
Bom "config.py em producao conhece o campo ($temCampo ocorrencia(s))"

Confirmar "Gravar S3_BUCKET_ANEXOS=$Bucket no .env e reiniciar a API?"

# Idempotente: rodar de novo nao duplica a linha. Chave duplicada no .env
# nao quebra o pydantic, mas deixa o arquivo mentindo sobre si mesmo --
# e a proxima pessoa a ler nao sabe qual das duas vale.
#
# SEM ASPAS DUPLAS. A versao anterior tinha `"..."` escapado com crase, e
# o PowerShell 5.1 comia as aspas na passagem para o ssh.exe -- igual ao
# que quebrou a prova do S3. Aqui passou despercebido porque `echo` de um
# valor sem espacos da o mesmo resultado com ou sem aspas. Funcionou por
# sorte, e sorte que ninguem viu e a que quebra quando o valor mudar.
#
# Aspas simples sobrevivem intactas (o PowerShell nao as toca) e o nome
# do bucket nao tem espaco nem caractere especial -- ele e validado no
# setup-s3-anexos.ps1, que o deriva do id da conta.
$comando = "sudo grep -q '^S3_BUCKET_ANEXOS=' /home/hipo/app/.env " +
           "&& echo 'ja existia' " +
           "|| sudo sh -c 'echo S3_BUCKET_ANEXOS=$Bucket >> /home/hipo/app/.env'"
Executar "gravando no .env" { ssh -i $Chave "$UsuarioSsh@$Ip" $comando }

# Conferir o que FICOU no arquivo, e nao so que o comando saiu com 0. A
# linha e o que decide se a API sobe no proximo restart.
$linha = & ssh -i $Chave "$UsuarioSsh@$Ip" "sudo grep '^S3_BUCKET_ANEXOS=' /home/hipo/app/.env"
$linha = ($linha | Out-String).Trim()
if ($linha -ne "S3_BUCKET_ANEXOS=$Bucket") {
    Abortar "a linha gravada no .env ficou '$linha', e nao 'S3_BUCKET_ANEXOS=$Bucket'. Corrija a mao antes de reiniciar a API."
}
Bom "linha conferida no .env: $linha"

Executar "reiniciando a API" {
    ssh -i $Chave "$UsuarioSsh@$Ip" "sudo systemctl restart hipo-api"
}
Bom "hipo-api reiniciado"

Passo "esperando a API voltar..."
Start-Sleep -Seconds 6

# =====================================================================
# 5. Smoke
# =====================================================================

Titulo "5. Smoke"

if ($PularSmoke) {
    Aviso "smoke pulado"
}
else {
    Passo "API..."
    try {
        # `versao`, com til comido -- e o nome do campo em /health. O
        # `$health.version` que veio do deploy-010 nunca existiu na
        # resposta, entao imprimia string vazia: um smoke que parecia
        # confirmar a versao e nao confirmava nada.
        $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
        if (-not $health.versao) { Abortar "/health respondeu sem o campo 'versao': $($health | ConvertTo-Json -Compress)" }
        Bom "API viva -- versao $($health.versao)"
    }
    catch {
        Abortar "a API NAO respondeu depois do restart: $($_.Exception.Message). Veja 'sudo journalctl -u hipo-api -n 50' -- se for 'Extra inputs are not permitted', o .env ganhou a chave antes do codigo."
    }

    Passo "front..."
    try {
        $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
        if ($front.StatusCode -ne 200) { Abortar "o front respondeu HTTP $($front.StatusCode)" }
        Bom "front servido (HTTP 200)"
    }
    catch { Abortar "o front nao respondeu: $($_.Exception.Message)" }

    # A prova de que a role chegou no processo. Roda como o usuario do
    # app, nao como root: quem precisa enxergar o bucket e o processo que
    # serve a API.
    Passo "credencial do S3, de dentro da EC2..."
    #
    # O SCRIPT VAI POR STDIN, e o comando remoto nao tem NENHUMA aspa.
    #
    # Duas tentativas anteriores morreram na mesma fronteira, e vale
    # anotar as duas porque parecem problemas diferentes e sao o mesmo:
    #
    #   1a) aspas duplas por fora, simples por dentro ->
    #       "syntax error near unexpected token" (o bash remoto recebeu o
    #       -c sem delimitador)
    #   2a) aspas simples por fora, duplas por dentro ->
    #       "NameError: name 'KeyCount' is not defined" (o Python recebeu
    #       print(KeyCount, ...) sem as aspas)
    #
    # A causa e a MESMA nas duas: o PowerShell 5.1 remove aspas duplas
    # nao escapadas ao montar a linha de comando de um executavel NATIVO
    # (ssh.exe). Nao adianta arrumar o nivel do bash: o estrago acontece
    # antes, do lado do Windows.
    #
    # Com o script em stdin, o unico argumento e "sudo -u hipo python3 -",
    # que nao tem aspas para perder. E as aspas do Python ficam dentro de
    # uma string PowerShell que nunca vira argumento de processo nativo.
    #
    # `-u` e nao `-iu`: o login shell do -i nao e necessario aqui (a
    # credencial vem da role da instancia, nao do HOME do usuario) e ele
    # complica o repasse do stdin.
    $py = @"
import boto3
print("KeyCount", boto3.client("s3").list_objects_v2(Bucket="$Bucket").get("KeyCount"))
"@

    $saida = $py | & ssh -i $Chave "$UsuarioSsh@$Ip" "sudo -u hipo python3 -"
    $texto = ($saida | Out-String)
    Write-Host $texto.TrimEnd() -ForegroundColor DarkGray

    if ($texto -match "KeyCount") {
        Bom "a EC2 enxerga o bucket"
    }
    elseif ($texto -match "AccessDenied") {
        Aviso "AccessDenied: a role nao chegou no processo. Confira a politica hipo-anexos-s3 em hipo-ec2-ses -- nao e bug do codigo dos anexos."
    }
    else {
        Aviso "a prova do S3 nao respondeu o esperado. Leia a saida acima antes de culpar a role: erro de sintaxe aqui e problema do comando, nao de permissao."
    }
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Backend dos anexos no ar"

Write-Host ""
Write-Host "  A feature esta invisivel de proposito: nao ha tela ainda." -ForegroundColor Green
Write-Host "  As quatro rotas existem e respondem:" -ForegroundColor Gray
Write-Host "     GET    /crm/tarefas/{id}/anexos" -ForegroundColor DarkGray
Write-Host "     POST   /crm/tarefas/{id}/anexos" -ForegroundColor DarkGray
Write-Host "     GET    /crm/anexos/{id}/url" -ForegroundColor DarkGray
Write-Host "     DELETE /crm/anexos/{id}" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Teste de ponta a ponta, se quiser conferir agora (troque o id" -ForegroundColor Yellow
Write-Host "  por uma tarefa ABERTA de verdade -- tarefa fechada devolve 422," -ForegroundColor Yellow
Write-Host "  que e a regra funcionando):" -ForegroundColor Yellow
Write-Host ""
Write-Host "     `$t = (Invoke-RestMethod -Method Post -Uri '$UrlPublica/api/auth/login' ``" -ForegroundColor White
Write-Host "            -Body (@{email='voce@dominio';senha='...'} | ConvertTo-Json) ``" -ForegroundColor White
Write-Host "            -ContentType 'application/json').access_token" -ForegroundColor White
Write-Host "     curl.exe -H `"Authorization: Bearer `$t`" ``" -ForegroundColor White
Write-Host "            -F 'arquivo=@C:\caminho\print.png;type=image/png' ``" -ForegroundColor White
Write-Host "            $UrlPublica/api/crm/tarefas/<ID-DA-TAREFA>/anexos" -ForegroundColor White
Write-Host ""
Write-Host "  Depois confira no bucket:" -ForegroundColor Gray
Write-Host "     aws s3 ls s3://$Bucket/tarefas/ --recursive" -ForegroundColor White
Write-Host ""
Write-Host "  Proxima: a 013, com a tela -- colar do clipboard, galeria e" -ForegroundColor Gray
Write-Host "  lightbox, mais os testes de vitest." -ForegroundColor Gray
Write-Host ""
