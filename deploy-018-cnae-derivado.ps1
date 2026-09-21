# =====================================================================
#  HIPO -- deploy 018: o de-para CNAE->vertical chega preenchido
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo      -- arquivos no lugar, chave SSH, porta 22
#    2. testes       -- vitest e build do front (o pytest de banco fica no CI)
#    3. migration    -- 015 no RDS, ANTES do push
#    4. push         -- o CI faz rsync e reinicia o servico
#    5. espera       -- ate o codigo novo aparecer no servidor
#    6. carga        -- deriva a vertical dos CNAEs antigos e preenche as contas
#    7. prova        -- conta quantas contas ficaram classificadas
#
#  POR QUE A MIGRATION VEM ANTES DO PUSH
#
#  Invertido, o codigo novo sobe pedindo uma coluna que ainda nao existe,
#  e a API comeca a estourar 500 no intervalo entre o deploy e o psql.
#
#  POR QUE A CARGA VEM DEPOIS DO PUSH
#
#  `scripts/semear_cnae_verticais.py` importa
#  `services/enriquecimento/cnae_estrutura.py`, que e codigo novo. Antes do
#  rsync ele nao existe no servidor. O script do lado de la detecta isso e
#  avisa em vez de estourar -- este aqui simplesmente espera.
#
#  A migration 015 e ADITIVA e IDEMPOTENTE: nenhum DROP, nenhum DELETE, e
#  rodar duas vezes nao faz nada na segunda. Por isso NAO exige export
#  previo em CSV -- essa regra vale para migration destrutiva, e esta nao e.
#
#  USO
#     .\deploy-018-cnae-derivado.ps1 -Simular    # nao muda nada, so confere
#     .\deploy-018-cnae-derivado.ps1
#     .\deploy-018-cnae-derivado.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO.
#
#  (PowerShell 5.1 come aspas duplas ao montar linha de comando externa, e
#  comentario com acento embaralha no copiar-e-colar. As duas coisas ja
#  custaram deploy aqui -- dai a regra do ASCII e dos argumentos passados
#  como array, nunca como string montada.)
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = "C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0",
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "63.179.88.212",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 600
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

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"

if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path $Pasta)) { Abortar "nao achei a pasta: $Pasta" }
Set-Location $Pasta
Bom "pasta: $Pasta"

# Os arquivos que a entrega precisa ter. Se um sumiu, o deploy quebra la na
# frente, e ai o banco ja mudou -- por isso a conferencia vem antes de tudo.
$esperados = @(
    "api\migrations\015_cnae_derivado.sql",
    "api\services\enriquecimento\cnae_estrutura.py",
    "api\services\enriquecimento\persistencia.py",
    "api\routers\crm_enriquecimento.py",
    "api\scripts\semear_cnae_verticais.py",
    "api\schema.sql",
    "api\tests\test_crm_enriquecimento.py",
    "infra\aplicar-015-cnae-derivado.sh",
    "web\src\components\crm\DeParaCnaes.jsx",
    "web\src\pages\crm\Cnaes.jsx",
    "web\src\tests\DeParaCnaes.test.jsx"
)

$faltando = @()
foreach ($f in $esperados) {
    if (-not (Test-Path (Join-Path $Pasta $f))) { $faltando += $f }
}
if ($faltando.Count -gt 0) {
    Write-Host ""
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($esperados.Count) arquivos da entrega conferidos"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Bom "chave SSH encontrada"

Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
}
catch { $aberta = $false }

if (-not $aberta) {
    Write-Host ""
    Write-Host "  A porta 22 nao respondeu. Se o erro for TIMEOUT, seu IP saiu" -ForegroundColor Gray
    Write-Host "  do Security Group (IP residencial e dinamico):" -ForegroundColor Gray
    Write-Host "     .\liberar-meu-ip-ssh.ps1" -ForegroundColor White
    Abortar "sem SSH nao da para aplicar a migration."
}
Bom "porta 22 responde"

# =====================================================================
# 2. Testes do front
# =====================================================================

Titulo "2. Testes do front"

if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
}
else {
    # O pytest de banco NAO roda aqui: sem Postgres local ele falha nos
    # testes com db_conn. Quem valida o backend e o job do CI.
    Passo "vitest..."
    Push-Location (Join-Path $Pasta "web")
    try {
        & npm.cmd run test -- --run
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Corrija antes de subir." }
        Bom "vitest verde"

        Passo "vite build..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Abortar "o build do front falhou." }
        Bom "build ok"
    }
    finally { Pop-Location }
}

# =====================================================================
# 3. Migration 015 -- ANTES do push
# =====================================================================

Titulo "3. Migration 015 no RDS"

