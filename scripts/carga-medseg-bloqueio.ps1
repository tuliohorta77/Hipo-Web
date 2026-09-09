<#
    HIPO - Marca os clientes da MedSeg como "nao prospectar".

    Roda do Windows, mas a carga acontece NA EC2: e la que mora o .env com a
    DATABASE_URL e o venv com o asyncpg. Este script so manda os arquivos e
    dispara o lado de la.

    ORDEM OBRIGATORIA: a migration 010 precisa estar aplicada em producao
    ANTES desta carga. Sem a coluna nao_prospectar, o UPDATE morre no meio e
    a transacao inteira volta.

        psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f api/migrations/010_nao_prospectar.sql

    USO (da raiz do projeto):

        .\scripts\carga-medseg-bloqueio.ps1              # dry-run
        .\scripts\carga-medseg-bloqueio.ps1 -Commit      # grava

    Leia o dry-run antes. Sao 326 CNPJ (a AERO PALETES ficou de fora nesta
    rodada -- ver api\scripts\dados\medseg_fora.csv). O numero de "contas criadas" diz
    quantas ainda nao existiam no HIPO; o resto ja estava la e so ganha a
    marca. Confira tambem a lista de contas bloqueadas COM negocio em aberto:
    o bloqueio nao fecha oportunidade nenhuma, e essas precisam ser
    encerradas a mao.
#>
[CmdletBinding()]
param(
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz       = Split-Path -Parent $PSScriptRoot
$importador = Join-Path $raiz "api\scripts\importar_medseg_bloqueio.py"
$payload    = Join-Path $raiz "api\scripts\dados\medseg_nao_prospectar_2026-09-09.json"
$remoto     = Join-Path $raiz "scripts\carga_medseg_bloqueio_remoto.sh"

foreach ($f in @($Chave, $importador, $payload, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}

Write-Host "servidor : $Servidor"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host ""

Write-Host "Enviando arquivos..." -ForegroundColor Cyan
scp -i $Chave $importador "${Servidor}:/tmp/importar_medseg_bloqueio.py"
if ($LASTEXITCODE -ne 0) { throw "scp do importador falhou." }
scp -i $Chave $payload    "${Servidor}:/tmp/medseg_nao_prospectar_2026-09-09.json"
if ($LASTEXITCODE -ne 0) { throw "scp do payload falhou." }
scp -i $Chave $remoto     "${Servidor}:/tmp/carga_medseg_bloqueio_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

# O .sh sai do Windows podendo levar CRLF; o tr limpa antes do bash ler.
Write-Host "Executando na EC2..." -ForegroundColor Cyan
$flag = if ($Commit) { "--commit" } else { "" }
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/carga_medseg_bloqueio_remoto.sh > /tmp/carga-medseg.sh && bash /tmp/carga-medseg.sh $flag"

if ($LASTEXITCODE -ne 0) {
    throw "A carga falhou na EC2. Nada foi gravado - a transacao inteira e desfeita em caso de erro."
}

Write-Host ""
if ($Commit) {
    Write-Host "Carga concluida. Confira o KPI 'Nao prospectar' em https://hipogestao.com.br/crm/contas" -ForegroundColor Green
} else {
    Write-Host "Dry-run terminado. Se os numeros baterem, rode de novo com -Commit." -ForegroundColor Yellow
}
