# =====================================================================
#  HIPO -- backfill do scorecard (entrega 030)
# =====================================================================
#
#  Avalia contra o Roteiro de Vendas as reunioes que ja tinham
#  transcricao antes do deploy 030. Rode DEPOIS do deploy-030.
#
#  USO
#     .\avaliar-reunioes.ps1                       # ensaio: so lista
#     .\avaliar-reunioes.ps1 -Aplicar              # avalia desde 01/09
#     .\avaliar-reunioes.ps1 -Desde 2026-09-15 -Aplicar
#     .\avaliar-reunioes.ps1 -Aplicar -Refazer     # refaz as prontas
#     .\avaliar-reunioes.ps1 -Aplicar -Limite 3    # so 3, para conferir
#
#  Cada reuniao leva ate 2 minutos na IA. O trabalho roda numa unit do
#  systemd no servidor: se a janela fechar no meio, ele continua.
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [string]$Desde = "2026-09-01",
    [switch]$Aplicar,
    [switch]$Refazer,
    [int]$Limite = 0,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user"
)

$ErrorActionPreference = "Stop"

function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    exit 1
}

if ($Desde -notmatch '^\d{4}-\d{2}-\d{2}$') { Abortar "use -Desde AAAA-MM-DD." }
$script = Join-Path $Pasta "infra\avaliar-reunioes.sh"
if (-not (Test-Path $script)) { Abortar "rode de dentro da pasta do projeto (nao achei $script)." }
if (-not (Test-Path $Chave))  { Abortar "nao achei a chave SSH: $Chave" }

$alvo = "$Usuario@$Servidor"
$argumentos = @($Desde)
if ($Aplicar) { $argumentos += "--aplicar" }
if ($Refazer) { $argumentos += "--refazer" }
if ($Limite -gt 0) { $argumentos += @("--limite", "$Limite") }

Write-Host "  -> enviando o script..." -ForegroundColor Gray
& scp -i $Chave -o StrictHostKeyChecking=accept-new $script "${alvo}:/tmp/"
if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }

& ssh -t -i $Chave $alvo "bash /tmp/avaliar-reunioes.sh $($argumentos -join ' ')"
if ($LASTEXITCODE -ne 0) { Abortar "o backfill terminou com erro (codigo $LASTEXITCODE)." }

if (-not $Aplicar) {
    Write-Host ""
    Write-Host "  Ensaio feito. Para avaliar:  .\avaliar-reunioes.ps1 -Aplicar" -ForegroundColor White
}
