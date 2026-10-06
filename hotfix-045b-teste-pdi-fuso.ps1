# =====================================================================
#  HIPO -- hotfix 045b: teste do PDI no fuso da operacao
# =====================================================================
#
#  So teste, sem codigo de producao:
#    test_pdi usava date.today() (UTC no runner do CI). Depois das 21h
#    em Sao Paulo, "ontem em UTC" ainda e "hoje" para o servidor, e o
#    prazo nao era recusado como passado. Agora usa _hoje() de
#    routers.carreira (FUSO_OPERACAO), igual ao servidor.
#
#  USO
#     .\hotfix-045b-teste-pdi-fuso.ps1 -Simular
#     .\hotfix-045b-teste-pdi-fuso.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [string]$Pasta = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

function Bom($texto)   { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !!  $texto" -ForegroundColor Yellow }
function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}

$base = "ec8ddc1"
$entrega = @("api\tests\test_pdi.py", "hotfix-045b-teste-pdi-fuso.ps1")

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta
foreach ($f in $entrega) {
    if (-not (Test-Path (Join-Path $Pasta $f))) { Abortar "falta: $f" }
}
Bom "arquivos conferidos"

$mexidos = & git diff --name-only $base HEAD -- "api/tests/test_pdi.py"
if ($mexidos) { Abortar "algum commit depois do $base mexeu em api/tests/test_pdi.py. Me mande o atual." }
$log = & git log --oneline -1 --grep "quiz final mostra as perguntas erradas"
if (-not $log) { Abortar "nao achei o commit da 045 no HEAD. Rode 'git pull'." }
Bom "045 no HEAD: $log"

$mensagem = @"
test(pdi): prazo no fuso da operacao, nao no UTC do runner

date.today() no CI e UTC: depois das 21h em Sao Paulo, "ontem" do teste
ainda era "hoje" para o servidor e o prazo passado passava (201).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
    exit 0
}

$r = Read-Host "  Commitar o hotfix e dar push na main?  [digite SIM para seguir]"
if ($r -ne "SIM") { Abortar "cancelado por voce." }
& git add -- $entrega
if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
$tmpMsg = Join-Path $env:TEMP "hipo-commit-045b.txt"
Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
& git commit -F $tmpMsg
if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
Remove-Item $tmpMsg -ErrorAction SilentlyContinue
& git push
if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
Bom "push feito -- acompanhe o Actions (3 jobs verdes sobem a 045 junto)"
