# =====================================================================
#  HIPO -- deploy 024: Relatorios com visao geral (sem recorte por usuario)
# =====================================================================
#
#  O QUE MUDA (so backend, 2 arquivos)
#    - Nos Relatorios, TODO cargo passa a ver todas as oportunidades,
#      tarefas e reunioes -- igual as outras telas do CRM hoje.
#    - O recorte por envolvimento fica DESLIGADO por uma constante
#      (RECORTE_POR_ENVOLVIMENTO em api\routers\crm_relatorios.py).
#      Religar no futuro e trocar para True; os testes do recorte continuam
#      na suite, rodando com a chave ligada.
#
#  SEM MIGRATION E SEM SSH: o CI faz o rsync e reinicia sozinho.
#
#  O QUE ESTE SCRIPT FAZ
#    1. pre-voo  -- arquivos no lugar
#    2. testes   -- vitest e build do front
#    3. push     -- SO os arquivos da entrega
#
#  USO
#     .\deploy-024-relatorios-visao-geral.ps1 -Simular
#     .\deploy-024-relatorios-visao-geral.ps1
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
    "api\routers\crm_relatorios.py",
    "api\tests\test_crm_relatorios.py",
    "deploy-024-relatorios-visao-geral.ps1"
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

$marca = Select-String -Path (Join-Path $Pasta "api\routers\crm_relatorios.py") -Pattern "RECORTE_POR_ENVOLVIMENTO = False" -Quiet
if (-not $marca) { Abortar "crm_relatorios.py nao e a versao nova (visao geral)." }
Bom "versao nova do crm_relatorios.py no lugar"

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
fix(relatorios): visao geral -- todo cargo ve todas as oportunidades

Decisao de 30/09: nos relatorios, todos os usuarios veem a base inteira,
como nas outras telas do CRM. O recorte por envolvimento fica desligado
por RECORTE_POR_ENVOLVIMENTO = False em routers/crm_relatorios.py; o motor
continua sabendo aplicar e os testes do recorte rodam com a chave ligada.
TestVisaoGeral trava a decisao.

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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-024.txt"
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
  2. Nao precisa relogar nem Ctrl+Shift+R: a mudanca e so no servidor.
     Qualquer usuario ja ve a base inteira nos Relatorios.
"@ -ForegroundColor White
