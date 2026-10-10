# HIPO - Entrega 056: ligacoes pelo Vivo Voz Negocio, gravadas e transcritas.
#
#  - o clique no telefone do contato (aba Contatos, tarefa, conta) avisa o
#    HIPO antes de o tel: abrir o softphone;
#  - o gravador (agente Windows, pasta gravador/) percebe a chamada pelo
#    microfone do softphone, grava microfone + saida em 2 canais e manda
#    direto para o S3 por URL assinada;
#  - o servidor casa a gravacao com o clique da mesma pessoa, transcreve no
#    AWS Transcribe (um canal por lado) e resume com a IA;
#  - aba Ligacoes na oportunidade, faixa "sem vinculo" em Tarefas e o
#    Gravador de ligacoes no Perfil (token por maquina, download do
#    instalador montado pelo CI em /downloads/hipo-gravador.zip);
#  - migration 040 (aditiva), aplicada pelo deploy do CI;
#  - timer hipo-ligacoes (a cada 2 min), instalado com -Servidor.
#
# Uso (na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File .\deploy-056-ligacoes.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\deploy-056-ligacoes.ps1
#   ... espere os 3 jobs do CI ficarem verdes, cole a policy na role da EC2 ...
#   powershell -ExecutionPolicy Bypass -File .\deploy-056-ligacoes.ps1 -Servidor

param([switch]$Simular, [switch]$Forcar, [switch]$Servidor)

$ErrorActionPreference = "Stop"
$ok = $true
$chave = Join-Path $HOME "Downloads\chave-hipo.pem"
$host_ec2 = "ec2-user@hipogestao.com.br"

if ($Servidor) {
  Write-Host "== Timer das ligacoes na EC2 ==" -ForegroundColor Cyan
  if (-not (Test-Path $chave)) { Write-Host "Chave SSH nao encontrada: $chave" -ForegroundColor Red; exit 1 }
  scp -i $chave infra/hipo-ligacoes.service infra/hipo-ligacoes.timer infra/instalar-ligacoes.sh "${host_ec2}:/tmp/"
  if ($LASTEXITCODE -ne 0) { Write-Host "scp falhou." -ForegroundColor Red; exit 1 }
  ssh -t -i $chave $host_ec2 "bash /tmp/instalar-ligacoes.sh"
  if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Timer instalado. Agora: Perfil > Gravador de ligacoes > Gerar token, e instale o gravador." -ForegroundColor Green
  } else {
    Write-Host "O instalador do servidor saiu com $LASTEXITCODE (mensagem acima)." -ForegroundColor Yellow
  }
  exit $LASTEXITCODE
}

$novos = @(
  "api/migrations/040_ligacoes.sql",
  "api/routers/crm_ligacoes.py",
  "api/routers/ligacoes_gravador.py",
  "api/scripts/coletar_ligacoes.py",
  "api/services/coleta_ligacao.py",
  "api/services/ligacao.py",
  "api/services/ligacao_aws.py",
  "api/tests/test_crm_ligacoes.py",
  "api/tests/test_ligacao_regras.py",
  "gravador/LEIA-ME.md",
  "gravador/app/__init__.py",
  "gravador/app/bandeja.py",
  "gravador/app/captura.py",
  "gravador/app/cliente.py",
  "gravador/app/config.py",
  "gravador/app/deteccao.py",
  "gravador/app/envio.py",
  "gravador/app/fila.py",
  "gravador/app/principal.py",
  "gravador/desinstalar.ps1",
  "gravador/hipo_gravador.pyw",
  "gravador/instalar.ps1",
  "gravador/requirements.txt",
  "gravador/tests/test_gravador.py",
  "infra/hipo-ligacoes.service",
  "infra/hipo-ligacoes.timer",
  "infra/instalar-ligacoes.sh",
  "infra/policy-transcribe-ligacoes.json",
  "web/src/components/crm/AbaLigacoes.jsx",
  "web/src/components/crm/GravadorLigacoes.jsx",
  "web/src/components/crm/LigacaoDetalhe.jsx",
  "web/src/components/crm/LigacoesSemVinculo.jsx",
  "web/src/components/crm/ligacoes.js",
  "web/src/tests/Ligacoes.test.jsx",
  "deploy-056-ligacoes.ps1"
)

