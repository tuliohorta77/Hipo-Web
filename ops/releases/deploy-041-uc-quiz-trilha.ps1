# =====================================================================
#  HIPO -- deploy 041: UC -- quiz final da trilha, em tela propria
# =====================================================================
#
#  Ajuste da 040 (pedido do Tulio):
#    - as aulas voltam a concluir pela trava de tempo (botao Conclui)
#    - o quiz e UM SO, no FINAL DA TRILHA, numa tela so dele
#      (/uc/trilhas/<id>/quiz): abre quando todas as aulas estao
#      concluidas, sorteia 10 perguntas do banco das aulas, aprova com
#      85% (9 de 10); a trilha so conclui com aprovacao
#    - reprovou: diz quais perguntas e de qual aula rever, nunca a certa;
#      nova tentativa em 10 minutos, com outro sorteio
#    - Estudio: cada aula tem um banco de 0 a 10 perguntas
#  Migration 025 (tabela uc_tentativas_trilha), ANTES do push.
#
#    1. pre-voo      -- arquivos no lugar, base do git, 025 livre, SSH
#    2. testes       -- testes puros do conteudo e do quiz (o CI roda o resto)
#    3. migration    -- 025 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga        -- todas as trilhas, com --atualizar (idempotente)
#
#  USO
#     .\deploy-041-uc-quiz-trilha.ps1 -Simular
#     .\deploy-041-uc-quiz-trilha.ps1
#     .\deploy-041-uc-quiz-trilha.ps1 -SoCarga    (o push ja foi; so a etapa 5)
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

# Commit sobre o qual a entrega foi feita (entrega 040 no ar).
$base = "91e67d3"

$substituidos = @(
    "api\routers\uc.py",
    "api\routers\uc_estudio.py",
    "api\schema.sql",
    "api\scripts\semear_uc.py",
    "api\services\atividade.py",
    "api\services\uc.py",
    "api\tests\test_uc_quiz.py",
    "api\tests\test_uc_regras.py",
    "web\src\App.jsx",
    "web\src\components\uc\EditorQuiz.jsx",
    "web\src\pages\uc\Aula.jsx",
    "web\src\pages\uc\MinhaUC.jsx",
    "web\src\pages\uc\Trilha.jsx",
    "web\src\tests\EditorQuiz.test.jsx",
    "web\src\tests\MinhaUC.test.jsx"
)

$novos = @(
    "api\migrations\025_uc_quiz_trilha.sql",
    "infra\aplicar-025-uc-quiz-trilha.sh",
    "web\src\pages\uc\QuizTrilha.jsx",
    "web\src\tests\QuizTrilha.test.jsx",
    "deploy-041-uc-quiz-trilha.ps1"
)

# A entrega APAGA estes (o quiz saiu da tela da aula). O script remove.
$removidos = @(
    "web\src\components\uc\QuizAula.jsx",
    "web\src\tests\QuizAula.test.jsx"
)

$entrega = $substituidos + $novos

$pdfs = @(
    "infra\uc\apresentacao-controller.pdf",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf",
    "infra\uc\roteiro-vendas.pdf",
    "infra\uc\energia-01.pdf"
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
    if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
    & git merge-base --is-ancestor $base HEAD
    if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
    Bom "base: $base esta no HEAD"
    $git_substituidos = ($substituidos + $removidos) | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

    Passo "migration 025 livre..."
    $outras025 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "025_*.sql" |
        Where-Object { $_.Name -ne "025_uc_quiz_trilha.sql" })
    if ($outras025.Count -gt 0) {
        Abortar "ja existe outra migration 025 ($($outras025[0].Name)). Me avise para renumerar."
    }
    Bom "025 livre"
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
# 2. Testes puros do conteudo
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
            Passo "pytest (conteudo, tour, quiz e regras da UC)..."
            & python -m pytest -q --no-cov tests\test_uc_conteudo.py tests\test_uc_tour_conteudo.py tests\test_uc_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes do conteudo falharam." }
            Bom "conteudo verde"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 025 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 025 no RDS"

$sql    = Join-Path $Pasta "api\migrations\025_uc_quiz_trilha.sql"
$script = Join-Path $Pasta "infra\aplicar-025-uc-quiz-trilha.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 025 (1 tabela nova, aditiva) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/025_uc_quiz_trilha.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da migration falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-025-uc-quiz-trilha.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script da migration falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-025-uc-quiz-trilha.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 025 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 025 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(uc): quiz final da trilha, em tela propria

- Aulas voltam a concluir pela trava de tempo.
- Quiz unico no final da trilha (/uc/trilhas/<id>/quiz): abre com todas
  as aulas concluidas, sorteia 10 perguntas do banco das aulas (rodizio
  entre aulas), aprova com 85% (9 de 10). A trilha so conclui com ele;
  painel e proxima aula apontam para o quiz quando as aulas acabam.
- Reprovou: mostra perguntas e aulas a rever (nunca a certa); nova
  tentativa em 10 min com outro sorteio.
- Estudio: banco de 0 a 10 perguntas por aula.
- Migration 025: uc_tentativas_trilha.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
    $removidos | ForEach-Object { Write-Host "     removeria: $_" -ForegroundColor DarkGray }
} else {
    Confirmar "Commitar a entrega 041 e dar push na main?"
    & git rm -q --ignore-unmatch -- $removidos
    if ($LASTEXITCODE -ne 0) { Abortar "git rm dos arquivos removidos falhou." }
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-041.txt"
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

$marcador = "grep -q QUIZ_TRILHA_PERGUNTAS /home/hipo/app/api/services/uc.py"
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
  1. A carga deve listar as 11 trilhas como atualizadas.
  2. Ctrl+Shift+R no navegador. NAO precisa relogar.
  3. Aula: de novo o botao Conclui. Trilha: ultima linha "Quiz final
     da trilha" (Depois das aulas / Disponivel / Aprovado).
  4. Quem ja tinha concluido todas as aulas de uma trilha ve, em
     Sua proxima aula, "Quiz final da trilha" com o botao Fazer o quiz.
"@ -ForegroundColor White
