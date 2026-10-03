# =====================================================================
#  HIPO -- deploy 035: UC -- trilhas de uso do HIPO por funcao + tour
# =====================================================================
#
#  Tres trilhas no pilar Metodo, uma por funcao, obrigatorias so para
#  o proprio cargo (ADM e Franqueado veem as tres sem obrigacao):
#    HIPO - SDR (7 aulas)   HIPO - EV (7 aulas)   HIPO - EC (6 aulas)
#  Cada aula tem o botao "Me mostra no HIPO": abre a tela real e um
#  balao destaca cada elemento explicado (tour guiado). O tour so
#  mostra -- nao cria nem altera dado nenhum.
#
#    1. pre-voo      -- arquivos no lugar, base do git, migration livre, SSH
#    2. testes       -- testes puros (conteudo, tour, regras da UC)
#    3. migration    -- 023 no RDS (coluna uc_aulas.tour), ANTES do push
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga        -- as trilhas (todas, com --atualizar) + PDFs
#
#  USO
#     .\deploy-035-uc-hipo.ps1 -Simular
#     .\deploy-035-uc-hipo.ps1
#     .\deploy-035-uc-hipo.ps1 -SoCarga    (o push ja foi; so a etapa 6)
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoCarga,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    # O CI completo (testes + build + deploy) passa de 15 min em dia cheio.
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

# Commit sobre o qual a entrega foi feita (cargo UC, entrega 034).
$base = "fba2a4d"

# Arquivos EXISTENTES que a entrega substitui.
$substituidos = @(
    "api\routers\uc.py",
    "api\routers\uc_estudio.py",
    "api\schema.sql",
    "api\scripts\semear_uc.py",
    "api\scripts\uc_conteudo.py",
    "api\services\uc.py",
    "api\tests\test_uc.py",
    "api\tests\test_uc_conteudo.py",
    "api\tests\test_uc_regras.py",
    "web\src\components\Layout.jsx",
    "web\src\components\crm\AbaTarefas.jsx",
    "web\src\components\crm\ContaDetalhe.jsx",
    "web\src\components\crm\DesfechoReuniao.jsx",
    "web\src\components\crm\FiltrosOportunidades.jsx",
    "web\src\components\crm\KanbanOportunidades.jsx",
    "web\src\components\crm\ModalDesfecho.jsx",
    "web\src\components\crm\ModalReuniao.jsx",
    "web\src\components\crm\OportunidadeDetalhe.jsx",
    "web\src\components\crm\ParceiroDetalhe.jsx",
    "web\src\components\crm\tarefaComum.jsx",
    "web\src\components\uc\EditorAula.jsx",
    "web\src\components\uc\EditorTrilha.jsx",
    "web\src\components\ui\Tabs.jsx",
    "web\src\pages\Monitor.jsx",
    "web\src\pages\crm\Agenda.jsx",
    "web\src\pages\crm\Contas.jsx",
    "web\src\pages\crm\Oportunidades.jsx",
    "web\src\pages\crm\Parceiros.jsx",
    "web\src\pages\crm\Prospeccao.jsx",
    "web\src\pages\crm\Relatorios.jsx",
    "web\src\pages\crm\Tarefas.jsx",
    "web\src\pages\uc\Aula.jsx",
    "web\src\pages\uc\MinhaUC.jsx",
    "web\src\tests\AulaUC.test.jsx"
)

$novos = @(
    "api\migrations\023_uc_tour.sql",
    "api\scripts\uc_conteudo_hipo.py",
    "api\tests\test_uc_tour_conteudo.py",
    "web\src\components\uc\TourGuiado.jsx",
    "web\src\components\uc\tour.js",
    "web\src\tests\TourGuiado.test.jsx",
    "web\src\tests\tour.test.js",
    "infra\aplicar-023-uc-tour.sh",
    "deploy-035-uc-hipo.ps1"
)

# Todos os arquivos da entrega (o que vai no `git add`).
$entrega = $substituidos + $novos

# Os PDFs das trilhas anteriores (a carga roda tudo de novo, idempotente).
$pdfs = @(
    "infra\uc\apresentacao-controller.pdf",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf",
    "infra\uc\roteiro-vendas.pdf"
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

$faltando = @(($entrega + $pdfs + @("infra\semear-uc.sh")) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega e PDFs conferidos"

if (-not $SoCarga) {
    & git cat-file -e "$base^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) { Abortar "o commit $base (entrega 034) nao esta no git daqui. Rode 'git pull'." }
    & git merge-base --is-ancestor $base HEAD
    if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
    Bom "base: $base (entrega 034) esta no HEAD"
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois da 034 mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois da 034 mexeu nos arquivos substituidos"

    Passo "migration 023 livre..."
    $outras023 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "023_*.sql" |
        Where-Object { $_.Name -ne "023_uc_tour.sql" })
    if ($outras023.Count -gt 0) {
        Abortar "ja existe outra migration 023 ($($outras023[0].Name)). Me avise para renumerar."
    }
    Bom "023 livre"
}

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para aplicar a migration nem carregar as trilhas."
}
Bom "porta 22 responde"

