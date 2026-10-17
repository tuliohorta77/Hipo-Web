# HIPO - Entrega 060b: tela Contratos mais compacta.
#  - resumo do mes em KPIs de barra (40px) na mesma linha do mes e da
#    proxima acao, no lugar dos 4 cards grandes;
#  - lista com altura da tela, rolagem propria e cabecalho preso; linhas
#    mais baixas; "1o mes", "pago" e botao sem quebrar linha;
#  - cabecalhos com o nome da coluna (Mensalidade, % repasse, Repasse,
#    Imposto, Liquido Spectre) no lugar das letras da planilha (K, L, N, O);
#  - nota para a Controller e historico compactos na lateral;
#  - sem migration, sem mudanca de API.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-060b-contratos-compacto.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\deploy-060b-contratos-compacto.ps1

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$arquivos = @(
  "web/src/pages/contratos/Contratos.jsx",
  "deploy-060b-contratos-compacto.ps1"
)
$baseTela = "972455cbb8f41bf5d619e748f01f141ecb1265da"

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
& cmd /c "git rev-parse HEAD:web/src/pages/contratos/Contratos.jsx > ""%TEMP%\hipo-060b.txt"" 2>nul"
$head = (Get-Content "$env:TEMP\hipo-060b.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($head -ne $baseTela) {
  if ($Forcar) {
    Write-Host "  AVISO (forcado): Contratos.jsx no HEAD difere da 060" -ForegroundColor Yellow
  } else {
    Write-Host "  Contratos.jsx no HEAD difere da 060 (a 060 foi commitada?)." -ForegroundColor Red
    $ok = $false
  }
}

if ($ok) {
  Write-Host ""
  Write-Host "== Vitest + build ==" -ForegroundColor Cyan
  Push-Location web
  npx vitest run src/tests/Contratos.test.jsx
  $r = $LASTEXITCODE
  if ($r -eq 0) { npx vite build; $r = $LASTEXITCODE }
  Pop-Location
  if ($r -ne 0) { Write-Host "Vitest/build falhou. Nada foi commitado." -ForegroundColor Red; $ok = $false }
}

if (-not $ok) {
  Write-Host ""
  Write-Host "Nada foi feito. Mande a saida acima." -ForegroundColor Red
} elseif ($Simular) {
  Write-Host ""
  Write-Host "Simulacao OK. Rode sem -Simular para commitar e subir." -ForegroundColor Green
} else {
  git add -- $arquivos
  git commit -m "Contratos: resumo do mes em barra, lista com rolagem propria e cabecalhos com nome da coluna" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. Depois: Ctrl+Shift+R na tela Contratos." -ForegroundColor Green
}
