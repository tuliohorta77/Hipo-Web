# HIPO - Entrega 057: nova ordem de assinatura do contrato.
#  1) Contratada (o CEO da Controller)
#  2) Testemunha da contratada (o vendedor)
#  3) Contratante (o cliente)
#  4) Testemunha da contratante
#  - so muda a ordem da fila na Autentique e a ordem do formulario;
#  - o carimbo continua no lugar certo do PDF (vem do rotulo da linha);
#  - contratos ja enviados seguem na ordem em que foram enviados;
#  - sem migration.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-057-contrato-ordem.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-057-contrato-ordem.ps1 -Simular

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "deploy-057-contrato-ordem.ps1"
)

# Versao de cada arquivo no commit 9ac9ee7.
$base = [ordered]@{
  "api/services/contrato.py"               = "6fe0d96a4bcdfd41501c28c0e01f6aabeedbd7b7"
  "api/tests/test_crm_contratos.py"        = "5bfc9eb18a878fe668c4d950f16d190efb19aa25"
  "web/src/components/crm/AbaContrato.jsx" = "0231420a27b8367479aa987e63d13b2ac0ef3104"
  "web/src/tests/AbaContrato.test.jsx"     = "485f43fe3caab9fd48202e8e7e9c265100d87f8c"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere da base da 057" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base da 057 (outra entrega mexeu nele?)." -ForegroundColor Red
      $ok = $false
    }
  }
}
if (-not $ok) {
  Write-Host ""
  Write-Host "Pre-voo falhou. Nada foi feito. Fale comigo com a saida acima." -ForegroundColor Red
}

if ($ok) {
  Write-Host ""
  Write-Host "== Vitest (Contrato) ==" -ForegroundColor Cyan
  Push-Location web
  npx vitest run src/tests/AbaContrato.test.jsx
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
    Write-Host "== Pytest (regras do contrato, sem banco) ==" -ForegroundColor Cyan
    Push-Location api
    $env:PYTHONPATH = (Get-Location).Path
    & "..\$py" -m pytest -q -p no:cacheprovider --no-cov tests/test_contrato_regras.py tests/test_contrato_render.py
    $pyt = $LASTEXITCODE
    Pop-Location
    if ($pyt -ne 0) {
      Write-Host "Pytest falhou. Nada foi commitado." -ForegroundColor Red
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
  git commit -m "Contrato: Controller assina primeiro (CEO, testemunha da Controller, contratante, testemunha da contratante)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI." -ForegroundColor Green
  Write-Host "Conferir depois: novo contrato -> o primeiro e-mail da Autentique vai para o Marcelo." -ForegroundColor Green
}