$sqlLocal     = Join-Path $Pasta "api\migrations\015_cnae_derivado.sql"
$scriptLocal  = Join-Path $Pasta "infra\aplicar-015-cnae-derivado.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
}
else {
    Write-Host ""
    Write-Host "  A 015 cria a coluna cnaes.mapeamento_origem e marca como" -ForegroundColor Gray
    Write-Host "  'humano' o que ja estava classificado. Aditiva e idempotente." -ForegroundColor Gray
    Confirmar "Aplicar a migration 015 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sqlLocal $scriptLocal "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    # O `-t` nao e detalhe: o script do lado de la pergunta antes de gravar,
    # e a pergunta le de /dev/tty. Sem terminal alocado ele nem tenta --
    # avisa e sai. (Ja custou um deploy: script que chega por pipe nao
    # consegue usar `read`, porque o stdin do bash E o proprio script.)
    Passo "aplicando (ele vai perguntar antes de gravar)..."
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-015-cnae-derivado.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 015 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 015 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(crm): de-para CNAE->vertical ja nasce preenchido pela secao da CNAE 2.0

Todo CNAE passa a nascer com a vertical derivada da secao do IBGE
(mapeamento_origem='derivado'); a tela vira conferencia, nao
preenchimento. Corrigir sugestao e operacional, remapear decisao humana
segue sendo de gestao. Grau de risco continua nulo -- vale por subclasse
no Anexo I da NR-4.

Migration 015 (aditiva, idempotente) + scripts/semear_cnae_verticais.py
para o retroativo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BxSMHJfYav864xun8YJPuE
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    Write-Host ""
    Write-Host "  git status --short:" -ForegroundColor DarkGray
    & git status --short
}
else {
    $sujo = & git status --porcelain
    if (-not $sujo) {
        Aviso "nada para commitar -- o codigo ja esta versionado"
    }
    else {
        Write-Host ""
        Write-Host "  O que vai no commit:" -ForegroundColor DarkGray
        & git status --short
        Write-Host ""
        Write-Host "  Confira se nao ha lixo junto. No commit 789937e foram" -ForegroundColor Gray
        Write-Host "  tres arquivos de fora da entrega por causa de um git add ." -ForegroundColor Gray
        Confirmar "Commitar e dar push na main?"

        & git add -A
        if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }

        # A mensagem vai por arquivo, e nao por -m: PowerShell 5.1 come as
        # aspas ao montar a linha de comando externa, e a mensagem sai
        # picada em pedacos.
        $tmpMsg = Join-Path $env:TEMP "hipo-commit-018.txt"
        Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
        & git commit -F $tmpMsg
        if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou." }
        Remove-Item $tmpMsg -ErrorAction SilentlyContinue
        Bom "commit criado"

        & git push
        if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
        Bom "push feito -- o CI assumiu daqui"
    }
}

# =====================================================================
# 5. Espera o codigo novo chegar no servidor
# =====================================================================

Titulo "5. Esperando o CI"

$marcador = "/home/hipo/app/api/services/enriquecimento/cnae_estrutura.py"

if ($Simular) {
    Aviso "simulacao: nao vou esperar"
}
else {
    Write-Host ""
    Write-Host "  Os 3 jobs precisam ficar verdes (Backend + Frontend + Deploy)." -ForegroundColor Gray
    Write-Host "  Vou perguntar ao servidor ate o arquivo novo aparecer la." -ForegroundColor Gray
    Write-Host ""

    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou  = $false

    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo "test -f $marcador" 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        $s = [int]$relogio.Elapsed.TotalSeconds
        Write-Host "     ainda nao ($s s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 15
    }
    $relogio.Stop()

    if (-not $chegou) {
        Write-Host ""
        Aviso "o codigo novo nao chegou em $EsperaMax s."
        Write-Host ""
        Write-Host "  A migration JA ESTA APLICADA -- nada a desfazer. Confira o" -ForegroundColor Gray
        Write-Host "  run em github.com/tuliohorta77/Hipo-Web/actions e, quando" -ForegroundColor Gray
        Write-Host "  ficar verde, rode so a carga:" -ForegroundColor Gray
        Write-Host ""
        Write-Host "     .\deploy-018-cnae-derivado.ps1 -PularTestes" -ForegroundColor White
        Write-Host ""
        Write-Host "  (ele passa reto pela migration, que e idempotente, e vai" -ForegroundColor Gray
        Write-Host "   direto para a carga)" -ForegroundColor Gray
        Write-Host ""
        exit 0
    }
    Bom "codigo novo no servidor ($([int]$relogio.Elapsed.TotalSeconds) s)"
}

