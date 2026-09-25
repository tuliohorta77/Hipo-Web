# =====================================================================
#  HIPO -- deploy 021: modulo de Relatorios (tabela dinamica + salvos)
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, base do git, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 017 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    5. espera       -- ate o codigo novo aparecer no servidor
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#    A tela de Relatorios carrega a lista de relatorios salvos ao abrir.
#    Codigo novo com tabela inexistente = 500 na tela.
#
#  A BASE DO GIT
#    A entrega foi feita em cima do commit de88080 (24/09, "fix(meet)").
#    Oito arquivos existentes sao SUBSTITUIDOS (main.py, schema.sql,
#    atividade.py, App.jsx, Layout.jsx, Oportunidades.jsx, Contas.jsx,
#    Layout.test.jsx). Se algum commit depois de de88080 mexeu num deles,
#    o zip apagaria essa mudanca -- o pre-voo confere e para.
#
#  O QUE ESTE SCRIPT NAO FAZ: nada no Google, nada de pip install. O modulo
#  so usa o que ja esta instalado na EC2.
#
#  USO
#     .\deploy-021-relatorios.ps1 -Simular
#     .\deploy-021-relatorios.ps1
#     .\deploy-021-relatorios.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 900,
    [string]$Base     = "de88080"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}
function Passo($texto) { Write-Host "  -> $texto" -ForegroundColor Gray }
function Bom($texto)   { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !!  $texto" -ForegroundColor Yellow }
function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}
function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

$alvo = "$Usuario@$Servidor"

# Arquivos EXISTENTES que a entrega substitui (conferidos contra a base).
$substituidos = @(
    "api\main.py",
    "api\schema.sql",
    "api\services\atividade.py",
    "web\src\App.jsx",
    "web\src\components\Layout.jsx",
    "web\src\pages\crm\Oportunidades.jsx",
    "web\src\pages\crm\Contas.jsx",
    "web\src\tests\Layout.test.jsx"
)

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + @(
    "api\migrations\017_relatorios_salvos.sql",
    "api\services\permissao.py",
    "api\services\relatorios.py",
    "api\routers\crm_relatorios.py",
    "api\tests\test_relatorios_regras.py",
    "api\tests\test_crm_relatorios.py",
    "infra\aplicar-017-relatorios.sh",
    "web\src\pages\crm\Relatorios.jsx",
    "web\src\components\relatorios\periodo.js",
    "web\src\components\relatorios\pivot.js",
    "web\src\components\relatorios\SeletorCampo.jsx",
    "web\src\components\relatorios\FiltroCampo.jsx",
    "web\src\components\relatorios\Construtor.jsx",
    "web\src\components\relatorios\TabelaDinamica.jsx",
    "web\src\components\relatorios\RegistrosDaCelula.jsx",
    "web\src\components\relatorios\SalvarRelatorio.jsx",
    "web\src\components\relatorios\ListaSalvos.jsx",
    "web\src\tests\relatoriosLogica.test.js",
    "web\src\tests\Relatorios.test.jsx",
    "web\src\tests\RelatoriosConstrutor.test.jsx",
    "deploy-021-relatorios.ps1"
)

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta
Bom "pasta: $Pasta"

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta. Extraiu o zip na raiz?"
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

Passo "base do git ($Base)..."
& git cat-file -e "$Base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Abortar "o commit $Base nao existe aqui. Rode 'git pull' ANTES de extrair o zip."
}
& git merge-base --is-ancestor $Base HEAD
if ($LASTEXITCODE -ne 0) {
    Abortar "HEAD nao descende de $Base. Rode 'git pull' ANTES de extrair o zip."
}
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $Base HEAD -- $git_substituidos
if ($mexidos) {
    Write-Host "  Commits depois de $Base mexeram em arquivos que o zip substitui:" -ForegroundColor Red
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "o zip apagaria essas mudancas. Me mande os arquivos atuais para eu refazer o patch."
}
Bom "nenhum commit depois de $Base mexeu nos arquivos substituidos"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Bom "chave SSH encontrada"

Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para aplicar a migration."
}
Bom "porta 22 responde"

