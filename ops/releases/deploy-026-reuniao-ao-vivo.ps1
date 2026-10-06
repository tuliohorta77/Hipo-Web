# =====================================================================
#  HIPO -- deploy 026: Reuniao ao vivo (prova de conceito da captura)
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, base do git, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 019 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz rsync e reinicia
#    5. espera       -- ate o codigo novo aparecer no servidor
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#    A tela nova le reuniao_sessoes_ao_vivo e reuniao_falas_ao_vivo.
#    Codigo novo com tabela inexistente = 500 na tela "Reuniao ao vivo".
#
#  A BASE DO GIT
#    A entrega foi feita em cima do commit 731c250 (botao Filtros das
#    oportunidades). Seis arquivos existentes sao SUBSTITUIDOS. Se algum
#    commit depois de 731c250 mexeu num deles, a entrega apagaria essa
#    mudanca -- o pre-voo confere e para.
#
#  O QUE ESTE SCRIPT NAO FAZ: pip install, nem mexer no .env. A captura
#  nao usa biblioteca nova nem chave nova: quem transcreve e o Chrome do
#  vendedor, e o servidor so recebe texto.
#
#  USO
#     .\deploy-026-reuniao-ao-vivo.ps1 -Simular
#     .\deploy-026-reuniao-ao-vivo.ps1
#     .\deploy-026-reuniao-ao-vivo.ps1 -PularTestes
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
    [string]$Base     = "731c250"
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
    "web\src\components\crm\ModalReuniao.jsx",
    "web\src\tests\ModalReuniao.test.jsx"
)

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + @(
    "api\migrations\019_reuniao_ao_vivo.sql",
    "api\services\ao_vivo.py",
    "api\routers\crm_ao_vivo.py",
    "api\tests\test_ao_vivo_regras.py",
    "api\tests\test_crm_ao_vivo.py",
    "infra\aplicar-019-reuniao-ao-vivo.sh",
    "web\src\components\crm\aoVivo.js",
    "web\src\pages\crm\ReuniaoAoVivo.jsx",
    "web\src\tests\aoVivo.test.js",
    "web\src\tests\ReuniaoAoVivo.test.jsx",
    "deploy-026-reuniao-ao-vivo.ps1"
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
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega conferidos"

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
# 3. Migration 019 -- ANTES do push
# =====================================================================

Titulo "3. Migration 019 no RDS"

$sql    = Join-Path $Pasta "api\migrations\019_reuniao_ao_vivo.sql"
$script = Join-Path $Pasta "infra\aplicar-019-reuniao-ao-vivo.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 019 cria reuniao_sessoes_ao_vivo e reuniao_falas_ao_vivo." -ForegroundColor Gray
    Write-Host "  Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 019 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # -t: o script pergunta antes de gravar, e le a resposta de /dev/tty.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-019-reuniao-ao-vivo.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 019 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 019 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(agenda): Reuniao ao vivo -- transcricao durante a call (PoC)

Prova de conceito do copiloto de reuniao: a tela "Reuniao ao vivo",
aberta numa aba ao lado do Meet, capta o microfone do vendedor e o audio
da aba do Meet e transcreve cada um no proprio Chrome (Web Speech API com
MediaStreamTrack, Chrome 133+). Custo de transcricao zero: o audio nao
passa pelo HIPO, so o texto, em lotes de 10 s.

- Dois canais (vendedor = microfone, cliente = aba): quem falou vem de
  graca, sem diarizacao. Painel com tempo, palavras de cada lado e a
  proporcao de fala do vendedor (amarela acima de 60%).
- Sessoes de captura com canais, navegador e erros do reconhecimento;
  falas com seq unico por sessao (reenvio nao duplica).
- Depois que a transcricao do Meet chega, a tela mostra quanto das
  palavras dela o ao vivo tambem pegou -- e o gabarito da PoC.
- Quem liga: anfitriao, participante ou gestao; de 1 h antes do inicio
  ate 3 h depois do fim; so reuniao online nao cancelada.
- Link "Reuniao ao vivo" no modal da reuniao.
- GET/POST /crm/agenda/tarefas/{id}/ao-vivo, POST /crm/agenda/ao-vivo/
  {sessao}/falas e /encerrar.

Migration 019 (aditiva, idempotente).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KasXt4zEWpFfuyvyRb9zRF
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-026.txt"
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

$marcador = "/home/hipo/app/api/routers/crm_ao_vivo.py"
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
  1. Ctrl+Shift+R no navegador (assets novos). NAO precisa relogar: a
     tela vive no modulo 'crm'.
  2. Agenda > abra uma reuniao ONLINE de hoje > link "Reuniao ao vivo".
     A captura abre 1 hora antes do inicio.
  3. Abra o Meet em outra aba. Na tela ao vivo, "Iniciar transcricao",
     escolha a aba do Meet e deixe "Compartilhar audio da guia" marcado.
  4. No fim, "Encerrar". Quando a transcricao do Meet chegar (timer de
     15 min), a tela mostra a comparacao com ela.
"@ -ForegroundColor White
