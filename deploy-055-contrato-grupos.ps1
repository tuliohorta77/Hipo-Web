# HIPO - Entrega 055: contrato por empresa (raiz de CNPJ), Anexo 1,
# substituicao e servicos marcaveis.
#  - matriz e filiais (mesmos 8 primeiros digitos) saem no MESMO contrato:
#    a matriz qualifica a contratante e as demais vao no Anexo 1;
#  - raizes diferentes = um contrato para cada empresa, sempre;
#  - CNPJ novo depois de assinado: contrato novo com todos os CNPJs da raiz,
#    que SUBSTITUI o anterior quando for assinado (sem aditivo);
#  - servicos extras (PPP, ergonomia, LTCAT de insalubridade etc.) viram
#    itens marcaveis na clausula 2, ja pre-marcados pelo escopo da proposta;
#  - modelo contrato_modelo.docx regerado (novos campos);
#  - migration 039 (aditiva; so troca um indice), aplicada pelo deploy do CI.
#
# PRE-REQUISITO: a entrega 054 ja precisa estar commitada (migration 038).
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-055-contrato-grupos.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-055-contrato-grupos.ps1 -Simular

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "api/migrations/039_contrato_grupo_cnpj.sql",
  "deploy-055-contrato-grupos.ps1"
)

# Versao de cada arquivo na entrega 054.
$base = [ordered]@{
  "api/services/contrato.py"               = "e5948c3f88c5ef57a0caae8b629734a271687a93"
  "api/routers/crm_contratos.py"           = "d0df8016120734ab5d0d077e2f5613c30ea3eae2"
  "api/scripts/gerar_modelo_contrato.py"   = "8eb8c0af98730f3dfefb9e5ac6fc7fd1666c0fe8"
  "api/templates/contrato_modelo.docx"     = "5dcc8d74efceed71368780a40ce150cb5f1cc9ee"
  "api/schema.sql"                         = "86b7e34f2b334329743936abf49ea8f9578521eb"
  "api/tests/test_crm_contratos.py"        = "4c571e69071077dc57d4083f580b46ecfd8a0afb"
  "api/tests/test_contrato_regras.py"      = "4525c823429da09f8ebd938cca9fca3ad423987d"
  "api/tests/test_contrato_render.py"      = "93a05d4b02f7042a07e54bd7e373a916e2bc9b65"
  "web/src/components/crm/AbaContrato.jsx" = "95f7404dcd1f6d8f1537889c05865c890503cc5c"
  "web/src/tests/AbaContrato.test.jsx"     = "e3e8de10f56e92e25ab32c731bd002bd68e65f33"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
$m38 = (git rev-parse "HEAD:api/migrations/038_contrato_aviso.sql" 2>$null)
if (-not $m38) {
  Write-Host "  A entrega 054 (migration 038) ainda nao foi commitada." -ForegroundColor Red
  Write-Host "  Rode antes: .\deploy-054-aviso-contrato.ps1" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "039_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 039 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
if ($m38) {
  foreach ($f in $base.Keys) {
    $head = (git rev-parse "HEAD:$f" 2>$null)
    if ($head -ne $base[$f]) {
      if ($Forcar) {
        Write-Host "  AVISO (forcado): $f no HEAD difere da base da 055" -ForegroundColor Yellow
      } else {
        Write-Host "  $f no HEAD difere da base da 055 (outra entrega mexeu nele?)." -ForegroundColor Red
        $ok = $false
      }
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
  git commit -m "Contrato por empresa (raiz de CNPJ) com Anexo 1, substituicao por contrato novo e servicos marcaveis (migration 039)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. O deploy aplica a migration 039 sozinho." -ForegroundColor Green
  Write-Host "Conferir depois: proposta com matriz + filial -> aba Contrato -> previa com Anexo 1." -ForegroundColor Green
}
