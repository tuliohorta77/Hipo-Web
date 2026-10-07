# =====================================================================
#  HIPO -- confirmacao da vespera para as reunioes JA MARCADAS (048)
# =====================================================================
#
#  Roda nas DUAS bases (principal e MOS, se existir). Precisa do deploy
#  da 048 verde no servidor: o script usa a regra do codigo deployado.
#
#  USO (da raiz do projeto)
#     .\scripts\criar-confirmacoes-vespera.ps1            (so mostra)
#     .\scripts\criar-confirmacoes-vespera.ps1 -Commit    (grava)
#
#  Rodar de novo nao duplica. ASCII puro.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@hipogestao.com.br"
)

$ErrorActionPreference = "Stop"
$raiz   = Split-Path $PSScriptRoot -Parent
$script = Join-Path $raiz "api\scripts\criar_confirmacoes_vespera.py"
$remoto = Join-Path $raiz "scripts\criar_confirmacoes_vespera_remoto.sh"

foreach ($f in @($Chave, $script, $remoto)) {
    if (-not (Test-Path $f)) { throw "nao achei: $f" }
}

& ssh -i $Chave $Servidor "mkdir -p /tmp/hipo-048"
if ($LASTEXITCODE -ne 0) { throw "ssh falhou." }
& scp -i $Chave $script "${Servidor}:/tmp/hipo-048/criar_confirmacoes_vespera.py"
if ($LASTEXITCODE -ne 0) { throw "scp do script falhou." }
& scp -i $Chave $remoto "${Servidor}:/tmp/hipo-048/remoto.sh.crlf"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }
& ssh -i $Chave $Servidor "tr -d '\r' < /tmp/hipo-048/remoto.sh.crlf > /tmp/hipo-048/remoto.sh"

$flag = ""
if ($Commit) { $flag = "--commit" }

foreach ($base in @("principal", "mos")) {
    Write-Host ""
    & ssh -i $Chave $Servidor "bash /tmp/hipo-048/remoto.sh $base $flag"
    if ($LASTEXITCODE -ne 0) { throw "falhou na base $base (codigo $LASTEXITCODE)." }
}

Write-Host ""
if ($Commit) {
    Write-Host "Pronto. As confirmacoes aparecem em Tarefas para quem agendou." -ForegroundColor Green
} else {
    Write-Host "Simulacao. Confira a lista e rode de novo com -Commit." -ForegroundColor Yellow
}
