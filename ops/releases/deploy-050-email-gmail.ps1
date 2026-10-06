# =====================================================================
#  HIPO -- deploy 050: e-mail comercial pela Gmail API
# =====================================================================
#
#  O que entra:
#    * Aba "E-mails" na oportunidade: primeiro contato e envio de proposta
#      saem DA CAIXA DO VENDEDOR pelo Gmail, com a assinatura dele. O
#      rascunho vem do modelo, preenchido; o vendedor ajusta e envia.
#    * "E-mail" em cada versao da proposta: abre o rascunho com o PDF
#      daquela versao (consolidada ou de um CNPJ) anexado.
#    * Modelos editaveis pela gestao (Franqueado/ADM), com variaveis.
#    * Resposta do cliente: o hipo-emails.timer olha os cabecalhos do fio
#      a cada 15 min (escopo gmail.metadata, sem ler o corpo) e marca
#      "Respondeu". Botao "Ver se respondeu" faz a mesma passada na hora.
#    * Migration 030 (aditiva): email_modelos + emails_enviados. Desde a
#      049 quem aplica e o CI/deploy -- nada de migration a mao.
#
#    1. pre-voo      -- arquivos, base do git, 030 livre, SSH
#    2. testes       -- regras puras (o CI roda o resto)
#    3. Google       -- checklist do Admin Console (voce faz, o script confere)
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. delegacao    -- token por escopo, sem enviar e-mail
#    7. timer        -- instala o hipo-emails.timer
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-050-email-gmail.ps1 -Simular
#     .\ops\releases\deploy-050-email-gmail.ps1
#     .\ops\releases\deploy-050-email-gmail.ps1 -SoTimer     # so os passos 6 e 7
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoTimer,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [string]$Caixa    = "tulio.horta@controllermedseg.com",
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

# Commit sobre o qual a entrega foi feita (entrega 049, main em 06/10/2026).
$base = "5a7e5e9"

$substituidos = @(
    "api\main.py",
    "api\services\atividade.py",
    "api\schema.sql",
    "web\src\components\crm\AbaProposta.jsx",
    "web\src\components\crm\OportunidadeDetalhe.jsx",
    "web\src\tests\AbaProposta.test.jsx"
)

$novos = @(
    "api\migrations\030_emails.sql",
    "api\services\email_comercial.py",
    "api\services\gmail.py",
    "api\routers\crm_emails.py",
    "api\scripts\verificar_respostas_email.py",
    "api\tests\test_email_comercial_regras.py",
    "api\tests\test_crm_emails.py",
    "web\src\components\crm\AbaEmails.jsx",
    "web\src\components\crm\ModelosEmail.jsx",
    "web\src\tests\AbaEmails.test.jsx",
    "infra\hipo-emails.service",
    "infra\hipo-emails.timer",
    "infra\instalar-timer-emails.sh",
    "infra\testar-delegacao-gmail.sh",
    "ops\releases\deploy-050-email-gmail.ps1"
)

$entrega = $substituidos + $novos

function Checar-Ssh {
    if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
    Passo "porta 22 em $Servidor..."
    $aberta = $false
    try {
        $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
            -InformationLevel Quiet -WarningAction SilentlyContinue
    } catch { $aberta = $false }
    if (-not $aberta) {
        Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
        Abortar "sem SSH nao da para conferir a delegacao nem instalar o timer."
    }
    Bom "porta 22 responde"
}

if (-not $SoTimer) {

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode da raiz do repositorio (nao achei api\main.py em $Pasta)."
}
Bom "pasta: $Pasta"

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
Bom "base: $base esta no HEAD"
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

Passo "migration 030 livre..."
$outras030 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "030_*.sql" |
    Where-Object { $_.Name -ne "030_emails.sql" })
if ($outras030.Count -gt 0) {
    Abortar "ja existe outra migration 030 ($($outras030[0].Name)). Me avise para renumerar."
}
Bom "030 livre"

Checar-Ssh

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
            Passo "pytest (regras do e-mail comercial e do catalogo de atividade)..."
            & python -m pytest -q --no-cov tests\test_email_comercial_regras.py tests\test_atividade.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "regras verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Google -- o que so voce pode fazer
# =====================================================================

Titulo "3. Google (Cloud Console + Admin Console)"
Write-Host @"
  O codigo sobe e funciona sem isto -- a aba E-mails so avisa que o envio
  esta desligado. Para LIGAR o envio:

  a) Cloud Console, projeto hipo-agenda:
     APIs e servicos -> Biblioteca -> "Gmail API" -> Ativar.

  b) Admin Console -> Seguranca -> Controle de acesso e dados ->
     Controles de API -> Delegacao em todo o dominio -> Client ID
     103061815113290784263 (hipo-calendar) -> Editar.
     A lista INTEIRA de escopos, separados por virgula (editar substitui
     tudo -- os do Calendar e do Meet precisam continuar):

