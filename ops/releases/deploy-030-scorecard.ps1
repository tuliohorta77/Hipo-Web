# =====================================================================
#  HIPO -- deploy 030: Scorecard da reuniao contra o Roteiro de Vendas
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, base do git, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 021 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    5. espera       -- ate o codigo novo aparecer no servidor
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#    O Monitor passa a ler reuniao_avaliacoes (quadro SCORECARD e coluna
#    Nota do APRE). Codigo novo com tabela inexistente = 500 no painel da
#    TV inteiro, e nao so numa tela nova.
#
#  A BASE DO GIT E AS OUTRAS ENTREGAS EM ANDAMENTO
#    Feita em cima do 16a22aa. Duas outras entregas estavam na pasta, ainda
#    sem subir: a UC (deploy-029-uc, migration 020 -- por isso esta e a
#    021) e a do pool asyncpg/CORS. As tres mexem em main.py, schema.sql,
#    atividade.py e test_monitor.py.
#
#    Esses QUATRO arquivos NAO vem inteiros: _entrega-030\patch_030.py
#    insere neles so o que e desta entrega, ancorado em linhas que as
#    outras nao tocam. Serve em qualquer ordem de deploy. Uma regra so: o
#    arquivo precisa estar LIMPO no git (sem mudanca de outra entrega
#    esperando commit), senao o `git add` daqui levaria a mudanca alheia
#    junto e o CI quebraria. Sujo = o pre-voo para e diz qual deploy rodar
#    antes.
#
#    Os outros dez arquivos substituidos sao conferidos contra o 16a22aa:
#    se algum commit depois dele mexeu num deles, o pre-voo para.
#
#  O QUE ESTE SCRIPT NAO FAZ
#    * pip install: nada novo (a IA vai por httpx, que ja esta la).
#    * mexer no .env: usa a ANTHROPIC_API_KEY que ja existe. O modelo da
#      avaliacao e claude-sonnet-4-5 (MODELO_PADRAO em
#      services/avaliacao_roteiro.py). NAO ponha ANTHROPIC_MODEL_AVALIACAO no
#      .env: o campo nao existe em config.py e, com extra="forbid", a API
#      nao sobe.
#    * o backfill das reunioes de setembro: e o avaliar-reunioes.ps1,
#      DEPOIS deste deploy (ensaio primeiro, -Aplicar depois).
#
#  USO
#     .\deploy-030-scorecard.ps1 -Simular
#     .\deploy-030-scorecard.ps1
#     .\deploy-030-scorecard.ps1 -PularTestes
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
    [string]$Base     = "16a22aa"
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


# Arquivos EXISTENTES que a entrega substitui INTEIROS (conferidos contra a base).
$substituidos = @(
    "api\routers\monitor.py",
    "api\scripts\coletar_transcricoes.py",
    "api\services\monitor.py",
    "api\tests\test_monitor_regras.py",
    "web\src\components\crm\TranscricaoReuniao.jsx",
    "web\src\components\monitor\ConfigMonitor.jsx",
    "web\src\components\monitor\DetalheIndicador.jsx",
    "web\src\components\monitor\monitorComum.js",
    "web\src\tests\Monitor.test.jsx",
    "web\src\tests\TranscricaoReuniao.test.jsx"
)

# Arquivos que outras entregas tambem mexem: recebem PATCH (patch_030.py).
$patcheados = @(
    "api\main.py",
    "api\schema.sql",
    "api\services\atividade.py",
    "api\tests\test_monitor.py"
)
$patch = "_entrega-030\patch_030.py"

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + $patcheados + @(
    "api\migrations\021_reuniao_avaliacao.sql",
    "api\routers\crm_avaliacao.py",
    "api\scripts\avaliar_reunioes.py",
    "api\services\avaliacao_roteiro.py",
    "api\services\coleta_avaliacao.py",
    "api\services\roteiro_scorecard.py",
    "api\tests\test_avaliacao_roteiro.py",
    "api\tests\test_crm_avaliacao.py",
    "infra\aplicar-021-reuniao-avaliacao.sh",
    "infra\avaliar-reunioes.sh",
    "web\src\components\crm\AvaliacaoRoteiro.jsx",
    "web\src\tests\AvaliacaoRoteiro.test.jsx",
    "avaliar-reunioes.ps1",
    "deploy-030-scorecard.ps1"
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

# Python para o patch: o do venv da API, se existir; senao o do sistema.
$python = Join-Path $Pasta "api\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
    if (-not $python) { Abortar "nao achei Python (precisa para o patch_030.py)." }
}
if (-not (Test-Path (Join-Path $Pasta $patch))) { Abortar "falta $patch." }
Bom "python: $python"

