# =====================================================================
#  HIPO -- deploy 048: confirmacao da vespera automatica
# =====================================================================
#
#  O que entra:
#    * Reuniao marcada numa oportunidade com pelo menos 2 dias uteis de
#      antecedencia abre sozinha uma tarefa de WhatsApp "Confirmar
#      reuniao dd/mm hh:mm - Empresa" para QUEM AGENDOU, no dia util
#      anterior as 09:00, com a mensagem do roteiro ja preenchida.
#    * A tarefa segue a reuniao: remarcou -> muda de dia (ou e cancelada
#      se nao sobrou folga); cancelou / no-show / realizada -> cancelada.
#    * Ela NAO conta como proximo passo da oportunidade.
#    * Migration 029: tarefas.confirmacao_de (aditiva, sem backfill).
#
#    1. pre-voo      -- arquivos, base do git, migration 029 livre, SSH
#    2. testes       -- regras puras (o CI roda o resto)
#    3. migration    -- 029 no RDS ANTES do push (e na base MOS, se ela
#                       ja existir -- entrega 046)
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#
#  Independe das entregas 046 (instancia MOS) e 047 (temperatura do
#  contato): nenhum arquivo em comum, pode ir antes ou depois delas.
#
#  USO
#     .\deploy-048-confirmacao-vespera.ps1 -Simular
#     .\deploy-048-confirmacao-vespera.ps1
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
    [int]$EsperaMax   = 1800
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

# Commit sobre o qual a entrega foi feita (entrega 045, main em 05/10/2026).
$base = "a7bc8b5"

$substituidos = @(
    "api\routers\crm_agenda.py",
    "api\routers\crm_tarefas.py",
    "api\schema.sql",
    "api\tests\test_crm_agenda.py"
)

$novos = @(
    "api\migrations\029_confirmacao_vespera.sql",
    "api\services\confirmacao.py",
    "api\tests\test_confirmacao_regras.py",
    "api\tests\test_crm_confirmacao_vespera.py",
    "infra\aplicar-029-confirmacao-vespera.sh",
    "deploy-048-confirmacao-vespera.ps1"
)

$entrega = $substituidos + $novos

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
Bom "arquivos da entrega conferidos"

& git cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
& git merge-base --is-ancestor $base HEAD
if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
Bom "base: $base esta no HEAD"
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

Passo "migration 029 livre..."
$outras029 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "029_*.sql" |
    Where-Object { $_.Name -ne "029_confirmacao_vespera.sql" })
if ($outras029.Count -gt 0) {
    Abortar "ja existe outra migration 029 ($($outras029[0].Name)). Me avise para renumerar."
}
Bom "029 livre"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
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
# 2. Testes puros
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            Passo "pytest (regras da confirmacao, da agenda e de tarefa)..."
            & python -m pytest -q --no-cov tests\test_confirmacao_regras.py tests\test_agenda_regras.py tests\test_tarefa_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "regras verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 029 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 029 no RDS"

$sql    = Join-Path $Pasta "api\migrations\029_confirmacao_vespera.sql"
$script = Join-Path $Pasta "infra\aplicar-029-confirmacao-vespera.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 029 (aditiva, sem backfill) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/029_confirmacao_vespera.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do SQL falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-029-confirmacao-vespera.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-029-confirmacao-vespera.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration falhou (codigo $LASTEXITCODE). Nada foi pushado." }
    Bom "migration 029 aplicada na base principal"

    # Desde a 046 pode existir a base da MOS, com o MESMO codigo: sem a 029
    # nela, as telas de tarefa e agenda da MOS dariam 500 depois do push.
    & ssh -i $Chave $alvo "sudo test -f /home/hipo/mos/.env"
    if ($LASTEXITCODE -eq 0) {
        Passo "instancia MOS encontrada -- aplicando a 029 nela tambem..."
        & ssh -t -i $Chave $alvo "ENV_PATH=/home/hipo/mos/.env bash /tmp/aplicar-029-confirmacao-vespera.sh"
        if ($LASTEXITCODE -ne 0) { Abortar "a migration falhou na base MOS (codigo $LASTEXITCODE). Nada foi pushado." }
        Bom "migration 029 aplicada na base MOS"
    } else {
        Passo "sem instancia MOS neste servidor -- so a base principal"
    }
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(agenda): confirmacao da vespera automatica (entrega 048)

- Reuniao marcada em oportunidade com 2+ dias uteis de folga abre uma
  tarefa de WhatsApp para quem agendou no dia util anterior, 09:00, com
  a mensagem do roteiro preenchida (amanha / dia da semana, link ou
  endereco). Pula fim de semana e dia_nao_util.
- A confirmacao segue a reuniao: remarcar move (ou cancela sem folga),
  remarcar depois de confirmada abre outra; cancelar, no-show,
  cancelada e realizada cancelam a aberta.
- Nao conta como proximo passo (contar_outras_abertas e outras_abertas).
- Regras puras em services/confirmacao.py. TarefaOut.confirmacao_de.
  Migration 029 (aditiva) + schema.sql.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QsyGQBGfwDGX5Puf613gxe
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 048 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-048.txt"
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

$marcador = "grep -q confirmacao_de /home/hipo/app/api/routers/crm_agenda.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo $marcador 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."
        exit 1
    }
    Bom "codigo novo no servidor"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R. NAO precisa relogar (nenhuma permissao mudou).
  2. Marque uma reuniao numa oportunidade para daqui a 3 dias uteis.
  3. Em Tarefas, quem agendou ve 'Confirmar reuniao dd/mm hh:mm - Empresa'
     na vespera, 09:00, com a mensagem pronta no detalhe.
  4. Remarque a reuniao: a confirmacao muda de dia junto.
"@ -ForegroundColor White
