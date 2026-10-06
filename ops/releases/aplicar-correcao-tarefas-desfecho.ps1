# HIPO - valida e publica a correcao de:
#   1. tarefa de parceiro travada no modulo de Tarefas (nao pedia a proxima)
#   2. modal de desfecho abrindo atras do modal da oportunidade
#   3. registro do fechamento obrigatorio no desfecho
#
# Os 16 arquivos JA foram gravados na pasta pelo Claude. Este script nao
# edita codigo: ele confere o que mudou, roda o que da para rodar no
# Windows, e publica no branch.
#
# Uso, a partir da raiz de "Hipo - v1.4.0":
#   powershell -ExecutionPolicy Bypass -File .\aplicar-correcao-tarefas-desfecho.ps1
#
# Opcoes:
#   -SemPush         valida e commita, mas nao empurra
#   -SoValidar       so roda os testes, nao mexe no git
#   -Branch <nome>   troca o nome do branch
#
# Sem acentos de proposito: comentario acentuado embaralha se este arquivo
# for colado no terminal em vez de executado.

#requires -Version 5.1
[CmdletBinding()]
param(
  [string]$Branch = "fix/tarefa-parceiro-e-registro-de-fechamento",
  [switch]$SemPush,
  [switch]$SoValidar
)

$ErrorActionPreference = "Stop"
$raiz = (Get-Location).Path

function Titulo($t) {
  Write-Host ""
  Write-Host ("=" * 68) -ForegroundColor DarkGray
  Write-Host "  $t" -ForegroundColor Cyan
  Write-Host ("=" * 68) -ForegroundColor DarkGray
}
function Ok($t)   { Write-Host "  OK   $t" -ForegroundColor Green }
function Aviso($t){ Write-Host "  ...  $t" -ForegroundColor Yellow }
function Morre($t){ Write-Host "  ERRO $t" -ForegroundColor Red; exit 1 }

# Os 16 arquivos que a correcao toca. Se algum estiver faltando, a pasta
# nao e a que o Claude gravou - melhor parar do que commitar pela metade.
$arquivos = @(
  "api/routers/crm_tarefas.py",
  "api/routers/crm_oportunidades.py",
  "api/tests/test_crm_oportunidades.py",
  "api/tests/test_crm_tarefas.py",
  "api/tests/test_tarefas_parceiro.py",
  "api/tests/test_crm_parceiros.py",
  "web/src/components/crm/tarefaComum.jsx",
  "web/src/components/crm/AbaTarefas.jsx",
  "web/src/components/crm/ModalDesfecho.jsx",
  "web/src/components/ui/Modal.jsx",
  "web/src/pages/crm/Tarefas.jsx",
  "web/src/pages/crm/Oportunidades.jsx",
  "web/src/tests/Modal.test.jsx",
  "web/src/tests/Tarefas.test.jsx",
  "web/src/tests/ModalDesfecho.test.jsx",
  "web/src/tests/Oportunidades.test.jsx"
)

# ------------------------------------------------------------------
Titulo "1/5  Conferindo a pasta"
# ------------------------------------------------------------------

if (-not (Test-Path "$raiz\api") -or -not (Test-Path "$raiz\web")) {
  Morre "rode este script na raiz de 'Hipo - v1.4.0' (a pasta que tem api\ e web\)."
}
Ok "raiz: $raiz"

$faltando = @()
foreach ($a in $arquivos) {
  if (-not (Test-Path (Join-Path $raiz $a))) { $faltando += $a }
}
if ($faltando.Count -gt 0) {
  Write-Host "  Faltando:" -ForegroundColor Red
  $faltando | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
  Morre "$($faltando.Count) arquivo(s) da correcao nao estao na pasta."
}
Ok "os 16 arquivos da correcao estao no lugar"

