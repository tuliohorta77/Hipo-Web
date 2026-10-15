# HIPO - Entrega 059: venda reaberta sai do Monitor.
#  - NMRR, contratos e ticket medio (painel e drawer) ignoram o ganho que foi
#    desfeito depois por uma reabertura (evento de status saindo de
#    'conquistado'); so conta oportunidade com status atual 'conquistado';
#  - reaberta e ganha de novo conta uma vez, pela data do novo ganho;
#  - mesma regra nas vendas do RPER (services/rper_dados.py);
#  - 3 testes novos em test_monitor.py;
#  - sem migration.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-059-nmrr-reaberta.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-059-nmrr-reaberta.ps1 -Simular

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$novos = @(
  "deploy-059-nmrr-reaberta.ps1"
)

# Versao de cada arquivo no HEAD em que a 059 foi feita.
$base = [ordered]@{
  "api/routers/monitor.py"     = "d80625483aeacb926873b12aa204e40c57e6aac4"
  "api/services/rper_dados.py" = "89baf0f9d1dcf53757d9674fcf127e02f794caff"
  "api/tests/test_monitor.py"  = "792432e3b36be6367ec3e0223046e6add5582838"
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
      Write-Host "  AVISO (forcado): $f no HEAD difere da base da 059" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base da 059 (outra entrega mexeu nele?)." -ForegroundColor Red
      $ok = $false
    }
  }
}
$alterado = git diff --name-only -- $base.Keys
if (-not $alterado) {
  Write-Host "  Nenhum dos 3 arquivos mudou em relacao ao HEAD: a 059 ja foi commitada ou os arquivos nao foram salvos." -ForegroundColor Red
  $ok = $false
}
if (-not $ok) {
  Write-Host ""
  Write-Host "Pre-voo falhou. Nada foi feito. Fale comigo com a saida acima." -ForegroundColor Red
}

if ($ok) {
  $py = "api\venv\Scripts\python.exe"
  if (Test-Path $py) {
    Write-Host ""
    Write-Host "== Pytest (sintaxe dos arquivos alterados) ==" -ForegroundColor Cyan
    & $py -m py_compile api/routers/monitor.py api/services/rper_dados.py api/tests/test_monitor.py
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Arquivo com erro de sintaxe. Nada foi commitado." -ForegroundColor Red
      $ok = $false
    } else {
      Write-Host "  ok (os testes de banco rodam no CI)"
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
  git commit -m "Monitor: venda reaberta deixa de contar no NMRR, contratos, ticket medio e RPER" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. Sem migration." -ForegroundColor Green
  Write-Host "Conferir depois: Monitor -> NMRR de outubro sem a HPS (R$ 1.350), 3 contratos." -ForegroundColor Green
}
