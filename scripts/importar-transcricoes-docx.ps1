<#
    HIPO - Importa transcricoes do Google Meet (.docx) para as reunioes do HIPO.

    Para quem conduziu a reuniao por fora da agenda do HIPO: o .docx que o Meet
    salva no Drive vira a transcricao da tarefa, com resumo e proximos passos,
    igual a coleta automatica. Regras em api/scripts/importar_transcricoes_docx.py.

    Os arquivos vao para a EC2 com nome sem acento (evita tropeco de encoding
    no scp) e sao APAGADOS de la no fim de cada rodada: e fala de cliente.

    USO (da raiz do projeto, "Hipo - vX.Y.Z"):

        # 1) dry-run: mostra o que faria com cada arquivo
        .\scripts\importar-transcricoes-docx.ps1 -Pasta "C:\...\transcricao Reunioes jakeline" -Responsavel jakeline

        # 2) grava
        .\scripts\importar-transcricoes-docx.ps1 -Pasta "..." -Responsavel jakeline -Por tulio@controllermedseg.com -Commit

        # decidir os REVISAR (trecho do nome do arquivo = uuid da tarefa, ou novo)
        ... -Mapa "VOXEL=novo","FQS=<uuid>"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Pasta,
    [Parameter(Mandatory = $true)][string]$Responsavel,
    [string]$Por,
    [string]$Tipo = "AP",
    [string[]]$Mapa = @(),
    [switch]$Sobrescrever,
    [switch]$SemResumo,
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@hipogestao.com.br"
)

$ErrorActionPreference = "Stop"

$raiz   = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz "api\scripts\importar_transcricoes_docx.py"
$dados  = Join-Path $raiz "api\scripts\dados"

foreach ($f in @($Chave, $script, $Pasta)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}
if ($Commit -and -not $Por) { throw "-Commit exige -Por <e-mail de quem esta lancando>." }
if (-not (Test-Path $dados)) { New-Item -ItemType Directory -Path $dados | Out-Null }

function Sem-Acento([string]$s) {
    $n  = $s.Normalize([Text.NormalizationForm]::FormD)
    $sb = New-Object Text.StringBuilder
    foreach ($ch in $n.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$sb.Append($ch)
        }
    }
    return ($sb.ToString() -replace '[^\x20-\x7E]', '_')
}

# Copia com nome ASCII para uma pasta temporaria.
$stage = Join-Path $env:TEMP ("hipo_import_" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Path $stage | Out-Null
$arquivos = Get-ChildItem -Path $Pasta -Filter *.docx -Recurse | Where-Object { $_.Name -notlike '~$*' }
if (-not $arquivos) { throw "Nenhum .docx em $Pasta" }
foreach ($a in $arquivos) {
    Copy-Item -LiteralPath $a.FullName -Destination (Join-Path $stage (Sem-Acento $a.Name))
}

$sufixo   = if ($Commit) { "aplicado" } else { "dry-run" }
$csvLocal = Join-Path $dados ("transcricoes_import_{0}_{1}.csv" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $sufixo)

Write-Host "servidor : $Servidor"
Write-Host "arquivos : $($arquivos.Count)"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host ""

try {
    Write-Host "Enviando..." -ForegroundColor Cyan
    ssh -i $Chave $Servidor "rm -rf /tmp/hipo_import && mkdir -p /tmp/hipo_import"
    if ($LASTEXITCODE -ne 0) { throw "ssh falhou (chave, IP liberado no SG?)." }
    scp -i $Chave $script "${Servidor}:/tmp/hipo_import/importar_transcricoes_docx.py"
    if ($LASTEXITCODE -ne 0) { throw "scp do script falhou." }
    # -r da pasta inteira: o scp do Windows nao expande curinga local.
    scp -r -i $Chave $stage "${Servidor}:/tmp/hipo_import/docx"
    if ($LASTEXITCODE -ne 0) { throw "scp dos .docx falhou." }

    $pyArgs = @(
        "--pasta /tmp/hipo_import/docx",
        "--responsavel '$Responsavel'",
        "--tipo '$Tipo'",
        "--csv /tmp/hipo_import/relatorio.csv"
    )
    if ($Por)          { $pyArgs += "--por '$Por'" }
    foreach ($m in $Mapa) { $pyArgs += "--mapa '$m'" }
    if ($Sobrescrever) { $pyArgs += "--sobrescrever" }
    if ($SemResumo)    { $pyArgs += "--sem-resumo" }
    if ($Commit)       { $pyArgs += "--commit" }

    # Como ec2-user, igual ao hipo-transcricoes.service: e o dono do .env,
    # que o config.py le sozinho. Com o usuario hipo o .env nao abre.
    $remoto = "cd /home/hipo/app/api && PYTHONPATH=/home/hipo/app/api PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 " +
              "python3 /tmp/hipo_import/importar_transcricoes_docx.py " + ($pyArgs -join " ")

    Write-Host "Executando na EC2..." -ForegroundColor Cyan
    ssh -i $Chave $Servidor $remoto
    $saida = $LASTEXITCODE

    scp -i $Chave "${Servidor}:/tmp/hipo_import/relatorio.csv" $csvLocal
    if ($LASTEXITCODE -eq 0) { Write-Host "CSV: $csvLocal" -ForegroundColor Green }

    if ($saida -ne 0) { throw "O script terminou com erro (codigo $saida). Veja a saida acima." }
}
finally {
    # A transcricao e fala de cliente: nao fica largada no /tmp da EC2 nem no TEMP local.
    ssh -i $Chave $Servidor "rm -rf /tmp/hipo_import" | Out-Null
    Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
}

Write-Host ""
if ($Commit) {
    Write-Host "Gravado. Ctrl+Shift+R na tela para ver o painel Transcricao nas tarefas." -ForegroundColor Green
} else {
    Write-Host "Dry-run. Confira a lista; decida os REVISAR com -Mapa e rode de novo com -Commit." -ForegroundColor Yellow
}
