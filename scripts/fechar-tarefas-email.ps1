<#
    HIPO - Da baixa nas tarefas de e-mail que a carga do CRM Omie subiu abertas.

    No Omie, o registro de e-mail era anotacao de envio ja acontecido: nao
    existia campo "Realizada" para ele. A carga trouxe essas linhas como tarefa
    tipo 'email' sem conclusao, e elas aparecem no HIPO como pendencia atrasada.
    Este script mapeia todas, traz o CSV para conferencia e fecha cada uma com
    a data do proprio envio (o prazo).

    Nao encosta em tarefa de e-mail criada a mao no HIPO: o filtro e a marca de
    importacao da carga.

    USO (da raiz do projeto, "Hipo - v1.4.0"):

        .\scripts\fechar-tarefas-email.ps1              # dry-run + CSV
        .\scripts\fechar-tarefas-email.ps1 -Commit      # grava
#>
[CmdletBinding()]
param(
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz   = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz "api\scripts\fechar_tarefas_email_crm_omie.py"
$remoto = Join-Path $raiz "scripts\fechar_tarefas_email_remoto.sh"
$dados  = Join-Path $raiz "api\scripts\dados"

foreach ($f in @($Chave, $script, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}
if (-not (Test-Path $dados)) { New-Item -ItemType Directory -Path $dados | Out-Null }

$sufixo  = if ($Commit) { "aplicado" } else { "dry-run" }
$csvLocal = Join-Path $dados ("tarefas_email_baixa_{0}_{1}.csv" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $sufixo)

Write-Host "servidor : $Servidor"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host ""

Write-Host "Enviando arquivos..." -ForegroundColor Cyan
scp -i $Chave $script "${Servidor}:/tmp/fechar_tarefas_email_crm_omie.py"
if ($LASTEXITCODE -ne 0) { throw "scp do script falhou." }
scp -i $Chave $remoto "${Servidor}:/tmp/fechar_tarefas_email_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

Write-Host "Executando na EC2..." -ForegroundColor Cyan
$flag = if ($Commit) { "--commit" } else { "" }
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/fechar_tarefas_email_remoto.sh > /tmp/fechar_email.sh && bash /tmp/fechar_email.sh $flag"
if ($LASTEXITCODE -ne 0) { throw "Falhou na EC2. Nada foi gravado." }

Write-Host ""
Write-Host "Trazendo o mapeamento..." -ForegroundColor Cyan
scp -i $Chave "${Servidor}:/tmp/tarefas_email_baixa.csv" $csvLocal
if ($LASTEXITCODE -ne 0) { throw "scp do CSV falhou. A operacao no banco ja terminou; so o arquivo nao veio." }
Write-Host "CSV: $csvLocal" -ForegroundColor Green

Write-Host ""
if ($Commit) {
    Write-Host "Tarefas de e-mail baixadas. Recarregue a tela de tarefas para ver." -ForegroundColor Green
} else {
    Write-Host "Dry-run. Confira o CSV e, se estiver certo, rode de novo com -Commit." -ForegroundColor Yellow
}