# Marcadores da correcao. Confere que a versao gravada e a nova, e nao a
# antiga - arquivo presente com conteudo velho passaria batido no teste
# de existencia acima.
$marcas = @{
  "web/src/components/crm/tarefaComum.jsx" = "exigeProximaTarefa"
  "web/src/components/ui/Modal.jsx"        = "CAMADAS"
  "api/routers/crm_tarefas.py"             = "inserir_tarefa_concluida"
  "api/routers/crm_oportunidades.py"       = "TarefaDeFinalizacao"
}
foreach ($par in $marcas.GetEnumerator()) {
  $conteudo = Get-Content (Join-Path $raiz $par.Key) -Raw -Encoding UTF8
  if ($conteudo -notmatch [regex]::Escape($par.Value)) {
    Morre "$($par.Key) nao tem '$($par.Value)' - o arquivo ainda e o antigo."
  }
}
Ok "conteudo confere (versao nova, nao a antiga)"

# ------------------------------------------------------------------
Titulo "2/5  O que mudou"
# ------------------------------------------------------------------

$temGit = $false
try { git rev-parse --is-inside-work-tree 2>$null | Out-Null; $temGit = $true } catch { }

if ($temGit) {
  git diff --stat -- $arquivos
  Ok "diff acima. O git e o backup: 'git checkout -- <arquivo>' desfaz qualquer um."
} else {
  Aviso "esta pasta nao e um repositorio git - pulando diff e publicacao."
  $SoValidar = $true
}

# ------------------------------------------------------------------
Titulo "3/5  Testes do frontend (vitest)"
# ------------------------------------------------------------------

Push-Location "$raiz\web"
try {
  if (-not (Test-Path "node_modules")) {
    Aviso "node_modules ausente - rodando npm ci (demora)"
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Morre "npm ci falhou." }
  }
  npx vitest run
  if ($LASTEXITCODE -ne 0) { Morre "vitest falhou - nao publique." }
  Ok "frontend verde (esperado: 445 testes)"
} finally { Pop-Location }

# ------------------------------------------------------------------
Titulo "4/5  Testes do backend (so os de logica pura)"
# ------------------------------------------------------------------
# Os testes que tocam banco precisam de Postgres e so rodam no CI. Aqui
# vao os puros, que e o que da para validar no Windows. Os testes de
# desfecho e de tarefa de parceiro estao entre os de banco - quem fecha a
# conta e o CI.

$puros = @(
  "tests/test_tarefa_regras.py",
  "tests/test_oportunidade_regras.py",
  "tests/test_parceiro_regras.py",
  "tests/test_proposta_regras.py",
  "tests/test_dias_uteis.py",
  "tests/test_cnpj.py",
  "tests/test_texto.py",
  "tests/test_relatorio_conteudo.py",
  "tests/test_telemetria_ruido.py"
)

Push-Location "$raiz\api"
try {
  # PYTHONPATH explicito: sem isso o import de 'services' e 'routers'
  # quebra dependendo de como o python foi chamado.
  $env:PYTHONPATH = (Get-Location).Path

  $py = "python"
  if (Test-Path "venv\Scripts\python.exe") { $py = ".\venv\Scripts\python.exe" }

  & $py -m pytest -q --no-cov @puros
  if ($LASTEXITCODE -ne 0) {
    Aviso "algum teste puro falhou. Confira antes de publicar."
    if (-not $SoValidar) { Morre "abortando a publicacao." }
  } else {
    Ok "logica pura verde"
  }
} finally { Pop-Location }

# Sanidade que nao precisa de banco: os modulos importam?
#
# config.Settings() exige DATABASE_URL e JWT_SECRET no proprio import - o
# conftest do pytest injeta as duas com setdefault, um "python -c" avulso
# nao. Valores de mentira aqui: nada conecta, so importa. O host e um
# localhost inexistente de proposito, para nunca esbarrar em producao.
Push-Location "$raiz\api"
$dbAntes  = $env:DATABASE_URL
$jwtAntes = $env:JWT_SECRET
try {
  $py = "python"
  if (Test-Path "venv\Scripts\python.exe") { $py = ".\venv\Scripts\python.exe" }
  $env:PYTHONPATH   = (Get-Location).Path
  $env:DATABASE_URL = "postgresql://checagem:checagem@127.0.0.1:1/import_check"
  $env:JWT_SECRET   = "checagem-de-import"

  & $py -c "import routers.crm_tarefas, routers.crm_oportunidades; print('imports ok')"
  if ($LASTEXITCODE -ne 0) { Morre "os routers nao importam - erro de sintaxe ou import circular." }
  Ok "routers importam (sem ciclo entre crm_oportunidades e crm_tarefas)"
} finally {
  # Devolve o ambiente como estava: DATABASE_URL de mentira vazando para o
  # resto da sessao e o tipo de coisa que faz um comando seguinte falhar
  # sem motivo aparente.
  $env:DATABASE_URL = $dbAntes
  $env:JWT_SECRET   = $jwtAntes
  Pop-Location
}