# Versao de cada arquivo na entrega 055 (commit 2ea64d5).
$base = [ordered]@{
  ".github/workflows/ci-cd.yml"                  = "1474826748e08b0ac2203b61ad9a8ffc2534b66a"
  "api/config.py"                                = "bd7942882012f9efab14d06f21c4ce74bf65b3d0"
  "api/main.py"                                  = "b0d8627afe183759959021325363bdd60d443b62"
  "api/schema.sql"                               = "acddd66b14f01c80a04f19839951f79126080281"
  "api/services/atividade.py"                    = "97c391e4280c8f0335b709ec99abbf0e0b862c70"
  "api/services/resumo_reuniao.py"               = "8002fd861dc74de3fa379ca7f919292f89748334"
  "web/src/components/crm/AbaContatos.jsx"       = "978973e309b87ce9b07f166021ebb03e7fd9ed1c"
  "web/src/components/crm/ContatosDaConta.jsx"   = "24d2be7aa6c71105b63382da546d1422c58c85e2"
  "web/src/components/crm/OportunidadeDetalhe.jsx" = "af5d15bdc497871797e5a08b3e5e9f776c9d76f6"
  "web/src/components/crm/contatoComum.jsx"      = "70e6fdc63d3e16cf7d83cc6ccc02e4501a27b154"
  "web/src/components/crm/tarefaComum.jsx"       = "38b4f138c0aa0990a53c9409d14baecdd6f88efd"
  "web/src/pages/Perfil.jsx"                     = "2c3806af301aa0e8acc3cf5a6c0f0c2766fbf42b"
  "web/src/pages/crm/Tarefas.jsx"                = "171f7225f7e2f09236432c69775d4c71784b0962"
}
$arquivos = $novos + @($base.Keys)

Write-Host "== Pre-voo ==" -ForegroundColor Cyan
$m39 = (git rev-parse "HEAD:api/migrations/039_contrato_grupo_cnpj.sql" 2>$null)
if (-not $m39) {
  Write-Host "  A entrega 055 (migration 039) ainda nao foi commitada." -ForegroundColor Red
  $ok = $false
}
foreach ($f in $arquivos) {
  if (-not (Test-Path $f)) { Write-Host "  FALTA: $f" -ForegroundColor Red; $ok = $false }
}
$migs = Get-ChildItem "api/migrations" -Filter "040_*.sql" | Select-Object -ExpandProperty Name
if (@($migs).Count -ne 1) {
  Write-Host "  Numero 040 em uso por outra migration: $($migs -join ', ')" -ForegroundColor Red
  $ok = $false
}
if ($m39) {
  foreach ($f in $base.Keys) {
    $head = (git rev-parse "HEAD:$f" 2>$null)
    if ($head -ne $base[$f]) {
      if ($Forcar) {
        Write-Host "  AVISO (forcado): $f no HEAD difere da base da 056" -ForegroundColor Yellow
      } else {
        Write-Host "  $f no HEAD difere da base da 056 (outra entrega mexeu nele?)." -ForegroundColor Red
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
  Write-Host "== Vitest (ligacoes e telas tocadas) ==" -ForegroundColor Cyan
  Push-Location web
  npx vitest run src/tests/Ligacoes.test.jsx src/tests/Perfil.test.jsx src/tests/Tarefas.test.jsx src/tests/ContatosMultithreading.test.jsx src/tests/ContaDetalhe.test.jsx src/tests/AbaTarefas.test.jsx src/tests/Oportunidades.test.jsx
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
    Write-Host "== Pytest (regras das ligacoes, sem banco) ==" -ForegroundColor Cyan
    Push-Location api
    $env:PYTHONPATH = (Get-Location).Path
    & "..\$py" -m pytest -q -p no:cacheprovider --no-cov tests/test_ligacao_regras.py
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
  git commit -m "Ligacoes pelo Vivo Voz Negocio: clique, gravador Windows, transcricao no AWS Transcribe e aba Ligacoes (migration 040)" -- $arquivos
  git push
  Write-Host ""
  Write-Host "Push feito. Acompanhe os 3 jobs do CI. O deploy aplica a migration 040 sozinho." -ForegroundColor Green
  Write-Host ""
  Write-Host "Depois do CI verde:" -ForegroundColor Green
  Write-Host "  1. AWS Console > IAM > Roles > (role da EC2) > Add permissions > Create inline policy > JSON:" -ForegroundColor Green
  Write-Host "     cole infra\policy-transcribe-ligacoes.json, nome 'hipo-ligacoes'." -ForegroundColor Green
  Write-Host "  2. .\deploy-056-ligacoes.ps1 -Servidor   (instala o timer; confere a policy antes)" -ForegroundColor Green
  Write-Host "  3. Ctrl+Shift+R, Perfil > Gravador de ligacoes > Gerar token > baixar e instalar." -ForegroundColor Green
}
