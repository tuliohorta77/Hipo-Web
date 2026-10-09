# HIPO - Entrega 054: aviso de contrato assinado.
#  - quando o ultimo assina, faturamento, contratos e ADM recebem um e-mail
#    com o PDF assinado e o resumo do negocio, saindo do Gmail do executivo
#    da proposta;
#  - a aba Contrato mostra se o aviso saiu (e para quem) e tem "Reenviar aviso";
#  - o timer de 30 min tenta de novo ate 5 vezes se o Gmail falhar;
#  - migration 038 (aditiva), aplicada sozinha pelo deploy do CI.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-054-aviso-contrato.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-054-aviso-contrato.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\deploy-054-aviso-contrato.ps1 -SoServidor
#       (depois do CI verde: grava a lista de destinatarios no .env)

param([switch]$Simular, [switch]$Forcar, [switch]$SoServidor)

$ErrorActionPreference = "Stop"
$ok = $true
$Chave = "$HOME\Downloads\chave-hipo.pem"
$Alvo = "ec2-user@35.156.111.168"

$novos = @(
  "api/migrations/038_contrato_aviso.sql",
  "deploy-054-aviso-contrato.ps1"
)

# Versao de cada arquivo no commit b0e759a (entrega 053).
$base = [ordered]@{
  "api/config.py"                          = "62678fa8f99c1d59999179d97b63a7fc3fde1dc7"
  "api/routers/crm_contratos.py"           = "8bc2d91273fdba8be2cc7490e0dec3ef2f1c8524"
  "api/routers/webhooks.py"                = "b94aee5c01050c22a99fb7fe89891a22f108ff35"
  "api/services/contrato.py"               = "ca11cc293bf92426e56244039d51d4f1269cfd88"
  "api/services/atividade.py"              = "33bc9412134fc6a86c5b9ba7012086d563cbe3fc"
  "api/schema.sql"                         = "05d57e90f86b955bc194b5de1d0673662b2b3351"
  "api/tests/test_crm_contratos.py"        = "bf9bf262ca1f65ef53f39a84b60317ff744418dc"
  "api/tests/test_contrato_regras.py"      = "bc308980edfb853732e73209c736b5d4a42a1656"
  "web/src/components/crm/AbaContrato.jsx" = "2854f9490295fd8b78351fb0ab558456f72f10d0"
  "web/src/tests/AbaContrato.test.jsx"     = "04d99a8db944f4e57f62b24ad6a776c378c96523"
}
$arquivos = $novos + @($base.Keys)

function Servidor {
  Write-Host ""
  Write-Host "== Servidor: destinatarios do aviso ==" -ForegroundColor Cyan
  Write-Host "Digite os e-mails separados por virgula (faturamento, contratos, ADM)."
  $lista = Read-Host "Destinatarios"
  $lista = ($lista -replace '\s', '')
  if (-not $lista) { Write-Host "Nada digitado. Nada foi feito." -ForegroundColor Yellow; return }
  & scp -i $Chave "infra\por-chave-no-env.sh" "${Alvo}:/tmp/por-chave-no-env.sh"
  if ($LASTEXITCODE -ne 0) { Write-Host "scp falhou." -ForegroundColor Red; return }
  & ssh -t -i $Chave $Alvo "bash /tmp/por-chave-no-env.sh CONTRATO_AVISO_DESTINATARIOS --valor '$lista'"
  Write-Host ""
  Write-Host "Conferir: aba Contrato de um contrato assinado mostra 'Aviso ao faturamento ...'" -ForegroundColor Green
  Write-Host "Contratos assinados ANTES desta entrega nao recebem aviso sozinhos: use 'Enviar aviso' na aba." -ForegroundColor Green
}

if ($SoServidor) { Servidor; return }

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "038_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 038 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere da base da 054" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base da 054 (outra entrega mexeu nele?)." -ForegroundColor Red
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
    & "..\$py" -m pytest -q -p no:cacheprovider --no-cov tests/test_contrato_regras.py
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
  git commit -m "Contrato: aviso de contrato assinado para faturamento, contratos e ADM pelo Gmail do executivo (migration 038)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. O deploy aplica a migration 038 sozinho." -ForegroundColor Green
  Write-Host ""
  Write-Host "DEPOIS DO CI VERDE, grave a lista de destinatarios:" -ForegroundColor Cyan
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\deploy-054-aviso-contrato.ps1 -SoServidor"
}
