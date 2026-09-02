<#
    HIPO - Carga das oportunidades ativas do CRM Omie.

    Roda do Windows, mas a carga acontece NA EC2: e la que mora o .env com a
    DATABASE_URL e o venv com o asyncpg. Este script so manda os arquivos e
    dispara o lado de la.

    USO (da raiz do projeto, "Hipo - v1.4.0"):

        .\scripts\carga-crm-omie.ps1              # dry-run, nao grava nada
        .\scripts\carga-crm-omie.ps1 -Commit      # grava de verdade

    Rode o dry-run primeiro e leia os numeros. Sao 313 contas, 297 contatos e
    315 oportunidades; se aparecer outra coisa, pare e investigue.
#>
[CmdletBinding()]
param(
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

# Ancorado na pasta do script, nao no diretorio corrente: rodar de dentro de
# api\ ou da raiz da o mesmo resultado.
$raiz = Split-Path -Parent $PSScriptRoot
$importador = Join-Path $raiz "api\scripts\importar_crm_omie.py"
$payload    = Join-Path $raiz "api\scripts\dados\crm_omie_ativas_2026-09-01.json"
$remoto     = Join-Path $raiz "scripts\carga_crm_omie_remoto.sh"

foreach ($f in @($Chave, $importador, $payload, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}

Write-Host "servidor : $Servidor"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host ""

Write-Host "Enviando arquivos..." -ForegroundColor Cyan
scp -i $Chave $importador "${Servidor}:/tmp/importar_crm_omie.py"
if ($LASTEXITCODE -ne 0) { throw "scp do importador falhou." }
scp -i $Chave $payload    "${Servidor}:/tmp/crm_omie_ativas_2026-09-01.json"
if ($LASTEXITCODE -ne 0) { throw "scp do payload falhou." }
scp -i $Chave $remoto     "${Servidor}:/tmp/carga_crm_omie_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

# O arquivo .sh sai do Windows podendo levar CRLF; o tr limpa antes do bash ler.
Write-Host "Executando na EC2..." -ForegroundColor Cyan
$flag = if ($Commit) { "--commit" } else { "" }
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/carga_crm_omie_remoto.sh > /tmp/carga.sh && bash /tmp/carga.sh $flag"

if ($LASTEXITCODE -ne 0) {
    throw "A carga falhou na EC2. Nada foi gravado - a transacao inteira e desfeita em caso de erro."
}

Write-Host ""
if ($Commit) {
    Write-Host "Carga concluida. Confira em https://hipogestao.com.br" -ForegroundColor Green
} else {
    Write-Host "Dry-run terminado. Se os numeros baterem, rode de novo com -Commit." -ForegroundColor Yellow
}
