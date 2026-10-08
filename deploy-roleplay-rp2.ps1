# HIPO - Carreira > Roleplay com IA (RP-2: nota contra o Roteiro de Vendas).
# Tambem: custo da IA visivel so para o Franqueado.
# Migration 035 (aditiva) e aplicada sozinha pelo deploy do CI.
# Nao precisa de chave nova: a nota usa a mesma IA do scorecard das reunioes.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2.ps1 -Simular   (so confere e testa)
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2.ps1 -Forcar    (pula a trava dos arquivos compartilhados)

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "api/migrations/035_roleplay_avaliacao.sql",
  "api/services/roleplay_avaliacao.py",
  "web/src/components/carreira/AvaliacaoRoleplay.jsx",
  "deploy-roleplay-rp2.ps1"
)

# Arquivos que esta entrega altera: a versao no HEAD precisa ser a do RP-1.
# Se nao for, o HEAD andou (ou ha outra entrega por commitar) e sobrescrever
# perderia mudanca.
$base = [ordered]@{
  "api/routers/roleplay.py"                   = "e1f83f8d30e4f2540644dcdf27000a6a218cd450"
  "api/services/roleplay.py"                  = "cc55ca9ce759c9f9f9bc852cd7bd3b540ef81900"
  "api/services/roleplay_cenarios.py"         = "e0a107a9697456e6cbbae5d94db113d1391e2c7d"
  "api/services/atividade.py"                 = "26ec615fa1209bfb463c6b60d455ccddfa5b8824"
  "api/schema.sql"                            = "8f8efe78ded55f2b3f3aff2503ac4e5b83902281"
  "api/tests/test_roleplay.py"                = "2a3bbc3be51951c23b8c3dc38c6a2a30094812b2"
  "api/tests/test_roleplay_regras.py"         = "e70d0371fee042667f46cae9b5c220c999e552df"
  "web/src/pages/carreira/Roleplay.jsx"       = "a25ae07189aaa35b1f2d78afba43c4382729ae6e"
  "web/src/pages/carreira/RoleplaySessao.jsx" = "43ad2de41b6bb01ee57a6b7f9de6c9d8900a44dc"
  "web/src/tests/RoleplayCarreira.test.jsx"   = "7782e1b69115cddeeb63453661162660e0eb31f5"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "035_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 035 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere do RP-1" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere do RP-1 (o RP-1 foi commitado? outra entrega mexeu nele?)." -ForegroundColor Red
      $ok = $false
    }
  }
}
if (-not $ok) {
  Write-Host ""
  Write-Host "Pre-voo falhou. Nada foi feito. Fale comigo com a saida acima." -ForegroundColor Red
}

if ($ok) {
  $outros = git status --porcelain | Where-Object {
    $caminho = $_.Substring(3).Trim('"').Replace('\', '/')
    -not ($arquivos -contains $caminho)
  }
  if ($outros) {
    Write-Host ""
    Write-Host "Atencao: ha outras mudancas na pasta (nao entram neste commit):" -ForegroundColor Yellow
    $outros | ForEach-Object { Write-Host "  $_" }
  }

  Write-Host ""
  Write-Host "== Vitest (Carreira) ==" -ForegroundColor Cyan
  Push-Location web
  npx vitest run src/tests/RoleplayCarreira.test.jsx src/tests/vozRealtime.test.js src/tests/MinhaUC.test.jsx src/tests/PdiCarreira.test.jsx src/tests/Layout.test.jsx
  $vitest = $LASTEXITCODE
  if ($vitest -eq 0) {
    Write-Host ""
    Write-Host "== Build ==" -ForegroundColor Cyan
    npx vite build
    $vitest = $LASTEXITCODE
  }
  Pop-Location
  if ($vitest -ne 0) {
    Write-Host "Vitest/build falhou. Nada foi commitado." -ForegroundColor Red
    $ok = $false
  }
}

if ($ok) {
  $py = "api\venv\Scripts\python.exe"
  if (Test-Path $py) {
    Write-Host ""
    Write-Host "== Pytest (regras do Roleplay, sem banco) ==" -ForegroundColor Cyan
    Push-Location api
    $env:PYTHONPATH = (Get-Location).Path
    & "..\$py" -m pytest -q -p no:cacheprovider --no-cov tests/test_roleplay_regras.py
    $pyt = $LASTEXITCODE
    Pop-Location
    if ($pyt -ne 0) {
      Write-Host "Pytest das regras falhou. Nada foi commitado." -ForegroundColor Red
      $ok = $false
    }
  } else {
    Write-Host "(api\venv nao encontrado: os testes do backend rodam so no CI)" -ForegroundColor Yellow
  }
}

if ($ok -and $Simular) {
  Write-Host ""
  Write-Host "Simulacao OK. Rode sem -Simular para commitar e subir." -ForegroundColor Green
} elseif ($ok) {
  git add -- $arquivos
  git commit -m "Carreira/Roleplay (RP-2): nota contra o Roteiro de Vendas, ajuste e validacao da gestao; custo da IA so para o Franqueado (migration 035)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI (Backend, Frontend, Deploy)." -ForegroundColor Green
  Write-Host "O deploy aplica a migration 035 sozinho. Nao ha passo manual." -ForegroundColor Green
  Write-Host ""
  Write-Host "Depois: hipogestao.com.br > Carreira > Roleplay (Ctrl+Shift+R)." -ForegroundColor Green
  Write-Host "Treinos feitos antes do RP-2 nao tem nota: abra o treino e clique em 'Avaliar de novo' (como Franqueado)." -ForegroundColor Green
}
