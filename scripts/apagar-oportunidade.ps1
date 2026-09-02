<#
    HIPO - Apaga uma oportunidade do banco de producao, pelo numero.

    Para tirar registro de teste. Nao existe rota para isso de proposito: no
    produto, oportunidade que nao vingou e CANCELADA, o que preserva a trilha.

    USO (da raiz do projeto, "Hipo - v1.4.0"):

        .\scripts\apagar-oportunidade.ps1 OPP-2026-00001            # so mostra
        .\scripts\apagar-oportunidade.ps1 OPP-2026-00001 -Commit    # apaga

    Vao junto, por CASCADE: tarefas, eventos, envolvidos e concorrentes da
    oportunidade. A conta e o contato FICAM.

    O backup em JSON e trazido para .\backups\ antes de qualquer exclusao.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Numero,
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz    = Split-Path -Parent $PSScriptRoot
$script  = Join-Path $raiz "api\scripts\apagar_oportunidade.py"
$remoto  = Join-Path $raiz "scripts\apagar_oportunidade_remoto.sh"
$backups = Join-Path $raiz "backups"

foreach ($f in @($Chave, $script, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}
if (-not (Test-Path $backups)) { New-Item -ItemType Directory -Path $backups | Out-Null }

Write-Host "servidor : $Servidor"
Write-Host "alvo     : $Numero"
Write-Host "modo     : $(if ($Commit) { 'COMMIT - APAGA' } else { 'DRY-RUN' })"
Write-Host ""

scp -i $Chave $script "${Servidor}:/tmp/apagar_oportunidade.py"
if ($LASTEXITCODE -ne 0) { throw "scp do script falhou." }
scp -i $Chave $remoto  "${Servidor}:/tmp/apagar_oportunidade_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

$flag = if ($Commit) { "--commit" } else { "" }
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/apagar_oportunidade_remoto.sh > /tmp/apagar.sh && bash /tmp/apagar.sh $Numero $flag"
if ($LASTEXITCODE -ne 0) { throw "Falhou na EC2. Nada foi apagado." }

# Traz o backup para ca, apagando ou nao - e barato e evita depender do /tmp da EC2.
$nomeBackup = "$($Numero -replace '/', '-')_backup.json"
scp -i $Chave "${Servidor}:/tmp/$nomeBackup" (Join-Path $backups $nomeBackup) 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "backup salvo em backups\$nomeBackup" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "AVISO: nao consegui trazer o backup da EC2 (ele continua em /tmp la)." -ForegroundColor Yellow
}

Write-Host ""
if ($Commit) {
    Write-Host "$Numero apagada." -ForegroundColor Green
} else {
    Write-Host "Dry-run. Se for isso mesmo, rode de novo com -Commit." -ForegroundColor Yellow
}
