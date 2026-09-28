# =====================================================================
#  HIPO -- deploy 022: Relatorios com painel "Campos" e sem mapa de calor
# =====================================================================
#
#  O QUE MUDA (so front, 5 arquivos)
#    - Filtros, Linhas, Colunas, Valores, fonte e periodo passam a morar
#      num painel que abre pela engrenagem "Campos". Fechado por padrao;
#      abre sozinho so ao comecar um relatorio novo. Fechado, uma linha
#      resume fonte, periodo, linhas, colunas e filtros.
#    - Sai o destaque de cor por quantidade nas celulas (e a opcao
#      "Destacar maiores").
#
#  SEM MIGRATION E SEM SSH: o CI faz o rsync e reinicia sozinho.
#
#  O QUE ESTE SCRIPT FAZ
#    1. pre-voo  -- arquivos no lugar
#    2. testes   -- vitest e build do front
#    3. push     -- SO os arquivos da entrega
#
#  USO
#     .\deploy-022-relatorios-campos.ps1 -Simular
#     .\deploy-022-relatorios-campos.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [string]$Pasta = (Get-Location).Path
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

$entrega = @(
    "web\src\pages\crm\Relatorios.jsx",
    "web\src\components\relatorios\TabelaDinamica.jsx",
    "web\src\components\relatorios\pivot.js",
    "web\src\tests\Relatorios.test.jsx",
    "web\src\tests\relatoriosLogica.test.js",
    "deploy-022-relatorios-campos.ps1"
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

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

# A entrega 021 precisa estar no ar: esta muda arquivos que ela criou.
if (-not (Test-Path (Join-Path $Pasta "api\routers\crm_relatorios.py"))) {
    Abortar "a entrega 021 (Relatorios) nao esta nesta pasta."
}
$marca = Select-String -Path (Join-Path $Pasta "web\src\pages\crm\Relatorios.jsx") -Pattern "rel-painel-campos" -Quiet
if (-not $marca) { Abortar "Relatorios.jsx nao e a versao nova (painel Campos)." }
Bom "versao nova do Relatorios.jsx no lugar"

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
feat(relatorios): campos atras da engrenagem e sem mapa de calor

Filtros, linhas, colunas, valores, fonte e periodo passam a morar no
painel "Campos" (engrenagem), fechado por padrao -- a tela e da tabela.
Abre sozinho so ao comecar um relatorio novo. Fechado, uma linha resume
fonte, periodo, linhas, colunas e filtros.

Sai o destaque de cor por quantidade nas celulas e a opcao "Destacar
maiores". Relatorios salvos com a opcao antiga continuam abrindo.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mt4fExbdSx7wRJV3rGdvzL
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Write-Host "  Vai no commit (e SO isto):" -ForegroundColor DarkGray
    & git status --short -- $entrega
    Confirmar "Commitar os arquivos da entrega e dar push na main?"

    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-022.txt"
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
  1. Espere os 3 jobs ficarem verdes no Actions (~3 min).
  2. Ctrl+Shift+R na tela de Relatorios. Nao precisa relogar.
"@ -ForegroundColor White
