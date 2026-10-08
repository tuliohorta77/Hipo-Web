# HIPO - Carreira > Roleplay com IA (RP-1: sessao gravada).
# Migration 034 (aditiva) e aplicada sozinha pelo deploy do CI.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp1.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp1.ps1 -Simular   (so confere e testa)
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp1.ps1 -Forcar    (pula a trava dos arquivos compartilhados)
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp1.ps1 -TestarGemini -Simular
#       (pede a chave do Gemini e confere, daqui do Windows, que o Google aceita o token do HIPO)
#
# Depois do CI verde: por a chave do Gemini no .env (passo 2 no fim deste script).

param([switch]$Simular, [switch]$Forcar, [switch]$TestarGemini)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "api/migrations/034_roleplay.sql",
  "api/routers/roleplay.py",
  "api/services/roleplay.py",
  "api/services/roleplay_cenarios.py",
  "api/scripts/roleplay_diagnostico.py",
  "api/tests/test_roleplay.py",
  "api/tests/test_roleplay_regras.py",
  "web/src/components/carreira/vozRealtime.js",
  "web/src/components/carreira/audioRoleplay.js",
  "web/src/pages/carreira/Roleplay.jsx",
  "web/src/pages/carreira/RoleplaySessao.jsx",
  "web/src/tests/RoleplayCarreira.test.jsx",
  "web/src/tests/vozRealtime.test.js",
  "deploy-roleplay-rp1.ps1"
)

# Arquivos compartilhados: a versao no HEAD precisa ser a mesma sobre a qual
# esta entrega foi escrita. Se nao for, ha mudanca de OUTRA entrega por
# commitar (ou o HEAD andou) e o git add levaria junto.
$base = [ordered]@{
  "api/.env.template"                           = "f94a2327a855a5e3e648f916557dcbd6acb02175"
  "api/config.py"                               = "2c78ba864d9476ba18d42b89b853f866ab58eae6"
  "api/main.py"                                 = "db0cf0faec1d381e0b02a25469a08edf367bedba"
  "api/schema.sql"                              = "19bbe4a311a6ac8ed4c1a037e4ba60be238f8eef"
  "api/services/atividade.py"                   = "a33497d2b17777aa925a1b5db7fc206d4f8f678d"
  "web/src/App.jsx"                             = "24bba101fdeac80c2582efaa4e22fbc89a75397b"
  "web/src/components/carreira/AbasCarreira.jsx" = "34038a93774a03d4367b3b51125f44d9407d1bac"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $novos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "034_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 034 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere da base desta entrega" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base desta entrega (outra entrega mexeu nele)." -ForegroundColor Red
      $ok = $false
    }
  }
}
if (-not $ok -and -not $Forcar) {
  Write-Host ""
  Write-Host "Pre-voo falhou. Nada foi feito. Suba as outras entregas primeiro ou fale comigo." -ForegroundColor Red
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
  Write-Host "== Vitest (Roleplay) ==" -ForegroundColor Cyan
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
  # Testes puros do backend (sem Postgres): rodam no Windows se o venv existir.
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

if ($ok -and $TestarGemini) {
  $py = "api\venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    Write-Host "api\venv nao encontrado: nao da para testar o Gemini daqui." -ForegroundColor Red
    $ok = $false
  } else {
    Write-Host ""
    Write-Host "== Gemini: o Google aceita o token montado pelo HIPO? ==" -ForegroundColor Cyan
    Push-Location api
    $env:PYTHONPATH = (Get-Location).Path
    if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "postgresql://local/nada" }
    if (-not $env:JWT_SECRET) { $env:JWT_SECRET = "local-so-para-o-teste" }
    & "..\$py" -m scripts.roleplay_diagnostico
    $gem = $LASTEXITCODE
    Pop-Location
    if ($gem -ne 0) {
      Write-Host "O Google recusou. Nada foi commitado. Copie a saida acima e me mande." -ForegroundColor Red
      $ok = $false
    }
  }
}

if ($ok -and $Simular) {
  Write-Host ""
  Write-Host "Simulacao OK. Rode sem -Simular para commitar e subir." -ForegroundColor Green
} elseif ($ok) {
  git add -- $arquivos
  git commit -m "Carreira/Roleplay com IA (RP-1): sessao por voz com Gemini Live, gravacao e transcricao (migration 034)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI (Backend, Frontend, Deploy)." -ForegroundColor Green
  Write-Host "O deploy aplica a migration 034 sozinho." -ForegroundColor Green
  Write-Host ""
  Write-Host "PASSO 2, depois do CI verde (chave do Gemini no .env, digitada sem aparecer):" -ForegroundColor Cyan
  Write-Host '  scp -i $HOME\Downloads\chave-hipo.pem infra/por-chave-no-env.sh ec2-user@35.156.111.168:/tmp/'
  Write-Host '  ssh -t -i $HOME\Downloads\chave-hipo.pem ec2-user@35.156.111.168 bash /tmp/por-chave-no-env.sh GEMINI_API_KEY'
  Write-Host ""
  Write-Host "PASSO 3, conferir que o servidor fala com o Gemini:" -ForegroundColor Cyan
  Write-Host '  ssh -i $HOME\Downloads\chave-hipo.pem ec2-user@35.156.111.168 "sudo -u hipo bash -c ''cd /home/hipo/app/api && python3 -m scripts.roleplay_diagnostico''"'
  Write-Host ""
  Write-Host "Depois: hipogestao.com.br > Carreira > Roleplay (Ctrl+Shift+R). Use fone de ouvido." -ForegroundColor Green
}
