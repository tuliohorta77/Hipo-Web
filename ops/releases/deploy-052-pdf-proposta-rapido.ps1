# =====================================================================
#  HIPO -- deploy 052: PDF da proposta mais rapido
# =====================================================================
#
#  O visualizador da proposta (051) levava ~20 s em "Montando o PDF".
#  Medido numa maquina de 2 vCPU: python-pptx 1-4 s + LibreOffice ~17 s
#  + 7 MB para baixar. O que muda:
#    * PDF com imagens a 200 dpi (o LibreOffice gastava o tempo
#      recomprimindo imagens de 2000-3000 px): ~7 MB -> ~3 MB
#    * os 4 slides institucionais viram PDF UMA vez (cache, montado na
#      subida da API); cada proposta converte so os slides que mudam e
#      junta as paginas (pypdf): ~3 s por proposta
#    * cada PDF montado fica em cache: reabrir e anexar no e-mail e
#      imediato
#    * a montagem roda fora do event loop (nao trava a API para os outros)
#    * modelo .pptx enxuto: 17 MB -> 8,6 MB (textura de linho do slide de
#      fechamento em cinza, 1000 px; foto de 3000 px reduzida a 2000)
#  Sem migration.
#
#    1. pre-voo   -- arquivos, base do git
#    2. testes    -- regras puras, PDF rapido e conferencia do modelo
#    3. push      -- SO os arquivos da entrega
#    4. espera    -- ate o codigo novo chegar no servidor
#    5. pypdf     -- instala na EC2 (infra/instalar-pypdf.sh) e reinicia
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-052-pdf-proposta-rapido.ps1 -Simular
#     .\ops\releases\deploy-052-pdf-proposta-rapido.ps1
#     .\ops\releases\deploy-052-pdf-proposta-rapido.ps1 -SoPypdf   (push ja feito)
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoPypdf,

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
function Passo($texto) { Write-Host "  -> $texto" -ForegroundColor Gray }
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

# Commit sobre o qual a entrega foi feita (051 + fix da agenda, 07/10/2026).
$base = "67f6aea"

$substituidos = @(
    "api\main.py",
    "api\requirements.txt",
    "api\routers\crm_emails.py",
    "api\routers\crm_propostas.py",
    "api\services\proposta_render.py",
    "api\templates\proposta_modelo.pptx",
    "api\tests\conftest.py",
    "api\tests\test_crm_proposta_multi_cnpj.py"
)
$novos = @(
    "api\scripts\otimizar_modelo_proposta.py",
    "api\tests\test_proposta_pdf_rapido.py",
    "infra\instalar-pypdf.sh",
    "ops\releases\deploy-052-pdf-proposta-rapido.ps1"
)
$entrega = $substituidos + $novos

if (-not $SoPypdf) {
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
Bom "base $base no HEAD, arquivos substituidos intactos"


Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            & python -m pytest -q --no-cov tests\test_proposta_regras.py tests\test_proposta_pdf_rapido.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes da proposta falharam." }
            & python -m scripts.conferir_modelo_proposta
            if ($LASTEXITCODE -ne 0) { Abortar "o modelo da proposta nao passou na conferencia." }
            Bom "regras e modelo verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

Titulo "3. Push"
$mensagem = @"
perf(propostas): PDF da proposta em ~3 s, e do cache depois (entrega 052)

- PDF com imagens a 200 dpi (ReduceImageResolution): o LibreOffice
  gastava o tempo recomprimindo imagens grandes; ~7 MB -> ~3 MB.
- Slides fixos (institucionais) convertidos uma vez e guardados; cada
  proposta converte so os slides variaveis e junta as paginas (pypdf).
  Cache aquecido na subida da API. Sem pypdf, cai no caminho inteiro.
- PDF de cada proposta/CNPJ em cache em disco (proposta nao muda):
  reabrir o visualizador e anexar no e-mail sao imediatos.
- Montagem fora do event loop (asyncio.to_thread) no download e no e-mail.
- Modelo .pptx 17 MB -> 8,6 MB (scripts/otimizar_modelo_proposta.py).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CDPWboU41EfBiKCaZHSU5R
"@
if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 052 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-052.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

Titulo "4. Esperando o CI"
$marcador = "grep -q aquecer_cache /home/hipo/app/api/services/proposta_render.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo $marcador 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) { Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."; exit 1 }
    Bom "codigo novo no servidor"
}

}  # fim do if (-not $SoPypdf)

Titulo "5. pypdf na EC2"
if ($Simular) {
    Aviso "simulacao: nao vou instalar nada"
} else {
    if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
    & scp -i $Chave (Join-Path $Pasta "infra\instalar-pypdf.sh") "${alvo}:/tmp/instalar-pypdf.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do instalador falhou. Se for o IP: .\ops\utilitarios\liberar-meu-ip-ssh.ps1" }
    & ssh -t -i $Chave $alvo "bash /tmp/instalar-pypdf.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o instalador do pypdf falhou -- ver a saida acima. O HIPO segue funcionando, so sem o PDF rapido." }
    Bom "pypdf instalado e API reiniciada"
}

Titulo "Pronto"
Write-Host @"
  1. Espere ~15 s depois do passo 5: a API monta o PDF dos slides fixos
     na subida. Para conferir:
       ssh -i $Chave $alvo "sudo journalctl -u hipo-api -n 80 --no-pager | grep 'cache do PDF'"
  2. Ctrl+Shift+R. Gere uma proposta: o visualizador deve abrir em ~3-5 s.
     Feche e abra de novo: imediato (cache).
  3. Propostas antigas: a primeira abertura de cada uma ainda leva ~3-5 s;
     da segunda em diante, imediato.
"@ -ForegroundColor White
