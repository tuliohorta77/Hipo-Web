# =====================================================================
#  HIPO -- deploy 050c: e-mail enviado vira tarefa concluida
# =====================================================================
#
#  O que entra:
#    * Todo envio da aba E-mails grava, na mesma transacao, uma tarefa JA
#      CONCLUIDA da oportunidade -- tipo E-mail, ou Proposta quando vai com
#      o PDF -- em nome de quem enviou e com o contato. O envio passa a
#      aparecer na lista de tarefas, na aba Tarefas da oportunidade e na
#      producao do mes.
#    * Migration 031 (aditiva): emails_enviados.tarefa_id + backfill dos
#      e-mails ja enviados (ganham a tarefa com a data do envio).
#    * Nao abre tarefa nem exige proximo passo: a tarefa nasce fechada.
#
#    1. pre-voo   -- arquivos, base do git, 031 livre
#    2. testes    -- regras puras
#    3. push      -- SO os arquivos da entrega (o CI aplica a 031)
#    4. espera    -- ate o codigo novo chegar no servidor
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-050c-email-vira-tarefa.ps1 -Simular
#     .\ops\releases\deploy-050c-email-vira-tarefa.ps1
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
Set-Location $Pasta

# Commit sobre o qual a entrega foi feita (050 + instalador 050b, 06/10/2026).
$base = "d9e3a68"

$substituidos = @(
    "api\routers\crm_tarefas.py",
    "api\routers\crm_emails.py",
    "api\services\email_comercial.py",
    "api\schema.sql",
    "api\tests\test_crm_emails.py",
    "api\tests\test_email_comercial_regras.py"
)
$novos = @(
    "api\migrations\031_email_tarefa.sql",
    "ops\releases\deploy-050c-email-vira-tarefa.ps1"
)
$entrega = $substituidos + $novos

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }
if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) { Abortar "rode da raiz do repositorio." }
$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega presentes"
$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne "main") { Abortar "voce esta no ramo '$ramo', nao na main." }
& git cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
& git merge-base --is-ancestor $base HEAD
if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
Bom "base $base no HEAD, arquivos substituidos intactos"
$outras031 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "031_*.sql" |
    Where-Object { $_.Name -ne "031_email_tarefa.sql" })
if ($outras031.Count -gt 0) { Abortar "ja existe outra migration 031 ($($outras031[0].Name))." }
Bom "031 livre"

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            & python -m pytest -q --no-cov tests\test_email_comercial_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "regras verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

Titulo "3. Push"
$mensagem = @"
feat(crm): e-mail enviado vira tarefa concluida (entrega 050c)

- Cada envio da aba E-mails grava, na mesma transacao, uma tarefa ja
  concluida da oportunidade (E-mail, ou Proposta quando vai com o PDF),
  em nome do remetente e com o contato: aparece na lista de tarefas, na
  aba Tarefas e na producao do mes. Nao abre tarefa nem exige proxima.
- inserir_tarefa_concluida aceita resultado.
- Migration 031 (aditiva): emails_enviados.tarefa_id + backfill dos
  e-mails ja enviados.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BmZvcuQXtjPbAz1p9dkYRg
"@
if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 050c e dar push na main? (o CI aplica a 031)"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-050c.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

Titulo "4. Esperando o CI"
$marcador = "grep -q tarefa_do_envio /home/hipo/app/api/routers/crm_emails.py"
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
    if (-not $chegou) { Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."; exit 1 }
    Bom "codigo novo no servidor"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R. NAO precisa relogar.
  2. Tarefas -> filtro Concluidas: os e-mails ja enviados aparecem como
     'E-mail enviado: ...' e 'Proposta vN enviada por e-mail'.
  3. Mande um e-mail novo pela oportunidade: a tarefa concluida aparece
     na aba Tarefas dela na hora.
"@ -ForegroundColor White
