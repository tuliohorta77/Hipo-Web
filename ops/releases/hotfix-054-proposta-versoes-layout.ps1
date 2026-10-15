# =====================================================================
#  HIPO -- hotfix 054: layout das versoes da proposta
# =====================================================================
#
#  Aba Proposta > "Versoes geradas": a fileira de botoes (Ver, E-mail,
#  Contrato, PPTX, PDF) tinha shrink-0 e ficava ao lado do texto. Nao
#  quebrava linha e espremia valor/vidas/datas numa coluna de uma
#  palavra por linha. Agora:
#    * botoes da versao numa linha propria, abaixo do texto
#    * BotoesArquivo sem shrink-0 (quebra linha quando falta espaco)
#    * linhas por CNPJ: razao social com largura minima, botoes descem
#  So frontend. Sem migration, sem mexer na EC2.
#
#    1. pre-voo   -- arquivo, ramo, base do git
#    2. testes    -- vitest da AbaProposta e Oportunidades
#    3. push      -- SO os arquivos da entrega
#    4. espera    -- ate o build novo chegar em /var/www/hipo
#
#  USO (da raiz do repositorio):
#     .\ops\releases\hotfix-054-proposta-versoes-layout.ps1 -Simular
#     .\ops\releases\hotfix-054-proposta-versoes-layout.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 1800
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}
function Bom($texto)   { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !!  $texto" -ForegroundColor Yellow }
function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}
function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

$alvo = "$Usuario@$Servidor"
Set-Location $Pasta

# Commit sobre o qual a entrega foi feita (Monitor: venda reaberta, 15/10/2026).
$base = "acc2e00"

$substituidos = @(
    "web\src\components\crm\AbaProposta.jsx"
)
$novos = @(
    "ops\releases\hotfix-054-proposta-versoes-layout.ps1"
)
$entrega = $substituidos + $novos

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }
if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) { Abortar "rode da raiz do repositorio." }
$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega presentes"
$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne "main") { Abortar "voce esta no ramo '$ramo', nao na main." }
& git cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
& git merge-base --is-ancestor $base HEAD
if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
$alterado = & git diff --name-only -- $git_substituidos
if (-not $alterado) { Abortar "o AbaProposta.jsx da pasta e igual ao do git -- a correcao nao foi copiada?" }
Bom "base $base no HEAD, AbaProposta.jsx com a correcao"


Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if ($npx -and (Test-Path (Join-Path $Pasta "web\node_modules"))) {
        Push-Location (Join-Path $Pasta "web")
        try {
            & npx vitest run src/tests/AbaProposta.test.jsx src/tests/Oportunidades.test.jsx
            if ($LASTEXITCODE -ne 0) { Abortar "testes do front falharam." }
            Bom "vitest verde"
        } finally { Pop-Location }
    } else {
        Aviso "npx ou web\node_modules nao encontrado -- os testes ficam so com o CI"
    }
}


Titulo "3. Push"
# Guarda qual bundle esta no ar agora, para saber quando o novo chegar.
$antes = $null
if (-not $Simular -and (Test-Path $Chave)) {
    $antes = (& ssh -i $Chave -o ConnectTimeout=10 $alvo "md5sum /var/www/hipo/index.html" 2>$null)
}

$mensagem = @"
fix(propostas): texto da versao nao fica mais espremido pelos botoes (hotfix 054)

- Botoes da versao (Ver, E-mail, Contrato, PPTX, PDF) numa linha
  propria, abaixo do valor, vidas, datas e status de aprovacao.
- BotoesArquivo sem shrink-0: a fileira quebra linha quando o card e
  estreito. Prop alinhar (start/end).
- Linhas por CNPJ: razao social com largura minima; botoes descem.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015eCYZqLQXHeen2aRFxr5zH
"@
if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar o hotfix 054 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-054.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}


Titulo "4. Esperando o CI"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} elseif (-not $antes) {
    Aviso "nao consegui ler o bundle atual por SSH (chave ou IP). Acompanhe no Actions."
    Aviso "Se for o IP: .\ops\utilitarios\liberar-meu-ip-ssh.ps1"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        Start-Sleep -Seconds 20
        $agora = (& ssh -i $Chave -o ConnectTimeout=10 $alvo "md5sum /var/www/hipo/index.html" 2>$null)
        if ($agora -and ($agora -ne $antes)) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
    }
    if (-not $chegou) { Aviso "o build novo nao chegou em $EsperaMax s. Olhe o Actions."; exit 1 }
    Bom "build novo no ar"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no HIPO.
  2. Abra uma oportunidade > aba Proposta > Versoes geradas: valor,
     vidas e datas em linhas inteiras, botoes logo abaixo.
"@ -ForegroundColor White