Passo "base do git ($Base)..."
& git cat-file -e "$Base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Abortar "o commit $Base nao existe aqui. Rode 'git pull' e me avise."
}
& git merge-base --is-ancestor $Base HEAD
if ($LASTEXITCODE -ne 0) {
    Abortar "HEAD nao descende de $Base. Rode 'git pull' e me avise."
}
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $Base HEAD -- $git_substituidos
if ($mexidos) {
    Write-Host "  Commits depois de $Base mexeram em arquivos que a entrega substitui:" -ForegroundColor Red
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "a entrega apagaria essas mudancas. Me mande os arquivos atuais para eu refazer o patch."
}
Bom "nenhum commit depois de $Base mexeu nos arquivos substituidos"

Passo "os 4 arquivos que recebem patch: so podem ter mudanca DESTA entrega..."
& $python $patch --verificar
if ($LASTEXITCODE -eq 2) {
    Write-Host "  Mudanca de outra entrega que ainda nao subiu (UC: deploy-029-uc.ps1;" -ForegroundColor Red
    Write-Host "  pool/CORS: o deploy dela). Rode aquele deploy primeiro e depois este." -ForegroundColor Red
    Abortar "o git add desta entrega levaria a mudanca alheia junto e o CI quebraria."
}
if ($LASTEXITCODE -ne 0) { Abortar "a verificacao do patch falhou (ancora mudou?). Me mande os arquivos." }

if ($Simular) {
    & $python $patch --conferir
} else {
    & $python $patch
}
if ($LASTEXITCODE -ne 0) { Abortar "o patch_030 nao aplicou (ancora mudou?). Nada foi gravado." }
Bom "patch nos 4 arquivos ok"

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

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
# 3. Migration 021 -- ANTES do push
# =====================================================================

Titulo "3. Migration 021 no RDS"

$sql    = Join-Path $Pasta "api\migrations\021_reuniao_avaliacao.sql"
$script = Join-Path $Pasta "infra\aplicar-021-reuniao-avaliacao.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 021 cria reuniao_avaliacoes e reuniao_avaliacao_itens." -ForegroundColor Gray
    Write-Host "  Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 021 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # -t: o script pergunta antes de gravar, e le a resposta de /dev/tty.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-021-reuniao-avaliacao.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 021 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 021 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(agenda): Scorecard da reuniao contra o Roteiro de Vendas

Toda reuniao de oportunidade com transcricao do Meet ganha, na mesma
passada do hipo-transcricoes.timer, uma avaliacao da IA contra o Roteiro
de Vendas da casa (versao 2026-09-30).

- 10 itens de 0 a 2 (max 20), cada um com o trecho LITERAL da conversa,
  justificativa e sugestao. Nota sem trecho que confira na transcricao e
  descartada (conta 0 ate a gestao avaliar).
- Resumo do coach: 2 pontos fortes, 2 a melhorar (com como fazer) e o
  foco da proxima reuniao. Tempo de fala do vendedor contado das falas.
- A nota vale assim que sai; a gestao (Franqueado/ADM) ajusta item a
  item -- COALESCE(nota_gestor, nota_ia) -- e valida como selo.
- Monitor: o quadro SCORECARD (media do mes, meta padrao 15) toma o lugar
  do TREINAMENTO; o detalhe do APRE ganha a coluna Nota.
- Timer avalia as dos ultimos 3 dias; scripts.avaliar_reunioes faz o
  backfill (ensaio por padrao). Trava por advisory lock contra avaliacao
  dupla.
- GET/POST/PATCH/DELETE /crm/agenda/tarefas/{id}/avaliacao[...].

Migration 021 (aditiva, idempotente).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01474CTKcBkDkCpGaSGbS4oZ
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-030.txt"
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

$marcador = "/home/hipo/app/api/routers/crm_avaliacao.py"
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
  1. Ctrl+Shift+R no navegador (assets novos). NAO precisa relogar: as
     rotas vivem no modulo 'crm' e o Monitor e de todo mundo.
  2. Monitor: o ultimo quadro agora e SCORECARD (meta padrao 15; ajuste
     em Metas e calendario). Fica sem carinha ate a primeira avaliacao.
  3. Backfill de setembro -- ensaio primeiro, depois de verdade:
       .\avaliar-reunioes.ps1
       .\avaliar-reunioes.ps1 -Aplicar -Limite 3     # confere 3 na tela
       .\avaliar-reunioes.ps1 -Aplicar               # o resto
  4. Abra uma reuniao com transcricao: o bloco "Scorecard do roteiro"
     aparece abaixo do resumo. Como gestao, "Ver os 10 itens" vira o
     seletor 0/1/2 de cada item, e o botao Validar aparece.
  5. Daqui para frente, a nota sai sozinha ate 15 min depois de a
     transcricao chegar. Log: journalctl -u hipo-transcricoes.service
"@ -ForegroundColor White
