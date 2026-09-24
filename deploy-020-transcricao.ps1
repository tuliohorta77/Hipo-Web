# =====================================================================
#  HIPO -- deploy 020: transcricao das reunioes do Google Meet
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 016 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    5. espera       -- ate o codigo novo aparecer no servidor
#    6. timer        -- instala o hipo-transcricoes.timer (a cada 15 min)
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#    A grade da agenda passa a fazer LEFT JOIN em reuniao_transcricoes.
#    Codigo novo com tabela inexistente = 500 na Agenda inteira.
#
#  POR QUE O TIMER VEM DEPOIS DO PUSH
#    A unit roda scripts/coletar_transcricoes.py, que e codigo novo. O
#    script do servidor confere que ele chegou antes de instalar.
#
#  O COMMIT LEVA SO A ENTREGA, e nao `git add -A`. Havia tres arquivos
#  modificados de fora (deploy-019, por-chave-no-env, zerar-funcionarios)
#  na ultima vez que olhamos -- nao sao desta entrega.
#
#  O QUE ESTE SCRIPT NAO FAZ: os passos no Google (Meet REST API no Cloud
#  Console, dois escopos novos na delegacao, Transcricoes ligadas no Admin
#  Console). Sem eles o codigo sobe e funciona, so que a coleta grava o
#  erro "falta o escopo" na tarefa. O roteiro esta no fim da saida.
#
#  USO
#     .\deploy-020-transcricao.ps1 -Simular
#     .\deploy-020-transcricao.ps1
#     .\deploy-020-transcricao.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    # O NOME, e nao o IP: a instancia ainda nao tem Elastic IP, e o IP ja
    # mudou uma vez (23/09) -- os deploys 018 e 019 ainda apontam para o
    # antigo, que hoje e de outra pessoa.
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 900
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

# Os arquivos da entrega. E tambem a lista do `git add`.
$entrega = @(
    "api\migrations\016_reuniao_transcricao.sql",
    "api\schema.sql",
    "api\services\transcricao.py",
    "api\services\google_meet.py",
    "api\services\resumo_reuniao.py",
    "api\services\coleta_transcricao.py",
    "api\services\google_agenda.py",
    "api\services\atividade.py",
    "api\routers\crm_agenda.py",
    "api\scripts\coletar_transcricoes.py",
    "api\tests\test_transcricao_regras.py",
    "api\tests\test_google_meet.py",
    "api\tests\test_crm_transcricao.py",
    "infra\aplicar-016-transcricao.sh",
    "infra\hipo-transcricoes.service",
    "infra\hipo-transcricoes.timer",
    "web\src\components\crm\TranscricaoReuniao.jsx",
    "web\src\components\crm\ModalReuniao.jsx",
    "web\src\components\crm\AbaTarefas.jsx",
    "web\src\pages\crm\Tarefas.jsx",
    "web\src\tests\TranscricaoReuniao.test.jsx",
    "deploy-020-transcricao.ps1"
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

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Bom "chave SSH encontrada"

Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  TIMEOUT na 22: antes de culpar o security group, confira o IP" -ForegroundColor Gray
    Write-Host "  na fonte (aws ec2 describe-instances) -- ja mudou uma vez." -ForegroundColor Gray
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
# 3. Migration 016 -- ANTES do push
# =====================================================================

Titulo "3. Migration 016 no RDS"

$sql    = Join-Path $Pasta "api\migrations\016_reuniao_transcricao.sql"
$script = Join-Path $Pasta "infra\aplicar-016-transcricao.sh"
$svc    = Join-Path $Pasta "infra\hipo-transcricoes.service"
$tmr    = Join-Path $Pasta "infra\hipo-transcricoes.timer"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 016 cria reuniao_transcricoes e duas colunas nulaveis em" -ForegroundColor Gray
    Write-Host "  reunioes. Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 016 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script $svc $tmr "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # -t: o script pergunta antes de gravar, e le a resposta de /dev/tty.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-016-transcricao.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 016 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 016 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(agenda): transcricao das reunioes do Google Meet, salva na tarefa

A reuniao online ja nasce com Meet; agora a sala nasce tambem com a
transcricao automatica ligada (Meet REST API, artifactConfig). Um timer
a cada 15 min busca as falas das reunioes que acabaram e grava o texto
na tarefa (reuniao_transcricoes), com resumo e proximos passos pela IA
-- sugestao, nao desfecho. Numero no resumo que nao esta na transcricao
descarta o resumo (mesma guarda do fechamento).

Painel "Transcricao" nas tres telas que mostram a tarefa (Tarefas, aba
da oportunidade, formulario da reuniao), com "Buscar agora".

Migration 016 (aditiva, idempotente) + hipo-transcricoes.timer.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019GvoeE2GXnWfYvdEQ41cko
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-020.txt"
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

$marcador = "/home/hipo/app/api/scripts/coletar_transcricoes.py"
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
        Write-Host "  Quando ficar verde, instale o timer na mao:" -ForegroundColor Gray
        Write-Host "     ssh -t -i $Chave $alvo `"bash /tmp/aplicar-016-transcricao.sh --timer`"" -ForegroundColor White
        exit 1
    }
    Bom "codigo novo no servidor"

    Passo "health da API..."
    & ssh -i $Chave $alvo "curl -s -o /dev/null -w '%{http_code}' https://hipogestao.com.br/api/health"
    Write-Host ""
}

# =====================================================================
# 6. Timer
# =====================================================================

Titulo "6. Timer do coletor"
if ($Simular) {
    Aviso "simulacao: nao vou instalar"
} else {
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-016-transcricao.sh --timer"
    if ($LASTEXITCODE -ne 0) { Abortar "a instalacao do timer falhou (codigo $LASTEXITCODE)." }
    Bom "hipo-transcricoes.timer ligado"
}

# =====================================================================
# O que falta, e e com voce no Google
# =====================================================================

Titulo "Falta no Google (uma vez)"
Write-Host @"
  1. console.cloud.google.com, projeto hipo-agenda:
       APIs e servicos -> Biblioteca -> "Google Meet REST API" -> Ativar

  2. admin.google.com -> Seguranca -> Acesso e controle de dados ->
     Controles de API -> Gerenciar delegacao em todo o dominio ->
     Client ID 103061815113290784263 -> Editar. Escopos (virgula):
       https://www.googleapis.com/auth/calendar.events,
       https://www.googleapis.com/auth/meetings.space.readonly,
       https://www.googleapis.com/auth/meetings.space.settings

  3. admin.google.com -> Apps -> Google Workspace -> Google Meet ->
     Configuracoes de video do Meet -> Transcricoes: ATIVADO

  Teste: marque uma reuniao online para daqui a 10 min, entre no Meet,
  fale um pouco, saia. Em ate 15 min (ou no "Buscar agora") o texto
  aparece na tarefa.
"@ -ForegroundColor White
