# HIPO - Entrega 053: contrato com assinatura eletronica pela Autentique.
#  - modelo do contrato (api/templates/contrato_modelo.docx), recriado da
#    minuta da Porto Pisos; editavel no Word;
#  - aba Contrato na oportunidade + botao "Contrato" na versao aprovada;
#  - webhook /api/webhooks/autentique e timer de sincronizacao (30 min);
#  - migration 037 (aditiva), aplicada sozinha pelo deploy do CI.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-053-contrato-assinatura.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy-053-contrato-assinatura.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\deploy-053-contrato-assinatura.ps1 -Forcar
#   powershell -ExecutionPolicy Bypass -File .\deploy-053-contrato-assinatura.ps1 -SoServidor
#       (pula o commit: so poe as chaves no .env, ensaia e instala o timer)

param([switch]$Simular, [switch]$Forcar, [switch]$SoServidor)

$ErrorActionPreference = "Stop"
$ok = $true
$Chave = "$HOME\Downloads\chave-hipo.pem"
$Alvo = "ec2-user@35.156.111.168"

$novos = @(
  "api/migrations/037_contratos.sql",
  "api/routers/crm_contratos.py",
  "api/routers/webhooks.py",
  "api/scripts/gerar_modelo_contrato.py",
  "api/scripts/sincronizar_contratos.py",
  "api/scripts/ensaiar_contrato.py",
  "api/services/autentique.py",
  "api/services/contrato.py",
  "api/services/contrato_render.py",
  "api/templates/contrato_logo.jpg",
  "api/templates/contrato_modelo.docx",
  "api/tests/test_contrato_regras.py",
  "api/tests/test_contrato_render.py",
  "api/tests/test_crm_contratos.py",
  "infra/hipo-contratos.service",
  "infra/hipo-contratos.timer",
  "infra/instalar-timer-contratos.sh",
  "web/src/components/crm/AbaContrato.jsx",
  "web/src/tests/AbaContrato.test.jsx",
  "deploy-053-contrato-assinatura.ps1"
)

# Arquivos que esta entrega altera: a versao no HEAD precisa ser a do
# commit d62984c (RP-2.1). Se nao for, outra entrega mexeu neles e
# sobrescrever perderia mudanca.
$base = [ordered]@{
  "api/config.py"                                  = "81e611f9644198006ae6172bc63922ea7f523a87"
  "api/main.py"                                    = "f831a0abe0f5e2d4d22526e2f40a16fbf01191c6"
  "api/schema.sql"                                 = "e4c992310bf0222f998ec9c0b879019a1ac40cad"
  "api/services/atividade.py"                      = "97039dbe9479f73afced972b9f6a97d55e75a022"
  "web/src/components/crm/AbaProposta.jsx"         = "6ed702ae8d9365bb03dc0bac1a6df1d2af77c65e"
  "web/src/components/crm/OportunidadeDetalhe.jsx" = "a7bae9a54b774927d8002e62c3e73ea8d5e5b459"
  "web/src/tests/AbaProposta.test.jsx"             = "be61e429a83fa44ea0970e5075da631de9ba5449"
  "infra/por-chave-no-env.sh"                      = "b4698741ec14cae73e0bbb80c9bafbb872352523"
}
$arquivos = $novos + @($base.Keys)

