# HIPO - Carreira > Roleplay com IA (RP-2.1: ajustes do teste de 07/10).
#  - cliente nao abre mais como atendente ("com o que posso te ajudar?");
#  - vigia de "cliente sem resposta": 9 s sem resposta -> reconecta e pede
#    para repetir a frase; deteccao de fala do Gemini menos sensivel a ruido;
#  - diario da conexao de cada treino (a gestao ve no resultado).
# Migration 036 (aditiva) e aplicada sozinha pelo deploy do CI.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2b.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2b.ps1 -Simular   (so confere e testa)
#   powershell -ExecutionPolicy Bypass -File .\deploy-roleplay-rp2b.ps1 -Forcar    (pula a trava dos arquivos compartilhados)

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "api/migrations/036_roleplay_eventos.sql",
  "deploy-roleplay-rp2b.ps1"
)

# Arquivos que esta entrega altera: a versao no HEAD precisa ser a do RP-2.
# Se nao for, o HEAD andou (ou ha outra entrega por commitar) e sobrescrever
# perderia mudanca.
$base = [ordered]@{
  "api/routers/roleplay.py"                     = "ec2ac79a8d0ca7703698c8f00f67e5cdc100f3ed"
  "api/services/roleplay.py"                    = "3c3bb5a9aae9d17cc31f9871c05fa7a6cbf300b4"
  "api/services/roleplay_cenarios.py"           = "9d7036710698f948fb22227ca8dc850178962cdb"
  "api/schema.sql"                              = "bbda14b5d9ce467a9502fa930a3e54f37ea2501b"
  "api/tests/test_roleplay.py"                  = "60da346754c8a1f12f234d12e4bfc1f4a7fb678d"
  "api/tests/test_roleplay_regras.py"           = "b1eff6c583bc1d72958904f04a57cb5441e2f561"
  "web/src/components/carreira/vozRealtime.js"  = "e8d3c41991570212de891553a52e2f4aa79bf505"
  "web/src/components/carreira/audioRoleplay.js" = "06b00baf48938dccf69b94def058ef397d6a7c7c"
  "web/src/pages/carreira/RoleplaySessao.jsx"   = "0b52e81e45a8363accedebfa9e7385889187e0aa"
  "web/src/tests/RoleplayCarreira.test.jsx"     = "cb29a8272763521ec43e4d9ace5034a9e4e6129b"
  "web/src/tests/vozRealtime.test.js"           = "8f7d6a1f1abdecc0820e6a956b1ed78e2fc5fd0a"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "036_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 036 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere do RP-2" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere do RP-2 (outra entrega mexeu nele?)." -ForegroundColor Red
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
  git commit -m "Carreira/Roleplay (RP-2.1): cliente nao abre como atendente, vigia de cliente sem resposta, VAD menos sensivel a ruido, diario da conexao (migration 036)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI (Backend, Frontend, Deploy)." -ForegroundColor Green
  Write-Host "O deploy aplica a migration 036 sozinho." -ForegroundColor Green
  Write-Host ""
  Write-Host "DEPOIS DO CI VERDE, conferir que o Google aceita o token com a nova deteccao de fala:" -ForegroundColor Cyan
  Write-Host '  ssh -i $HOME\Downloads\chave-hipo.pem ec2-user@35.156.111.168 "sudo bash -c ''cd /home/hipo/app/api && python3 -m scripts.roleplay_diagnostico''"'
  Write-Host "Tem que terminar em OK. Se der erro 400, me mande a saida." -ForegroundColor Cyan
  Write-Host ""
  Write-Host "Depois: hipogestao.com.br > Carreira > Roleplay (Ctrl+Shift+R). Use fone de ouvido." -ForegroundColor Green
}
