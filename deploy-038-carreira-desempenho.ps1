# =====================================================================
#  HIPO -- deploy 038: Carreira (Universidade + PDI + Desempenho)
# =====================================================================
#
#  Etapa 1 da Carreira. Sem migration e sem carga:
#    - o modulo Universidade passa a se chamar Carreira no menu, com 3
#      abas: Universidade (a UC de hoje), PDI (em breve) e Desempenho
#    - Desempenho: metas da RPeR (Monitor) x realizado da pessoa, no mes
#      atual (meta de hoje, como o Monitor) e nos meses anteriores;
#      ponto de atencao, funil com taxas de conversao e historico de
#      6 meses. Gestao escolhe a pessoa e ve em modo leitura.
#    - GET /api/carreira/desempenho (router novo, modulo crm)
#
#    1. pre-voo      -- arquivos no lugar, base do git
#    2. testes       -- testes puros do Desempenho (o CI roda o resto)
#    3. push         -- SO os arquivos da entrega
#    4. espera       -- ate /api/carreira/desempenho existir no ar
#
#  USO
#     .\deploy-038-carreira-desempenho.ps1 -Simular
#     .\deploy-038-carreira-desempenho.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Site     = "https://hipogestao.com.br",
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

# Commit sobre o qual a entrega foi feita (entrega 037 no ar).
$base = "f53d70b"

$substituidos = @(
    "api\main.py",
    "api\services\rper_dados.py",
    "web\src\App.jsx",
    "web\src\components\Layout.jsx",
    "web\src\pages\uc\MinhaUC.jsx",
    "web\src\pages\uc\Estudio.jsx",
    "web\src\tests\Layout.test.jsx",
    "web\src\tests\MinhaUC.test.jsx"
)

$novos = @(
    "api\routers\carreira.py",
    "api\services\desempenho.py",
    "api\tests\test_carreira.py",
    "api\tests\test_desempenho_regras.py",
    "web\src\components\carreira\AbasCarreira.jsx",
    "web\src\pages\carreira\Desempenho.jsx",
    "web\src\pages\carreira\Pdi.jsx",
    "web\src\tests\DesempenhoCarreira.test.jsx",
    "deploy-038-carreira-desempenho.ps1"
)

$entrega = $substituidos + $novos

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta
Bom "pasta: $Pasta"

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega conferidos"

& git cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
& git merge-base --is-ancestor $base HEAD
if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
Bom "base: $base esta no HEAD"
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

# =====================================================================
# 2. Testes puros
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            Passo "pytest (regras do Desempenho)..."
            & python -m pytest -q --no-cov tests\test_desempenho_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes das regras do Desempenho falharam." }
            Bom "regras verdes (os testes com banco ficam com o CI)"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(carreira): modulo Carreira com Universidade, PDI e Desempenho

- Menu: Universidade vira Carreira, com 3 abas (Universidade, PDI,
  Desempenho). /uc continua funcionando e acende o item Carreira.
- Desempenho: metas da RPeR x realizado da pessoa. Mes aberto compara
  com a meta de hoje (dias uteis, como o Monitor); mes fechado com a
  meta do mes. Ponto de atencao com atalho para agir, funil com taxas
  de conversao por squad e historico de 6 meses.
- Gestao escolhe a pessoa (SDR, EV, EC) e ve em modo leitura.
- PDI: aba "em breve" (proxima entrega).
- rper_dados.coletar_janela: mesma coleta sobre qualquer janela.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 038 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-038.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, so acompanhe o Actions." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 4. Espera o codigo novo (pela URL publica, sem SSH)
# =====================================================================

Titulo "4. Esperando o CI"

# Antes do deploy a rota nao existe (404). Depois, sem token, ela
# responde 401/403 -- o sinal de que a API nova subiu.
function StatusDaRota {
    try {
        $r = Invoke-WebRequest -Uri "$Site/api/carreira/desempenho" -UseBasicParsing -TimeoutSec 15
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

if ($Simular) {
    Passo "status atual da rota: $(StatusDaRota) (404 = ainda nao subiu)"
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        $s = StatusDaRota
        if ($s -eq 401 -or $s -eq 403) { $chegou = $true; break }
        Write-Host "     ainda nao (HTTP $s, $([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "a rota nao apareceu em $EsperaMax s. Olhe o Actions (3 jobs verdes?)."
        exit 1
    }
    Bom "API nova no ar"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador. NAO precisa relogar (sem permissao nova).
  2. O item do menu agora e "Carreira"; abre na aba Universidade.
  3. Aba Desempenho como SDR, EV ou EC: o mes atual com a meta de hoje.
     Sem meta cadastrada, a tela avisa: Monitor > RPeR > Metas.
  4. Como Franqueado/ADM: o seletor "Pessoa" troca o colaborador.
"@ -ForegroundColor White
