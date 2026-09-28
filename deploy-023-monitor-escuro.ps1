# =====================================================================
#  HIPO -- deploy 023: tema escuro no Monitor
# =====================================================================
#
#  O QUE MUDA (so front, 6 arquivos)
#    - Botao lua/sol na barra do Monitor. A escolha fica gravada NAQUELE
#      navegador (localStorage): a TV fica escura, o notebook continua
#      claro, mesmo com o mesmo usuario.
#    - Escurece tudo do Monitor: quadros, a lista da carinha, o formulario
#      da reuniao e Metas e calendario. O resto do HIPO nao muda.
#    - Como: as cores hipo-* viraram variaveis CSS (index.css). O claro tem
#      exatamente os mesmos valores de antes; a classe .tema-escuro no
#      container do Monitor redefine as variaveis so ali dentro.
#    - Conserta de carona: no `npm run dev` o Monitor ficava parado em
#      "Carregando painel..." (StrictMode). Producao nao era afetada.
#
#  SEM MIGRATION E SEM SSH: o CI faz o rsync e reinicia sozinho.
#
#  O QUE ESTE SCRIPT FAZ
#    1. pre-voo  -- arquivos no lugar
#    2. testes   -- vitest e build do front
#    3. push     -- SO os arquivos da entrega
#
#  USO
#     .\deploy-023-monitor-escuro.ps1 -Simular
#     .\deploy-023-monitor-escuro.ps1
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
    "web\tailwind.config.js",
    "web\src\index.css",
    "web\src\components\ui\Modal.jsx",
    "web\src\components\monitor\monitorComum.js",
    "web\src\pages\Monitor.jsx",
    "web\src\tests\Monitor.test.jsx",
    "deploy-023-monitor-escuro.ps1"
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

$marca = Select-String -Path (Join-Path $Pasta "web\src\index.css") -Pattern "tema-escuro" -Quiet
if (-not $marca) { Abortar "index.css nao e a versao nova (tema escuro)." }
Bom "versao nova do index.css no lugar"

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
feat(monitor): tema escuro, escolhido por tela

Botao lua/sol na barra do Monitor; a escolha fica no localStorage daquele
navegador (a TV escura, o notebook claro, mesmo usuario). Escurece tudo que
abre dentro do painel: quadros, lista da carinha, formulario da reuniao e
Metas e calendario.

As cores hipo-* viraram variaveis CSS (index.css) com os mesmos valores do
manual no claro; .tema-escuro redefine as variaveis so no container do
Monitor. Overlay dos modais ganhou token proprio (hipo-overlay).

Fix: no dev (StrictMode) o Monitor ficava em "Carregando painel..." porque
o ref `montado` nao voltava para true na remontagem.

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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-023.txt"
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
  2. Ctrl+Shift+R no Monitor. Nao precisa relogar.
  3. Na TV: botao "Escuro" uma vez -- ela lembra sozinha dali em diante.
"@ -ForegroundColor White
