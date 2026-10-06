# =====================================================================
#  HIPO -- deploy 031: pool asyncpg por worker + CORS por ambiente
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo   -- 030 commitado, HEAD exatamente como esperado,
#                    arquivos de _entrega-031\ postos no lugar
#    2. push      -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    3. espera    -- ate https://hipogestao.com.br/api/health responder
#                    "pool": true, e confere o CORS de fora
#
#  ORDEM OBRIGATORIA: deploy-030-scorecard.ps1 PRIMEIRO, este depois.
#    Esta entrega foi feita em cima do main.py do 030 (que ja traz a UC).
#    O pre-voo confere, pelo hash do blob no git, que main.py, config.py,
#    database.py e .env.template no HEAD sao EXATAMENTE as versoes sobre as
#    quais o patch foi montado. Se qualquer um mudou, aborta em vez de
#    apagar a mudanca de outra entrega.
#
#    Por isso os arquivos chegam em _entrega-031\ e nao no lugar: se
#    estivessem no lugar, o `git add` do 030 levaria o pool para o commit
#    do scorecard.
#
#  O QUE ESTE SCRIPT NAO FAZ
#    * mexer no .env: os campos novos tem padrao no codigo. Em producao,
#      CORS vazio vira https://hipogestao.com.br (+ www). Nenhuma linha
#      nova e necessaria -- e, com extra="forbid", NAO adiante colocar
#      linha nova no .env antes deste deploy estar no ar.
#    * migration, pip install, SSH: nada disso e preciso.
#    * rodar o pytest local: no Windows nao ha Postgres; o CI roda os
#      ~2300 testes (UC + 030 + 031 passaram juntos no ensaio).
#
#  USO
#     .\deploy-031-pool-cors.ps1 -Simular
#     .\deploy-031-pool-cors.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,

    [string]$Pasta     = (Get-Location).Path,
    [string]$Url       = "https://hipogestao.com.br",
    [int]$EsperaMax    = 900
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}
function Passo($texto) { Write-Host "  -> $texto" -ForegroundColor Gray }
function Bom($texto)   { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !!  $texto" -ForegroundColor Yellow }
function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}
function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

$pastaEntrega = "_entrega-031"

# Blob esperado NO HEAD (depois do commit do 030) para cada arquivo que
# esta entrega substitui. E o que garante que o patch nao apaga nada.
$baseEsperada = @{
    "api/main.py"       = "8bd2ba313d01a81113c424dbdeeb72d79c58bf83"  # main.py do 030
    "api/config.py"     = "aed312cbd209802ba4309226161b062807846dbb"
    "api/database.py"   = "957f3587e7c80ea7a3a3c018f475cb866f5b6b87"
    "api/.env.template" = "72db738cefc3a43a86b6f6ba64b3ecc71f8d7a33"
}

# Blob das versoes desta entrega -- para saber se ja foram postas no
# lugar numa rodada anterior do script.
$versao031 = @{
    "api/main.py"                    = "c3873111cd4cb1d6564be34b5a1e3689ce1f1a59"
    "api/config.py"                  = "3fd3c22a75ef6367be9e5bbbfce9c9e87230f693"
    "api/database.py"                = "1994e7ce75cb6925ac98fad868a5df4024550e29"
    "api/.env.template"              = "a4b6dcd96d99fd73759f53148dd0d59ec659f9a7"
    "api/tests/test_pool_conexao.py" = "40c1dfe0de0cf9298bfed563164462c1a95ea5b8"
}

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = @(
    "api\main.py",
    "api\config.py",
    "api\database.py",
    "api\.env.template",
    "api\tests\test_pool_conexao.py",
    "deploy-031-pool-cors.ps1"
)

