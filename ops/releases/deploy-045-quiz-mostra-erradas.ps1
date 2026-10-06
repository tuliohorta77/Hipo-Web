# =====================================================================
#  HIPO -- deploy 045: quiz final mostra as perguntas erradas
# =====================================================================
#
#  Sem migration, sem carga:
#    O resultado do quiz final passa a mostrar o enunciado de cada
#    pergunta errada e a alternativa que a pessoa marcou (riscada),
#    agrupadas por aula. A resposta certa continua sem ir para a tela.
#    A correcao grava o texto como estava na hora; tentativas antigas
#    sao completadas na leitura pelo sorteio e respostas gravados.
#    Vale tambem para o aprovado com 1 erro e para a gestao (leitura).
#
#    1. pre-voo -- arquivos no lugar, base do git
#    2. testes  -- vitest do quiz (o CI roda o resto)
#    3. push    -- SO os arquivos da entrega
#
#  USO
#     .\deploy-045-quiz-mostra-erradas.ps1 -Simular
#     .\deploy-045-quiz-mostra-erradas.ps1
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

# Commit sobre o qual a entrega foi feita (entrega 044 no ar).
$base = "ec8ddc1"

$substituidos = @(
    "api\routers\uc.py",
    "api\tests\test_uc_quiz.py",
    "web\src\pages\uc\QuizTrilha.jsx",
    "web\src\tests\QuizTrilha.test.jsx"
)
$novos = @("deploy-045-quiz-mostra-erradas.ps1")
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
# 2. Testes
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if ($npx -and (Test-Path (Join-Path $Pasta "web\node_modules"))) {
        Push-Location (Join-Path $Pasta "web")
        try {
            Passo "vitest (quiz final)..."
            & npx vitest run src/tests/QuizTrilha.test.jsx
            if ($LASTEXITCODE -ne 0) { Abortar "testes do quiz falharam." }
            Bom "quiz verde"
        } finally { Pop-Location }
    } else {
        Aviso "npx ou web\node_modules ausente -- os testes ficam so com o CI"
    }
    Aviso "os testes de backend (test_uc_quiz.py) precisam de Postgres: rodam no CI"
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(uc): quiz final mostra as perguntas erradas, sem o gabarito

- O resultado lista, por aula, o enunciado de cada pergunta errada e a
  alternativa marcada (riscada). A certa nunca vai para a tela.
- A correcao grava enunciado e sua_resposta como estavam na hora;
  tentativas antigas sao completadas na leitura pelo sorteio gravado
  (pergunta apagada do banco: fica so o numero).
- Aparece tambem no aprovado com erro e no modo leitura da gestao.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 045 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-045.txt"
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
  1. Acompanhe o Actions: Backend Tests + Frontend Tests + Deploy verdes.
  2. Depois do deploy: Ctrl+Shift+R (ou fechar e abrir a aba). Sem relogar.
  3. Quem ja reprovou ve as erradas da ultima tentativa na hora,
     inclusive as feitas antes desta entrega.
"@ -ForegroundColor White
