# HIPO - Entrega 058: vencimento do contrato.
#  - o 1o vencimento passa a ser 30 dias depois da emissao do contrato; os
#    demais caem no mesmo dia dos meses seguintes (antes: todo dia 10 fixo);
#  - Clausula 5: "com o primeiro vencimento em 14 de novembro de 2026 e os
#    demais todo dia 14 de cada mes"; dia 29/30/31 ganha a regra do ultimo
#    dia do mes;
#  - formulario: campo "1o vencimento" (data), calculado sozinho a partir da
#    data do contrato e editavel;
#  - modelo contrato_modelo.docx regerado;
#  - migration 041 (aditiva; troca a CHECK do dia), aplicada pelo deploy do CI.
#  - contratos ja enviados nao mudam.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-058-contrato-vencimento.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-058-contrato-vencimento.ps1 -Simular

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "api/migrations/041_contrato_primeiro_vencimento.sql",
  "deploy-058-contrato-vencimento.ps1"
)

# Versao de cada arquivo no commit d72e9aa.
$base = [ordered]@{
  "api/routers/crm_contratos.py"             = "cfed363db6a3731cfb3fc1c887a031d7685dd046"
  "api/schema.sql"                           = "9aaeea1b341b554cf59a5e2dbcd5efe7de899583"
  "api/scripts/ensaiar_contrato.py"          = "6280478002c041fc6385affdfd15a5dc2c9e3be5"
  "api/scripts/gerar_modelo_contrato.py"     = "1a8d55794c743ed1f773ce660d38d03f764b577c"
  "api/services/contrato.py"                 = "0edc98bb8a496ea2801ad4dd8f9e6c6181375125"
  "api/templates/contrato_modelo.docx"       = "e2f616f7bc4b2dcf0c2deb869f9c4df43bdcd1fc"
  "api/tests/test_contrato_regras.py"        = "d5081f298a3a380dc38165fe8471370495674722"
  "api/tests/test_contrato_render.py"        = "7a585a20878672379bd9cf7e322fd851acaa4a9a"
  "api/tests/test_crm_contratos.py"          = "7ab2d0077105115b9e8e29fecbaccf25a89d13b7"
  "web/src/components/crm/AbaContrato.jsx"   = "d7fa4bead09918c2f165b157fa86dd349b511e5f"
  "web/src/tests/AbaContrato.test.jsx"       = "ec6b402408c5153ccfd45fd463a29c58ef146c6b"
}
$arquivos = $novos + @($base.Keys)
Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "041_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 041 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere da base da 058" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base da 058 (outra entrega mexeu nele?)." -ForegroundColor Red
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
    Write-Host "== Pytest (regras e modelo do contrato, sem banco) ==" -ForegroundColor Cyan
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
  git commit -m "Contrato: primeiro vencimento 30 dias apos a emissao, depois mensal no mesmo dia (migration 041)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. O deploy aplica a migration 041 sozinho." -ForegroundColor Green
  Write-Host "Conferir depois: Novo contrato -> campo 1o vencimento = data + 30 dias; previa mostra a Clausula 5 nova." -ForegroundColor Green
}