# Mesma lista com barra normal, para o git (aceita nos dois sistemas).
$gitEntrega = $entrega | ForEach-Object { $_.Replace("\", "/") }

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta
Bom "pasta: $Pasta"

Passo "o 030 (scorecard) ja foi commitado?"
$commit030 = (& git log -1 --format=%h -- "api/migrations/021_reuniao_avaliacao.sql") 2>$null
if (-not $commit030) {
    Abortar "o 030 ainda nao foi commitado. Rode .\deploy-030-scorecard.ps1 primeiro."
}
Bom "030 no historico ($commit030)"

$sobra030 = Get-ChildItem -Path (Join-Path $Pasta "_entrega-030") -Recurse -File -ErrorAction SilentlyContinue
if ($sobra030) {
    # Sobra do 030 nao bloqueia: quem garante que nada se perde e a
    # conferencia de hash contra o HEAD, logo abaixo.
    Aviso "_entrega-030\ ainda tem $(@($sobra030).Count) arquivo(s) -- sobra do 030, pode apagar depois"
}

Passo "HEAD com as versoes sobre as quais o patch foi montado..."
foreach ($f in $baseEsperada.Keys) {
    $noHead = (& git rev-parse "HEAD:$f") 2>$null
    if ($noHead -ne $baseEsperada[$f]) {
        Abortar "$f no HEAD nao e a versao esperada (achei $noHead). Algum commit mexeu nele depois do 030. Me mande o arquivo atual para eu refazer o patch."
    }
}
Bom "main.py, config.py, database.py e .env.template batem com o HEAD"

Passo "pondo os arquivos de $pastaEntrega\ no lugar..."
foreach ($f in $versao031.Keys) {
    $local   = $f.Replace("/", "\")
    $destino = Join-Path $Pasta $local
    $origem  = Join-Path (Join-Path $Pasta $pastaEntrega) $local

    $atual = ""
    if (Test-Path $destino) { $atual = (& git hash-object -- $destino) 2>$null }
    if ($atual -eq $versao031[$f]) {
        Aviso "$local ja estava no lugar (rodada anterior)"
        continue
    }
    if (-not (Test-Path $origem)) {
        Abortar "falta $origem."
    }
    if ($baseEsperada.ContainsKey($f) -and $atual -ne $baseEsperada[$f]) {
        Abortar "$local tem mudanca local que nao esta no HEAD. Me mande o arquivo atual."
    }
    if ($Simular) {
        Aviso "simulacao: $local seria substituido por $pastaEntrega\$local"
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $destino) | Out-Null
        Copy-Item -Path $origem -Destination $destino -Force
        $novo = (& git hash-object -- $destino) 2>$null
        if ($novo -ne $versao031[$f]) {
            Abortar "$local copiado, mas o conteudo nao confere (hash $novo). Encoding/fim de linha mudou na copia?"
        }
        Remove-Item -Force $origem
        Bom "$local posto no lugar"
    }
}

if (-not $Simular) {
    $faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
    if ($faltando.Count -gt 0) {
        foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
        Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
    }
    Bom "$($entrega.Count) arquivos da entrega conferidos"
}

# =====================================================================
# 2. Push -- so a entrega
# =====================================================================

Titulo "2. Push"

$mensagem = @"
perf(api): pool asyncpg por worker + CORS por ambiente

Pool asyncpg criado no lifespan, um por worker (DB_POOL_MIN=1,
DB_POOL_MAX=5; com --workers 4 o teto e 20 conexoes). get_conn tira do
pool e devolve no fim da request; sem pool em app.state (suite de testes,
ou banco fora no boot) cai no connect-por-request de antes. O shutdown
fecha o pool depois da descarga da telemetria e volta app.state.pool
para None -- sem isso, um pool morto ficaria no app para os testes
seguintes. /health ganha "pool": true|false.

CORS deixa de ser "*" em producao: vazio vira https://hipogestao.com.br
(+ www), e "*" no .env e descartado. Sem trava que impeca a API de subir:
o front chama a API pela mesma origem, e com extra="forbid" nao haveria
ordem de deploy que satisfizesse uma variavel obrigatoria nova.

config.py tambem declara ANTHROPIC_MODEL_AVALIACAO (lido pelo scorecard
do 030 via getattr), para a troca de modelo pelo .env nao derrubar a API.

Nenhuma linha nova no .env. Sem migration.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GQSPZC4cj5GrDPJaMGyyHJ
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Write-Host "  Vai no commit (e SO isto):" -ForegroundColor DarkGray
    & git status --short -- $gitEntrega
    $fora = & git status --porcelain | Where-Object {
        $caminho = $_.Substring(3).Replace("/", "\")
        -not ($entrega -contains $caminho)
    }
    if ($fora) {
        Write-Host ""
        Write-Host "  Fica FORA do commit (modificado, mas nao e desta entrega):" -ForegroundColor DarkGray
        $fora | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
    }
    Confirmar "Commitar os arquivos da entrega e dar push na main?"

    & git add -- $gitEntrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path ([IO.Path]::GetTempPath()) "hipo-commit-031.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"

    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 3. Espera o codigo novo e confere
# =====================================================================

Titulo "3. Esperando o CI"

if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    Write-Host "  Os 3 jobs precisam ficar verdes. Pergunto ao /api/health ate aparecer o campo 'pool'." -ForegroundColor Gray
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $saude = $null
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        try {
            $saude = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 10
        } catch { $saude = $null }
        if ($saude -and ($saude.PSObject.Properties.Name -contains "pool")) { break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not ($saude -and ($saude.PSObject.Properties.Name -contains "pool"))) {
        Aviso "o codigo novo nao apareceu em $EsperaMax s. Olhe o Actions no GitHub."
        exit 1
    }
    Bom "codigo novo no ar (versao $($saude.versao))"

    if ($saude.pool -eq $true) {
        Bom "pool asyncpg ativo"
    } else {
        Aviso "o worker que respondeu esta SEM pool (caiu no connect-por-request)."
        Write-Host "     A API funciona igual, mas veja por que o pool nao subiu:" -ForegroundColor Yellow
        Write-Host "     ssh ... 'sudo journalctl -u hipo-api -n 80 | grep -i pool'" -ForegroundColor Yellow
    }

    Passo "CORS: preflight vindo do proprio dominio..."
    $h = @{ "Origin" = $Url; "Access-Control-Request-Method" = "GET" }
    try {
        $r = Invoke-WebRequest -Uri "$Url/api/health" -Method Options -Headers $h -UseBasicParsing -TimeoutSec 10
        $permitida = $r.Headers["Access-Control-Allow-Origin"]
        if ($permitida -eq $Url) { Bom "liberado para $Url" }
        else { Aviso "resposta sem Access-Control-Allow-Origin=$Url (veio '$permitida')" }
    } catch {
        Aviso "preflight do proprio dominio falhou: $($_.Exception.Message)"
    }

    Passo "CORS: preflight de uma origem estranha (tem de ser recusado)..."
    $h = @{ "Origin" = "https://exemplo-qualquer.com"; "Access-Control-Request-Method" = "GET" }
    $recusado = $false
    try {
        $r = Invoke-WebRequest -Uri "$Url/api/health" -Method Options -Headers $h -UseBasicParsing -TimeoutSec 10
        if (-not $r.Headers["Access-Control-Allow-Origin"]) { $recusado = $true }
    } catch { $recusado = $true }   # 400 do Starlette cai aqui
    if ($recusado) { Bom "origem estranha recusada" }
    else { Aviso "origem estranha foi ACEITA -- o CORS de producao nao entrou" }
}

Titulo "Pronto"
Write-Host @"
  1. Nada a fazer no navegador: o front nao mudou e ninguem precisa relogar.
  2. Se der problema, o reverso e um 'git revert' deste commit e push --
     o codigo antigo nao conhece os campos novos, mas eles tambem nao
     estao no .env, entao nao ha armadilha de extra="forbid".
  3. Para ajustar o pool (ex.: 'connection reset' sob carga), DEPOIS deste
     deploy no ar: DB_POOL_MAX=8 no .env e restart do hipo-api.
"@ -ForegroundColor White
