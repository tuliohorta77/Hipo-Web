<#
    HIPO - Acrescenta os envolvidos que faltaram na carga do CRM Omie.

    A carga de 01/09 subiu so com SDR (Gabriel e Kethlleen). Jakeline e Bruno,
    que sao EV em 43 oportunidades, ficaram sem nenhuma. Este script corrige
    isso no que ja esta em producao, sem recriar nada e sem remover ninguem.

    USO (da raiz do projeto, "Hipo - v1.4.0"):

        .\scripts\corrigir-envolvidos.ps1              # dry-run
        .\scripts\corrigir-envolvidos.ps1 -Commit      # grava
#>
[CmdletBinding()]
param(
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz    = Split-Path -Parent $PSScriptRoot
$script  = Join-Path $raiz "api\scripts\corrigir_envolvidos_crm_omie.py"
$payload = Join-Path $raiz "api\scripts\dados\crm_omie_ativas_2026-09-01.json"
$remoto  = Join-Path $raiz "scripts\corrigir_envolvidos_remoto.sh"

foreach ($f in @($Chave, $script, $payload, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}

Write-Host "servidor : $Servidor"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host ""

Write-Host "Enviando arquivos..." -ForegroundColor Cyan
scp -i $Chave $script  "${Servidor}:/tmp/corrigir_envolvidos_crm_omie.py"
if ($LASTEXITCODE -ne 0) { throw "scp do script falhou." }
scp -i $Chave $payload "${Servidor}:/tmp/crm_omie_ativas_2026-09-01.json"
if ($LASTEXITCODE -ne 0) { throw "scp do payload falhou." }
scp -i $Chave $remoto  "${Servidor}:/tmp/corrigir_envolvidos_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

Write-Host "Executando na EC2..." -ForegroundColor Cyan
$flag = if ($Commit) { "--commit" } else { "" }
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/corrigir_envolvidos_remoto.sh > /tmp/corrigir.sh && bash /tmp/corrigir.sh $flag"
if ($LASTEXITCODE -ne 0) { throw "Falhou na EC2. Nada foi gravado." }

Write-Host ""
if ($Commit) {
    Write-Host "Envolvidos corrigidos. Faca logout/login no HIPO para a tela recarregar." -ForegroundColor Green
} else {
    Write-Host "Dry-run. Se os numeros baterem, rode de novo com -Commit." -ForegroundColor Yellow
}
