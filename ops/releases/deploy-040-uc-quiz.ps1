# =====================================================================
#  HIPO -- deploy 040: UC -- quiz depois da aula
# =====================================================================
#
#  A trava de tempo garante presenca, nao entendimento. Agora:
#    - toda aula das trilhas carregadas tem quiz de 7 perguntas
#      (298 novas, escritas a partir do texto de cada aula)
#    - aprova com 85% (6 de 7); o quiz so abre depois do tempo minimo
#    - reprovou: ve QUAIS perguntas errou (nunca a certa), alternativas
#      reembaralhadas e nova tentativa em 10 minutos
#    - aula com quiz nao tem mais o botao Conclui; quem ja concluiu continua
#    - Estudio: a gestao escreve o quiz de qualquer aula (7 ou nenhuma)
#  Migration 024 (3 tabelas novas + nota minima 85), ANTES do push.
#
#    1. pre-voo      -- arquivos no lugar, base do git, 024 livre, SSH
#    2. testes       -- testes puros do conteudo e do quiz (o CI roda o resto)
#    3. migration    -- 024 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga        -- todas as trilhas, com --atualizar: grava os quizzes
#
#  USO
#     .\deploy-040-uc-quiz.ps1 -Simular
#     .\deploy-040-uc-quiz.ps1
#     .\deploy-040-uc-quiz.ps1 -SoCarga    (o push ja foi; so a etapa 5)
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

# Commit sobre o qual a entrega foi feita (entrega 039 no ar).
$base = "e2dc67d"

$substituidos = @(
    "api\routers\uc.py",
    "api\routers\uc_estudio.py",
    "api\schema.sql",
    "api\scripts\semear_uc.py",
    "api\scripts\uc_conteudo.py",
    "api\scripts\uc_conteudo_energia.py",
    "api\scripts\uc_conteudo_hipo.py",
    "api\scripts\uc_conteudo_roteiros.py",
    "api\services\atividade.py",
    "api\services\uc.py",
    "api\tests\test_uc_conteudo.py",
    "api\tests\test_uc_regras.py",
    "web\src\components\uc\EditorAula.jsx",
    "web\src\pages\uc\Aula.jsx"
)

$novos = @(
    "api\migrations\024_uc_quiz.sql",
    "api\tests\test_uc_quiz.py",
    "infra\aplicar-024-uc-quiz.sh",
    "web\src\components\uc\EditorQuiz.jsx",
    "web\src\components\uc\QuizAula.jsx",
    "web\src\tests\EditorQuiz.test.jsx",
    "web\src\tests\QuizAula.test.jsx",
    "deploy-040-uc-quiz.ps1"
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
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

    Passo "migration 024 livre..."
    $outras024 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "024_*.sql" |
        Where-Object { $_.Name -ne "024_uc_quiz.sql" })
    if ($outras024.Count -gt 0) {
        Abortar "ja existe outra migration 024 ($($outras024[0].Name)). Me avise para renumerar."
    }
    Bom "024 livre"
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
# 3. Migration 024 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 024 no RDS"

$sql    = Join-Path $Pasta "api\migrations\024_uc_quiz.sql"
$script = Join-Path $Pasta "infra\aplicar-024-uc-quiz.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 024 (3 tabelas novas, nao destrutiva) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/024_uc_quiz.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da migration falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-024-uc-quiz.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script da migration falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-024-uc-quiz.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 024 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 024 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(uc): quiz depois da aula -- 7 perguntas, 85% para aprovar

- Aula com quiz so conclui com aprovacao (6 de 7); o quiz so abre
  depois do tempo minimo da aula. Reprovou: mostra quais perguntas
  errou (nunca a certa), reembaralha e libera nova tentativa em 10 min.
- Gabarito nunca vai ao navegador; correcao, nota e esperas no servidor.
- Todas as 76 aulas carregadas com 7 perguntas (298 novas).
- Estudio: editor de quiz (7 perguntas ou nenhuma, 3 a 5 alternativas,
  uma correta). Aula sem quiz segue no Conclui com a trava de tempo.
- Migration 024: uc_perguntas, uc_alternativas, uc_tentativas;
  nota_minima 85.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 040 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-040.txt"
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

$marcador = "grep -q PERGUNTAS_POR_QUIZ /home/hipo/app/api/services/uc.py"
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
  3. Abra uma aula ainda nao concluida: no fim, o card "Quiz da aula"
     (trancado ate a metade da duracao), sem o botao Conclui.
  4. Estudio > trilha > aula: a secao Quiz mostra as 7 perguntas com
     a correta marcada.
"@ -ForegroundColor White