# =====================================================================
# 2. Testes do front
# =====================================================================

Titulo "2. Testes do front"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    Push-Location (Join-Path $Pasta "web")
    try {
        Passo "vitest..."
        & npm.cmd run test -- --run
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Corrija antes de subir." }
        Bom "vitest verde"
        Passo "vite build..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Abortar "o build do front falhou." }
        Bom "build ok"
    } finally { Pop-Location }
}

# =====================================================================
# 3. Migration 017 -- ANTES do push
# =====================================================================

Titulo "3. Migration 017 no RDS"

$sql    = Join-Path $Pasta "api\migrations\017_relatorios_salvos.sql"
$script = Join-Path $Pasta "infra\aplicar-017-relatorios.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 017 cria relatorios_salvos (tabela + 2 indices)." -ForegroundColor Gray
    Write-Host "  Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 017 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # -t: o script pergunta antes de gravar, e le a resposta de /dev/tty.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-017-relatorios.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 017 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 017 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(relatorios): tabela dinamica sobre a base + relatorios salvos no perfil

Modulo de Relatorios (/crm/relatorios), no estilo da tabela dinamica do
Excel: fonte de dados, periodo (pela data que fizer sentido: criacao,
desfecho, prazo, data da reuniao...), filtros, linhas, colunas e valores.

- 7 fontes (oportunidades, tarefas, reunioes, propostas, movimentacoes do
  funil, contas, contatos) e ~200 campos com nome claro, num catalogo em
  lista branca (services/relatorios.py). Nada do cliente vira SQL.
- Motor no banco com GROUPING SETS: subtotais e totais certos para media
  e contagem distinta. READ ONLY + statement_timeout de 20 s.
- Recorte por envolvimento (services/permissao.py): gestao ve tudo,
  operacional ve o que e seu -- na tabela, no drilldown e nos filtros.
- Drilldown: todo numero abre os registros, e cada registro abre a
  oportunidade ou a conta (?abrir=<id> em Oportunidades e Contas).
- Relatorios salvos com nome, periodo relativo ou fixo; compartilhar deixa
  a equipe ver e duplicar, editar e so do dono. ?r=<id> abre direto.

Migration 017 (aditiva, idempotente).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mt4fExbdSx7wRJV3rGdvzL
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Write-Host "  Vai no commit (e SO isto):" -ForegroundColor DarkGray
    & git status --short -- $entrega
    $fora = & git status --porcelain | Where-Object {
        $caminho = $_.Substring(3).Replace("/", "\")
        -not ($entrega -contains $caminho)
    }
    if ($fora) {
        Write-Host ""
        Write-Host "  Fica FORA do commit (modificado, mas nao e desta entrega):" -ForegroundColor DarkGray
        $fora | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
    }
    Confirmar "Commitar os arquivos da entrega e dar push na main?"

    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-021.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"

    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 5. Espera o codigo novo
# =====================================================================

Titulo "5. Esperando o CI"

$marcador = "/home/hipo/app/api/routers/crm_relatorios.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    Write-Host "  Os 3 jobs precisam ficar verdes. Pergunto ao servidor ate o arquivo chegar." -ForegroundColor Gray
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo "test -f $marcador" 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions no GitHub."
        exit 1
    }
    Bom "codigo novo no servidor"

    Passo "health da API..."
    & ssh -i $Chave $alvo "curl -s -o /dev/null -w '%{http_code}' https://hipogestao.com.br/api/health"
    Write-Host ""
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador (assets novos). NAO precisa relogar: o
     modulo e o 'crm', que todo cargo ja tem.
  2. Relatorios aparece na barra, antes do Monitor.
  3. Teste rapido: Oportunidades > Este mes > Linhas: Fase > Valores:
     Soma de Mensalidade. Clique num numero: abre os registros.
"@ -ForegroundColor White
