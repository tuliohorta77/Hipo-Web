# HIPO - Entrega 060b: tela Contratos mais compacta.
#  - resumo do mes em KPIs de barra (40px) na mesma linha do mes e da
#    proxima acao, no lugar dos 4 cards grandes;
#  - lista com altura da tela, rolagem propria e cabecalho preso; linhas
#    mais baixas; "1o mes", "pago" e botao sem quebrar linha;
#  - cabecalhos com o nome da coluna (Mensalidade, % repasse, Repasse,
#    Imposto, Liquido Spectre) no lugar das letras da planilha (K, L, N, O);
#  - nota para a Controller e historico compactos na lateral;
#  - sem o titulo "Contratos"; filtros na mesma linha do mes; uma linha so
#    antes da tabela; somas de cada coluna no cabecalho (no lugar dos KPIs);
#  - sem migration, sem mudanca de API.
#  - abas, mes, filtros e proxima acao numa linha so; somas do cabecalho
#    contam lancado + sugestao (a nota da lateral segue so com lancados);
#  Serve tanto antes quanto depois do primeiro push da 060b.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-060b-contratos-compacto.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\deploy-060b-contratos-compacto.ps1

param([switch]$Simular, [switch]$Forcar)

$ErrorActionPreference = "Stop"
$ok = $true

$arquivos = @(
  "web/src/pages/contratos/Contratos.jsx",
  "web/src/tests/Contratos.test.jsx",
  "deploy-060b-contratos-compacto.ps1"
)
$basesTela = @("972455cbb8f41bf5d619e748f01f141ecb1265da", "b36ca89f46f52792fe4930946cdcc88edf18b82a", "2ad1c9413a1a93b59a6ccdbbc0f995cac134275a")

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
& cmd /c "git rev-parse HEAD:web/src/pages/contratos/Contratos.jsx > ""%TEMP%\hipo-060b.txt"" 2>nul"
$head = (Get-Content "$env:TEMP\hipo-060b.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($basesTela -notcontains $head) {
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
  git commit -m "Contratos: abas, mes e filtros numa linha; somas do cabecalho com sugestoes" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. Depois: Ctrl+Shift+R na tela Contratos." -ForegroundColor Green
}