https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/meetings.space.readonly,https://www.googleapis.com/auth/meetings.space.settings,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/gmail.metadata

  Nada muda no .env e nenhuma biblioteca nova (google-auth ja esta la).
"@ -ForegroundColor White
if (-not $Simular) {
    Confirmar "Fez (ou vai fazer) os passos a e b? O deploy segue de qualquer jeito"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(crm): e-mail comercial pela Gmail API (entrega 050)

- Aba E-mails na oportunidade: primeiro contato e envio de proposta saem
  da caixa do vendedor (delegacao em todo o dominio, gmail.send), com a
  assinatura do Gmail dele (gmail.settings.basic). Rascunho preenchido a
  partir do modelo; o que sai e o texto da tela.
- Botao E-mail em cada versao da proposta: PDF da versao (consolidada ou
  de um CNPJ) anexado, remontado na hora como no download.
- Modelos editaveis pela gestao, com variaveis validadas ao salvar.
- Resposta do cliente: hipo-emails.timer (15 min) e botao "Ver se
  respondeu" leem so os cabecalhos do fio (gmail.metadata).
- Falha do Gmail volta 502 e nao grava; so e-mail enviado vira linha.
- Migration 030 (aditiva): email_modelos, emails_enviados.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BmZvcuQXtjPbAz1p9dkYRg
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 050 e dar push na main? (o CI aplica a 030 e sobe o codigo)"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-050.txt"
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

$marcador = "test -f /home/hipo/app/api/routers/crm_emails.py"
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
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoTimer."
        exit 1
    }
    Bom "codigo novo no servidor"
}

} else {
    Titulo "Modo -SoTimer: pulando direto para a delegacao e o timer"
    Checar-Ssh
}

# =====================================================================
# 6. Delegacao (sem enviar e-mail)
# =====================================================================

Titulo "6. Delegacao do Gmail ($Caixa)"
$teste = Join-Path $Pasta "infra\testar-delegacao-gmail.sh"
if ($Simular) {
    Aviso "simulacao: nao vou conferir"
} else {
    & scp -i $Chave $teste "${alvo}:/tmp/testar-delegacao-gmail.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do teste falhou." }
    & ssh -i $Chave $alvo "bash /tmp/testar-delegacao-gmail.sh $Caixa"
    if ($LASTEXITCODE -ne 0) {
        Aviso "algum escopo ainda nao responde (ver acima). A delegacao leva ate ~10 min para"
        Aviso "propagar. O timer pode ser instalado assim mesmo -- ele so registra o erro."
    } else {
        Bom "os quatro escopos respondem e a Gmail API esta habilitada"
    }
}

# =====================================================================
# 7. Timer da verificacao de resposta
# =====================================================================

Titulo "7. hipo-emails.timer"
if ($Simular) {
    Aviso "simulacao: nao vou instalar"
} else {
    foreach ($f in @("infra\hipo-emails.service", "infra\hipo-emails.timer", "infra\instalar-timer-emails.sh")) {
        & scp -i $Chave (Join-Path $Pasta $f) "${alvo}:/tmp/$(Split-Path $f -Leaf)"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp de $f falhou." }
    }
    & ssh -t -i $Chave $alvo "bash /tmp/instalar-timer-emails.sh"
    if ($LASTEXITCODE -eq 3) { Aviso "timer nao instalado (voce cancelou). Rode de novo com -SoTimer." }
    elseif ($LASTEXITCODE -ne 0) { Abortar "a instalacao do timer falhou (codigo $LASTEXITCODE)." }
    else { Bom "hipo-emails.timer ligado" }
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R. NAO precisa relogar (nenhuma permissao mudou).
  2. Abra uma oportunidade -> aba E-mails -> Novo e-mail. O rascunho do
     primeiro contato vem preenchido para o contato principal.
  3. Primeiro teste: mande para um e-mail PESSOAL seu (o Para e editavel;
     a propria caixa corporativa e recusada como destino) e confira
     a assinatura e o remetente na caixa de entrada.
  4. Na aba Proposta, o botao E-mail de uma versao abre o rascunho com o
     PDF anexado (so aparece se o servidor gera PDF).
  5. Responda o e-mail de teste e clique em "Ver se respondeu".
  Quem tiver usuario do HIPO com e-mail fora do @controllermedseg.com nao
  consegue enviar (a tela diz por que).
"@ -ForegroundColor White