if (-not $SoCarga) {

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
            Passo "pytest (conteudo, tour e regras da UC)..."
            & python -m pytest -q --no-cov tests\test_uc_conteudo.py tests\test_uc_tour_conteudo.py tests\test_uc_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes do conteudo falharam." }
            Bom "conteudo e tour verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes de backend ficam so com o CI"
    }
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if ($npx -and (Test-Path (Join-Path $Pasta "web\node_modules"))) {
        Push-Location (Join-Path $Pasta "web")
        try {
            Passo "vitest (tour e aula)..."
            & npx vitest run src/tests/tour.test.js src/tests/TourGuiado.test.jsx src/tests/AulaUC.test.jsx src/tests/Layout.test.jsx
            if ($LASTEXITCODE -ne 0) { Abortar "testes do front falharam." }
            Bom "front verde"
        } finally { Pop-Location }
    } else {
        Aviso "sem node_modules no web -- os testes do front ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 023 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 023 no RDS"

$sql    = Join-Path $Pasta "api\migrations\023_uc_tour.sql"
$script = Join-Path $Pasta "infra\aplicar-023-uc-tour.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 023 (coluna nova, aditiva) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/023_uc_tour.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da migration falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-023-uc-tour.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script da migration falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-023-uc-tour.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 023 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 023 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(uc): trilhas de uso do HIPO por funcao, com tour guiado na tela real

- Tres trilhas no pilar Metodo, obrigatorias so para o proprio cargo
  (ADM e Franqueado veem as tres): HIPO - SDR (prospeccao, fila de
  contato, funil, agenda para o EV, contas, numeros), HIPO - EV (funil,
  oportunidade por dentro, proposta e fechamento, follow-up, agenda com
  desfecho/transcricao/scorecard, contas, relatorios, monitor) e
  HIPO - EC (carteira de parceiros, farol, tarefas e reunioes de
  parceiro, indicacoes com Finder, numeros da carteira). Prazo 15 dias.
- Tour guiado: toda aula de uso tem "Me mostra no HIPO". Abre a tela
  real; um balao destaca cada elemento (atributos data-tour nas telas),
  abre cartao/aba/formulario em branco quando o passo pede e volta para
  a aula no fim. A camada do tour bloqueia o mouse: nada e gravado.
- Migration 023: uc_aulas.tour JSONB (aditiva). Validado em
  services/uc.validar_tour; a API da aula devolve o tour; o estudio
  mostra quantos passos a aula tem.
- Testes: as ancoras usadas pelo conteudo existem no front, o tour so
  clica no que abre e so passa por tela que o cargo enxerga.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 035 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-035.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, rode com -SoCarga." }
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

$marcador = "/home/hipo/app/api/scripts/uc_conteudo_hipo.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo "test -f $marcador" 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoCarga."
        exit 1
    }
    Bom "codigo novo no servidor"
}

}  # fim do if (-not $SoCarga)

# =====================================================================
# 6. Carga das trilhas
# =====================================================================

Titulo "6. Carga das trilhas da UC"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem carregar nada"
} else {
    Passo "enviando o script e os PDFs..."
    & ssh -i $Chave $alvo "mkdir -p /tmp/uc"
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar /tmp/uc no servidor." }
    & scp -i $Chave (Join-Path $Pasta "infra\semear-uc.sh") "${alvo}:/tmp/semear-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    foreach ($p in $pdfs) {
        & scp -i $Chave (Join-Path $Pasta $p) "${alvo}:/tmp/uc/"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp de $p falhou." }
    }
    Bom "arquivos em /tmp/ no servidor"

    & ssh -t -i $Chave $alvo "bash /tmp/semear-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a carga falhou (codigo $LASTEXITCODE). Rode de novo com -SoCarga depois de corrigir." }
    Bom "trilhas carregadas"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador. NAO precisa relogar.
  2. Universidade como SDR, EV ou EC: o Manual da funcao ganha a trilha
     HIPO do proprio cargo (so a dele). Gestao ve as tres em Outras.
  3. Abra uma aula da trilha HIPO: o bloco "Veja na pratica" lista os
     passos. Clique em "Me mostra no HIPO": a tela real abre com o balao.
     Setas/Enter avancam, Esc sai, o ultimo passo volta para a aula.
  4. Estudio > HIPO - EV: cada aula mostra "tour de N passos".
"@ -ForegroundColor White
