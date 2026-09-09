<#
    HIPO - Carga da carteira da Oraculus como suspects.

    Roda do Windows, mas a carga acontece NA EC2: e la que mora o .env com a
    DATABASE_URL e o venv com o asyncpg.

    ORDEM: rode a carga da MedSeg (carga-medseg-bloqueio.ps1) ANTES desta. Um
    CNPJ que estiver nas duas listas tem que ja estar bloqueado quando esta
    carga passar - senao ele entra no funil e so seria barrado na proxima
    rodada. Hoje as duas listas nao se cruzam; a ordem existe para a proxima
    versao da planilha, que pode cruzar.

    O CNPJ DA ORACULUS E OBRIGATORIO
    E a conta que vira finder_conta_id das 946 oportunidades. Se ela ainda
    nao existir no HIPO, passe tambem -FinderRazao e o script a cria, ja
    marcada como parceira.

    USO (da raiz do projeto):

        # dry-run
        .\scripts\carga-oraculus.ps1 -FinderCnpj "12.345.678/0001-99"

        # grava tudo
        .\scripts\carga-oraculus.ps1 -FinderCnpj "12.345.678/0001-99" -Commit

        # grava em lote de 100 (roda de novo para continuar de onde parou)
        .\scripts\carga-oraculus.ps1 -FinderCnpj "..." -Limite 100 -Commit

    OS ENVOLVIDOS JA SAO DIVIDIDOS AO MEIO
    Por padrao, metade das oportunidades entra no nome do Gabriel e metade no
    da Kethlleen, ambos como SDR. Nao precisa passar nada: o rodizio e o
    comportamento normal do script, e ele imprime a divisao no fim.

    A divisao e por POSICAO na carteira, entao ela continua meio a meio mesmo
    que voce suba em lotes com -Limite.

    Para trocar a lista:
        -Responsaveis "fulano@controllermedseg.com,sicrano@controllermedseg.com"
    Para carregar sem ninguem:
        -SemResponsavel

    Leia o dry-run antes. Esperado: 946 contas, 463 contatos, 946
    oportunidades em suspect e 473 para cada SDR. Se aparecer outra coisa,
    pare e investigue.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FinderCnpj,
    [string]$FinderRazao = "",
    # Vazio significa "usa o padrao do importador" (Gabriel + Kethlleen).
    # Repetir a lista aqui criaria duas fontes de verdade para a mesma regra.
    [string]$Responsaveis = "",
    [switch]$SemResponsavel,
    [switch]$PularComNegocio,
    [switch]$AdotarFinder,
    [int]$Limite = 0,
    [switch]$Commit,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz       = Split-Path -Parent $PSScriptRoot
$importador = Join-Path $raiz "api\scripts\importar_oraculus.py"
$payload    = Join-Path $raiz "api\scripts\dados\oraculus_2026-09-09.json"
$remoto     = Join-Path $raiz "scripts\carga_oraculus_remoto.sh"

foreach ($f in @($Chave, $importador, $payload, $remoto)) {
    if (-not (Test-Path $f)) { throw "Nao encontrei: $f" }
}

$digitos = ($FinderCnpj -replace '\D', '')
if ($digitos.Length -ne 14) { throw "FinderCnpj precisa ter 14 digitos. Recebi: $FinderCnpj" }

Write-Host "servidor : $Servidor"
Write-Host "finder   : $digitos"
Write-Host "modo     : $(if ($Commit) { 'COMMIT' } else { 'DRY-RUN' })"
Write-Host "resp.    : $(if ($SemResponsavel) { 'NENHUM' } elseif ($Responsaveis -ne '') { $Responsaveis } else { 'Gabriel + Kethlleen (padrao, meio a meio)' })"
if ($Limite -gt 0) { Write-Host "limite   : $Limite" }
Write-Host ""

Write-Host "Enviando arquivos..." -ForegroundColor Cyan
scp -i $Chave $importador "${Servidor}:/tmp/importar_oraculus.py"
if ($LASTEXITCODE -ne 0) { throw "scp do importador falhou." }
scp -i $Chave $payload    "${Servidor}:/tmp/oraculus_2026-09-09.json"
if ($LASTEXITCODE -ne 0) { throw "scp do payload falhou." }
scp -i $Chave $remoto     "${Servidor}:/tmp/carga_oraculus_remoto.sh"
if ($LASTEXITCODE -ne 0) { throw "scp do script remoto falhou." }

# Montado como lista e unido no fim: concatenar string com if inline vira
# espaco duplicado e argumento vazio no bash.
$extraArgs = @()
if ($Commit)                  { $extraArgs += "--commit" }
if ($Limite -gt 0)            { $extraArgs += "--limite"; $extraArgs += "$Limite" }
# base64, e nao aspas: o PowerShell 5.1 remove aspas duplas ao montar a linha
# de comando de um programa externo, entao --finder-razao "RAZAO COM ESPACO"
# chega como tres palavras soltas. Aspas simples nao cobrem a apostrofe de
# "ORACULU'S CONTABIL LTDA". Base64 nao tem metacaractere nenhum.
if ($FinderRazao -ne "") {
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($FinderRazao))
    $extraArgs += "--finder-razao-b64"; $extraArgs += $b64
}
if ($PularComNegocio)         { $extraArgs += "--pular-com-negocio" }
if ($AdotarFinder)            { $extraArgs += "--adotar-finder-no-suspect" }
if ($SemResponsavel)          { $extraArgs += "--sem-responsavel" }
elseif ($Responsaveis -ne "") { $extraArgs += "--responsaveis"; $extraArgs += "$Responsaveis" }
$extras = $extraArgs -join " "

# O .sh sai do Windows podendo levar CRLF; o tr limpa antes do bash ler.
Write-Host "Executando na EC2..." -ForegroundColor Cyan
ssh -i $Chave $Servidor "tr -d '\r' < /tmp/carga_oraculus_remoto.sh > /tmp/carga-oraculus.sh && bash /tmp/carga-oraculus.sh $digitos $extras"

if ($LASTEXITCODE -ne 0) {
    throw "A carga falhou na EC2. Nada foi gravado - a transacao inteira e desfeita em caso de erro."
}

Write-Host ""
if ($Commit) {
    Write-Host "Carga concluida. Confira o funil em https://hipogestao.com.br/crm/oportunidades" -ForegroundColor Green
} else {
    Write-Host "Dry-run terminado. Se os numeros baterem, rode de novo com -Commit." -ForegroundColor Yellow
}
