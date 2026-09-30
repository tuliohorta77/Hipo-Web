# =====================================================================
#  HIPO -- deploy 025: botao "Filtros" na tela de Oportunidades
# =====================================================================
#
#  O QUE MUDA
#    - Barra do funil ganha UM botao "Filtros" (selo com quantos estao
#      ativos) que abre um painel com os filtros do Relatorios:
#      situacao, fase, periodo (criacao / previsao / desfecho / ultima
#      atualizacao), temperatura, mensalidade, equipe (pessoa + papel),
#      origem, vertical e indicacao de parceiro.
#    - Os selects soltos de Envolvido e Fase sairam da barra (foram pro
#      painel). A busca continua na barra.
#    - Os MESMOS filtros valem no kanban, na tabela, no funil e nos KPIs.
#      No kanban, filtro de fase/situacao mostra so as colunas do recorte;
#      com periodo, a coluna Finalizado larga o "mes corrente".
#    - KPI "Em aberto" vira filtro de situacao (ativa + suspensa) e passa
#      a valer tambem no kanban.
#    - api.js: listas vao repetidas na query (fase=a&fase=b).
#
#  SEM MIGRATION E SEM SSH: o CI faz o rsync e reinicia sozinho.
#  SEM RELOGIN: nenhuma permissao mudou.
#
#  O QUE ESTE SCRIPT FAZ
#    1. pre-voo  -- arquivos no lugar
#    2. testes   -- vitest e build do front
#    3. push     -- SO os arquivos da entrega
#
#  USO
#     .\deploy-025-filtros-oportunidades.ps1 -Simular
#     .\deploy-025-filtros-oportunidades.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [string]$Pasta = (Get-Location).Path
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

$entrega = @(
    "api\routers\crm_oportunidades.py",
    "api\tests\test_crm_oportunidades.py",
    "web\src\api.js",
    "web\src\components\crm\FiltrosOportunidades.jsx",
    "web\src\pages\crm\Oportunidades.jsx",
    "web\src\tests\FiltrosOportunidades.test.jsx",
    "web\src\tests\Oportunidades.test.jsx",
    "deploy-025-filtros-oportunidades.ps1"
)

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

$marca = Select-String -Path (Join-Path $Pasta "api\routers\crm_oportunidades.py") -Pattern "def filtros_funil" -Quiet
if (-not $marca) { Abortar "crm_oportunidades.py nao e a versao nova (filtros do funil)." }
$marca = Select-String -Path (Join-Path $Pasta "web\src\api.js") -Pattern "indexes: null" -Quiet
if (-not $marca) { Abortar "api.js nao e a versao nova (paramsSerializer)." }
Bom "versoes novas no lugar"

# =====================================================================
# 2. Testes do front
# =====================================================================

Titulo "2. Testes do front"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    Push-Location (Join-Path $Pasta "web")
    try {
        Passo "vitest..."
        & npm.cmd run test -- --run
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Corrija antes de subir." }
        Bom "vitest verde"
        Passo "vite build..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Abortar "o build do front falhou." }
        Bom "build ok"
    } finally { Pop-Location }
}

# =====================================================================
# 3. Push -- so a entrega
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(oportunidades): botao Filtros com os filtros do Relatorios

Situacao, fase, periodo (criacao/previsao/desfecho/atualizacao),
temperatura, mensalidade, equipe (pessoa + papel), origem, vertical e
indicacao de parceiro, num painel atras de um botao so. Rascunho +
Aplicar: a tela so busca ao aplicar.

Backend: dependencia unica filtros_funil para resumo, kanban, coluna e
listagem. Kanban devolve so as colunas do recorte de fase/situacao; com
periodo, a Finalizado larga o mes corrente. KPI Em aberto vira filtro
de situacao. api.js serializa listas repetidas (fase=a&fase=b).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017b55ymqyHeMEjs2emNbsHk
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Write-Host "  Vai no commit (e SO isto):" -ForegroundColor DarkGray
    & git status --short -- $entrega
    Confirmar "Commitar os arquivos da entrega e dar push na main?"

    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-025.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"

    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

Titulo "Pronto"
Write-Host @"
  1. Espere os 3 jobs ficarem verdes no Actions (~8 min com o backend).
  2. Ctrl+Shift+R na tela de Oportunidades (front novo). Nao precisa
     relogar: nenhuma permissao mudou.
  3. Conferir: botao Filtros -> Situacao "Perdida" + periodo "Mes passado"
     (data: Desfecho) -> o kanban mostra so a coluna Finalizado com as
     perdidas do mes passado.
"@ -ForegroundColor White