function Servidor {
  Write-Host ""
  Write-Host "== Servidor: chaves no .env ==" -ForegroundColor Cyan
  Write-Host "Cada uma pede o valor no terminal (nao aparece na tela)."
  foreach ($f in @("infra\por-chave-no-env.sh", "infra\hipo-contratos.service",
                   "infra\hipo-contratos.timer", "infra\instalar-timer-contratos.sh")) {
    & scp -i $Chave $f "${Alvo}:/tmp/$(Split-Path $f -Leaf)"
    if ($LASTEXITCODE -ne 0) { Write-Host "scp de $f falhou." -ForegroundColor Red; return }
  }
  # Publicos: vao com --valor, sem prompt.
  & ssh -t -i $Chave $Alvo "bash /tmp/por-chave-no-env.sh CONTRATO_CONTRATADA_NOME --valor 'Marcelo Canton Dick'"
  & ssh -t -i $Chave $Alvo "bash /tmp/por-chave-no-env.sh CONTRATO_CONTRATADA_EMAIL --valor marcelod@controllermedseg.com.br"
  # Segredos: digitados.
  Write-Host "Cole o TOKEN da API (painel.autentique.com.br > Chaves de API):" -ForegroundColor Yellow
  & ssh -t -i $Chave $Alvo "bash /tmp/por-chave-no-env.sh AUTENTIQUE_API_TOKEN"
  Write-Host "Cole o SEGREDO do webhook (painel da Autentique > Webhooks > endpoint do HIPO):" -ForegroundColor Yellow
  & ssh -t -i $Chave $Alvo "bash /tmp/por-chave-no-env.sh AUTENTIQUE_WEBHOOK_SEGREDO"

  Write-Host ""
  Write-Host "== Servidor: ensaio (monta o PDF, nao envia nada) ==" -ForegroundColor Cyan
  # Como ec2-user, o mesmo usuario da API e do timer: o config.py le o
  # .env (600 ec2-user) sozinho. Nada de `source`: o nome do CEO tem espaco.
  & ssh -t -i $Chave $Alvo "cd /home/hipo/app/api && PYTHONPATH=/home/hipo/app/api python3 -m scripts.ensaiar_contrato"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "O ensaio acusou problema (saida acima). Corrija antes de instalar o timer." -ForegroundColor Red
    return
  }

  Write-Host ""
  Write-Host "== Servidor: timer de sincronizacao ==" -ForegroundColor Cyan
  & ssh -t -i $Chave $Alvo "bash /tmp/instalar-timer-contratos.sh"

  Write-Host ""
  Write-Host "Webhook: o endereco a cadastrar na Autentique e" -ForegroundColor Green
  Write-Host "  https://hipogestao.com.br/api/webhooks/autentique"
  Write-Host "  eventos: signature.viewed, signature.accepted, signature.rejected,"
  Write-Host "           signature.delivery_failed, document.finished"
  Write-Host "Teste: curl -s -o /dev/null -w '%{http_code}' -X POST https://hipogestao.com.br/api/webhooks/autentique"
  Write-Host "  -> 401 (assinatura invalida) prova que a rota existe e o segredo esta no .env; 503 = segredo vazio."
}

if ($SoServidor) { Servidor; return }

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "037_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 037 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
foreach ($f in $base.Keys) {
  $head = (git rev-parse "HEAD:$f" 2>$null)
  if ($head -ne $base[$f]) {
    if ($Forcar) {
      Write-Host "  AVISO (forcado): $f no HEAD difere da base da 053" -ForegroundColor Yellow
    } else {
      Write-Host "  $f no HEAD difere da base da 053 (outra entrega mexeu nele?)." -ForegroundColor Red
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
  Write-Host "== Vitest (Contrato, Proposta, Oportunidades) ==" -ForegroundColor Cyan
  Push-Location web
  npx vitest run src/tests/AbaContrato.test.jsx src/tests/AbaProposta.test.jsx src/tests/Oportunidades.test.jsx
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
  git commit -m "Contrato com assinatura eletronica pela Autentique: modelo, aba Contrato, webhook e sincronizacao (migration 037)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI (Backend, Frontend, Deploy)." -ForegroundColor Green
  Write-Host "O deploy aplica a migration 037 sozinho." -ForegroundColor Green
  Write-Host ""
  Write-Host "DEPOIS DO CI VERDE, configure o servidor (chaves, ensaio e timer):" -ForegroundColor Cyan
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\deploy-053-contrato-assinatura.ps1 -SoServidor"
}