# =====================================================================
# 6. Carga retroativa das verticais
# =====================================================================

Titulo "6. Carga das verticais"

if ($Simular) {
    Aviso "simulacao: nao vou rodar a carga"
}
else {
    Write-Host ""
    Write-Host "  O script simula primeiro e mostra, por vertical, quantos" -ForegroundColor Gray
    Write-Host "  CNAEs e quantas contas seriam classificados. So grava depois" -ForegroundColor Gray
    Write-Host "  que voce confirmar. Ele nunca toca em CNAE decidido por gente" -ForegroundColor Gray
    Write-Host "  nem em conta que ja tem vertical." -ForegroundColor Gray
    Write-Host ""

    # Mesmo script da etapa 3. A migration ja aplicada e idempotente, entao
    # ele passa reto por ela e vai direto para a carga.
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-015-cnae-derivado.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a carga falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "carga concluida"
}

# =====================================================================
# 7. Prova
# =====================================================================

Titulo "7. Prova"

if ($Simular) {
    Write-Host ""
    Write-Host "  Simulacao terminada. Nada foi alterado." -ForegroundColor Cyan
    Write-Host "  Para valer:  .\deploy-018-cnae-derivado.ps1" -ForegroundColor White
    Write-Host ""
    exit 0
}

Passo "a API responde?"
try {
    $r = Invoke-WebRequest -Uri "https://hipogestao.com.br/api/openapi.json" `
        -TimeoutSec 20 -UseBasicParsing
    if ($r.StatusCode -eq 200) { Bom "openapi.json responde 200" }
    else { Aviso "openapi.json voltou $($r.StatusCode)" }
}
catch { Aviso "nao consegui falar com a API: $($_.Exception.Message)" }

Passo "quantas contas ficaram classificadas?"

# ESTE TRECHO VAI POR BASE64, E NAO COMO STRING DE ASPAS.
#
# PowerShell 5.1 remonta a linha de comando de um executavel externo e COME
# as aspas duplas no caminho. Um SQL com aspas, passado direto para o ssh,
# chega picado do outro lado e o psql estoura em erro de sintaxe. Em base64
# nao ha aspa nenhuma para ele comer -- o que viaja e um blob ASCII.
#
# (Aqui o `| bash` e seguro. O que nao pode e um script com `read` chegar
# assim: o stdin do bash vira o proprio script e a pergunta falha em
# silencio. Este trecho so consulta.)
#
# O .env e 600 e o dono NAO e necessariamente `hipo` -- em producao e do
# ec2-user. A cascata cobre os tres estados em vez de apostar num deles.
$remoto = @'
set -e
ENVV=$(sudo cat /home/hipo/app/.env 2>/dev/null \
    || sudo -iu hipo cat /home/hipo/app/.env 2>/dev/null \
    || cat /home/hipo/app/.env)
DB=$(printf '%s\n' "$ENVV" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
psql "$DB" -At <<'SQL'
SELECT 'contas ativas com vertical: '
       || count(*) FILTER (WHERE vertical_id IS NOT NULL)
       || ' de ' || count(*)
  FROM contas WHERE ativo;
SELECT 'CNAEs sugeridos, a conferir: ' || count(*)
  FROM cnaes WHERE mapeamento_origem = 'derivado';
SELECT 'CNAEs decididos por gente:   ' || count(*)
  FROM cnaes WHERE mapeamento_origem = 'humano';
SELECT 'contas ativas ainda sem vertical: ' || count(*)
  FROM contas WHERE ativo AND vertical_id IS NULL;
SQL
'@

$b64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes(($remoto -replace "`r`n", "`n"))
)

& ssh -i $Chave $alvo "echo $b64 | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { Aviso "nao consegui ler os numeros -- confira pela tela" }

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host "  FALTA VOCE FAZER" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  1. LOGOUT e LOGIN na tela." -ForegroundColor White
Write-Host "     O front le os modulos do localStorage, gravado no login." -ForegroundColor Gray
Write-Host "     Ctrl+Shift+R recarrega os assets mas NAO zera o localStorage." -ForegroundColor Gray
Write-Host ""
Write-Host "  2. CRM > CNAEs." -ForegroundColor White
Write-Host "     A lista chega preenchida. O trabalho agora e discordar onde" -ForegroundColor Gray
Write-Host "     couber: Confirmar aceita a sugestao, trocar vira Aplicar." -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Grau de risco continua vazio, de proposito." -ForegroundColor White
Write-Host "     Vale por subclasse no Anexo I da NR-4 -- derivar por secao" -ForegroundColor Gray
Write-Host "     seria inventar o numero que dimensiona SESMT." -ForegroundColor Gray
Write-Host ""
