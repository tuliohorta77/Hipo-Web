# =====================================================================
#  HIPO -- deploy 024: RPeR gerado do HIPO + metas por squad e pessoa
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, base do git, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 018 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    5. espera       -- ate o codigo novo aparecer no servidor
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#    O PPT le as metas do mes em metas_comerciais. Codigo novo com tabela
#    inexistente = 500 no botao RPeR.
#
#  A BASE DO GIT
#    A entrega foi feita em cima do commit 8255abf (monitor tema escuro).
#    Cinco arquivos existentes sao SUBSTITUIDOS (main.py, schema.sql,
#    atividade.py, Monitor.jsx, Monitor.test.jsx). Se algum commit depois
#    de 8255abf mexeu num deles, o zip apagaria essa mudanca -- o pre-voo
#    confere e para.
#
#  O QUE ESTE SCRIPT NAO FAZ: pip install. O RPeR usa python-pptx (ja
#  instalado para a proposta) e, para o PDF, o LibreOffice (idem). A IA usa
#  a ANTHROPIC_API_KEY que o fechamento diario ja usa.
#
#  USO
#     .\deploy-024-rper.ps1 -Simular
#     .\deploy-024-rper.ps1
#     .\deploy-024-rper.ps1 -PularTestes
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
    [string]$Base     = "8255abf"
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
    "web\src\pages\Monitor.jsx",
    "web\src\tests\Monitor.test.jsx"
)

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + @(
    "api\migrations\018_metas_comerciais.sql",
    "api\services\rper.py",
    "api\services\rper_dados.py",
    "api\services\rper_ia.py",
    "api\services\rper_render.py",
    "api\routers\rper.py",
    "api\templates\rper\bg_capa.png",
    "api\templates\rper\bg_secao.png",
    "api\templates\rper\bg_conteudo.png",
    "api\templates\rper\logo.png",
    "api\templates\rper\swoosh_laranja.png",
    "api\templates\rper\swoosh_verde.png",
    "api\tests\test_rper_regras.py",
    "api\tests\test_rper.py",
    "infra\aplicar-018-metas-comerciais.sh",
    "web\src\components\monitor\RperMonitor.jsx",
    "web\src\tests\RperMonitor.test.jsx",
    "deploy-024-rper.ps1"
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
# 3. Migration 018 -- ANTES do push
# =====================================================================

Titulo "3. Migration 018 no RDS"

$sql    = Join-Path $Pasta "api\migrations\018_metas_comerciais.sql"
$script = Join-Path $Pasta "infra\aplicar-018-metas-comerciais.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 018 cria metas_comerciais (tabela + 3 indices)." -ForegroundColor Gray
    Write-Host "  Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 018 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # -t: o script pergunta antes de gravar, e le a resposta de /dev/tty.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-018-metas-comerciais.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 018 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 018 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(rper): PPT da Reuniao de Planejamento e Resultados gerado do HIPO

O PPT do 1o dia util (resultados do mes fechado + planejamento do mes
seguinte) sai pronto do Monitor, botao RPeR (gestao).

- 15 slides no visual do PPT que a operacao ja usava (mesmas imagens,
  Poppins, paleta): capa; por squad EC, SDR e EV: secao, resultados
  (meta x realizado x atingimento + 4 quadros + leitura), indicadores por
  pessoa, planejamento (metas do mes novo + acoes); no EV ainda pipeline
  por executivo (graficos nativos) e top 10 negociacoes.
- Numeros das mesmas fontes do Monitor e da Agenda (desfecho efetivo,
  evento de venda, agendado_por). Realizado do squad sai das linhas
  deduplicadas, nao da soma das pessoas. MRR do EC = vendas do mes com o
  EC envolvido.
- Textos de leitura pela IA, com a guarda numerica POR CAMPO: numero
  inventado ou texto longo demais volta ao texto padrao so naquela caixa.
- Metas por squad e por pessoa (metas_comerciais): a do squad e lancada a
  parte, nao e a soma das pessoas. Aba de metas no mesmo modal, com copiar
  do mes anterior.
- GET /rper/previa, /rper/arquivo (pptx|pdf), /rper/metas (+ PUT, copiar).

Migration 018 (aditiva, idempotente).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01V9GEpNw7op3HmSDwmbS9iB
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-024.txt"
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

$marcador = "/home/hipo/app/api/routers/rper.py"
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
     RPeR vive no modulo 'crm' e a guarda e o cargo (gestao).
  2. Monitor > botao RPeR (so Franqueado e ADM veem).
  3. Aba 'Metas por squad e pessoa': lance as metas de setembro (para o
     RPeR de outubro, as de outubro). A meta do squad e separada.
  4. Aba 'Gerar PPT': escolha o mes fechado, confira a previa e baixe.
"@ -ForegroundColor White
