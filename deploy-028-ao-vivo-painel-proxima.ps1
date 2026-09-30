# =====================================================================
#  HIPO -- deploy 028: Reuniao ao vivo -- painel da proxima visivel
# =====================================================================
#
#  Deploy SO DE FRONT. Correcao da 027: quando Realizada exige a
#  proxima tarefa (ultima tarefa aberta de oportunidade viva), o painel
#  abria no alto da pagina sem aviso, e o clique parecia nao fazer nada.
#  Agora a tela rola ate o painel e diz o que falta.
#
#    1. pre-voo      -- arquivos no lugar, base do git
#    2. testes       -- vitest e build do front
#    3. push         -- SO os arquivos da entrega; o CI faz o resto
#
#  A BASE DO GIT: b9ccce1 (entrega 027). Dois arquivos sao substituidos.
#
#  USO
#     .\deploy-028-ao-vivo-painel-proxima.ps1 -Simular
#     .\deploy-028-ao-vivo-painel-proxima.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 900,
    [string]$Base     = "b9ccce1"
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

$alvo = "$Usuario@$Servidor"

# Arquivos EXISTENTES que a entrega substitui (conferidos contra a base).
$substituidos = @(
    "web\src\pages\crm\ReuniaoAoVivo.jsx",
    "web\src\tests\ReuniaoAoVivo.test.jsx"
)

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + @(
    "deploy-028-ao-vivo-painel-proxima.ps1"
)

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

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

Passo "base do git ($Base)..."
& git cat-file -e "$Base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Abortar "o commit $Base nao existe aqui. Rode 'git pull' e me avise."
}
& git merge-base --is-ancestor $Base HEAD
if ($LASTEXITCODE -ne 0) {
    Abortar "HEAD nao descende de $Base. Rode 'git pull' e me avise."
}
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $Base HEAD -- $git_substituidos
if ($mexidos) {
    Write-Host "  Commits depois de $Base mexeram em arquivos que a entrega substitui:" -ForegroundColor Red
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "a entrega apagaria essas mudancas. Me mande os arquivos atuais para eu refazer o patch."
}
Bom "nenhum commit depois de $Base mexeu nos arquivos substituidos"

# =====================================================================
# 2. Testes do front
# =====================================================================

Titulo "2. Testes do front"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    Push-Location (Join-Path $Pasta "web")
    try {
        Passo "vitest..."
        & npm.cmd run test -- --run
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Corrija antes de subir." }
        Bom "vitest verde"
        Passo "vite build..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Abortar "o build do front falhou." }
        Bom "build ok"
    } finally { Pop-Location }
}

# =====================================================================
# 3. Push -- so a entrega
# =====================================================================

Titulo "3. Push"

$mensagem = @"
fix(agenda): Reuniao ao vivo -- painel da proxima tarefa visivel

Realizada na ultima tarefa aberta de oportunidade viva abre o painel da
proxima tarefa (regra da casa), mas ele nascia no alto da pagina sem
aviso e o clique parecia mudo. Agora a tela rola ate o painel e explica
que falta a proxima para dar baixa.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KasXt4zEWpFfuyvyRb9zRF
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Write-Host "  Vai no commit (e SO isto):" -ForegroundColor DarkGray
    & git status --short -- $entrega
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

    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-028.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"

    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

Titulo "Pronto"
Write-Host @"
  1. Acompanhe os 3 jobs no GitHub Actions ate ficarem verdes.
  2. Ctrl+Shift+R no HIPO.
  3. Realizada que exige a proxima: a tela rola ate o painel; preencha a
     proxima tarefa e clique em "Registrar realizada".
"@ -ForegroundColor White