if ($SoValidar) {
  Titulo "Fim - modo so validar"
  Write-Host "  Nada foi commitado. Rode sem -SoValidar para publicar." -ForegroundColor Gray
  exit 0
}

# ------------------------------------------------------------------
Titulo "5/5  Branch, commit e push"
# ------------------------------------------------------------------

$atual = (git rev-parse --abbrev-ref HEAD).Trim()
if ($atual -eq $Branch) {
  Ok "ja no branch $Branch"
} else {
  $existe = git branch --list $Branch
  if ($existe) { git checkout $Branch } else { git checkout -b $Branch }
  if ($LASTEXITCODE -ne 0) { Morre "nao consegui trocar de branch." }
  Ok "branch: $Branch (era $atual)"
}

git add -- $arquivos
if ($LASTEXITCODE -ne 0) { Morre "git add falhou." }

$mensagem = @"
fix(crm): tarefa de parceiro travada, desfecho atras do modal e registro de fechamento

1. Tarefa de parceiro nao deixava concluir no modulo de Tarefas.
   Tarefas.jsx decidia se pedia a proxima olhando so status_oportunidade,
   que chega nulo em tarefa de parceiro. A tela escondia o formulario da
   proxima e ainda dizia "oportunidade finalizada"; o backend recusava com
   422 (exige_proxima(None) e True). A unica saida era abrir o parceiro
   pelo modulo de Parceiros. A regra virou uma funcao so,
   exigeProximaTarefa(alvo, status), compartilhada com a AbaTarefas -
   quem decide e o alvo, nao o nulo. Comentarios do backend que ainda
   descreviam a regra antiga foram corrigidos.

2. Modal de desfecho abria atras do modal da oportunidade.
   Todo modal usava z-50 e o Modal renderiza no lugar do JSX, entao o
   empilhamento vinha da ordem no DOM. Modal ganhou a prop nivel
   (1=z-50, 2=z-[60], 3=z-[70]); desfecho e drilldown da conta declaram
   nivel=2 em si mesmos.

3. Finalizar uma oportunidade passa a exigir o registro do fechamento.
   POST /desfecho recebe o campo obrigatorio 'tarefa' e cria a tarefa ja
   concluida na mesma transacao. Vale para conquistado, perdido e
   cancelado. responsavel_id vazio = quem finalizou; prazo vazio = agora.
   Obrigatorio no schema, nao so na tela.

Testes: backend 989 passed (Postgres real), frontend 445 passed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0189q3cDTsmB6yEjAX9NdCCM
"@

# UTF-8 SEM BOM. O "-Encoding UTF8" do PowerShell 5.1 grava COM bom, e o
# git nao tira: o BOM entra como primeiro caractere do subject e aparece
# como lixo invisivel antes do "fix(" no historico do GitHub.
$tmp = Join-Path $env:TEMP "hipo-commit-msg.txt"
[IO.File]::WriteAllText($tmp, $mensagem, (New-Object Text.UTF8Encoding $false))
git commit -F $tmp
$rc = $LASTEXITCODE
Remove-Item $tmp -ErrorAction SilentlyContinue
if ($rc -ne 0) { Morre "git commit falhou (nada staged?)." }
Ok "commit criado"

if ($SemPush) {
  Titulo "Fim - sem push"
  Write-Host "  Commit local pronto. 'git push -u origin $Branch' quando quiser." -ForegroundColor Gray
  exit 0
}

git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { Morre "push falhou." }

Titulo "Pronto"
Write-Host "  Branch $Branch publicado." -ForegroundColor Green
Write-Host "  Abra o PR e espere os 3 jobs (Backend + Frontend + Deploy)." -ForegroundColor Gray
Write-Host ""
Write-Host "  Depois do deploy, logout/login antes de testar: o front le" -ForegroundColor Gray
Write-Host "  o usuario do localStorage e Ctrl+Shift+R nao zera isso." -ForegroundColor Gray
