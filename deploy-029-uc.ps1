# =====================================================================
#  HIPO -- deploy 029: Universidade Corporativa (UC-1)
# =====================================================================
#
#  Conteudo e manual da funcao: trilhas por pilar (Tecnica, Metodo,
#  Energia), aulas com video por link + texto + material no S3, progresso
#  por versao da aula, tela "Universidade" para todo cargo e estudio para
#  a gestao. Primeira trilha: NR-01 e NR-04, com os PDFs oficiais.
#  Especificacao: claude/universidade-corporativa.md (Project).
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- vitest, build e os testes puros da UC
#    3. migration    -- 020 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega; o CI faz o resto
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga        -- trilha de NR-01/NR-04 + PDFs
#
#  SEM MODULO NOVO: a UC vive no modulo 'crm'. Ninguem precisa relogar e
#  os asserts de modulos_do_cargo ficam como estao.
#
#  USO
#     .\deploy-029-uc.ps1 -Simular
#     .\deploy-029-uc.ps1
#     .\deploy-029-uc.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$PularCarga,

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

# Arquivos EXISTENTES que a entrega substitui (conferidos contra a base).
$substituidos = @(
    "api\main.py",
    "api\schema.sql",
    "api\services\atividade.py",
    "api\tests\test_monitor.py",
    "web\src\App.jsx",
    "web\src\components\Layout.jsx",
    "web\src\tests\Layout.test.jsx"
)

# Todos os arquivos da entrega. E tambem a lista do `git add`.
$entrega = $substituidos + @(
    "api\migrations\020_uc.sql",
    "api\services\uc.py",
    "api\services\uc_material.py",
    "api\routers\uc.py",
    "api\routers\uc_estudio.py",
    "api\scripts\semear_uc_nr.py",
    "api\tests\test_uc.py",
    "api\tests\test_uc_regras.py",
    "api\tests\test_uc_conteudo_nr.py",
    "infra\aplicar-020-uc.sh",
    "infra\semear-uc-nr.sh",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf",
    "web\src\components\uc\ucComum.js",
    "web\src\components\uc\TextoAula.jsx",
    "web\src\components\uc\EditorAula.jsx",
    "web\src\components\uc\EditorTrilha.jsx",
    "web\src\pages\uc\MinhaUC.jsx",
    "web\src\pages\uc\Trilha.jsx",
    "web\src\pages\uc\Aula.jsx",
    "web\src\pages\uc\Estudio.jsx",
    "web\src\tests\ucComum.test.js",
    "web\src\tests\TextoAula.test.jsx",
    "web\src\tests\MinhaUC.test.jsx",
    "web\src\tests\AulaUC.test.jsx",
    "web\src\tests\EstudioUC.test.jsx",
    "deploy-029-uc.ps1"
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

Passo "proxima migration livre..."
$outras020 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "020_*.sql" |
    Where-Object { $_.Name -ne "020_uc.sql" })
if ($outras020.Count -gt 0) {
    Abortar "ja existe outra migration 020 ($($outras020[0].Name)). Me avise para renumerar."
}
Bom "020 livre"

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
# 2. Testes
# =====================================================================

Titulo "2. Testes"
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

    # Os testes puros da UC rodam sem Postgres. Os de rota ficam com o CI.
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            Passo "pytest (regras puras da UC)..."
            & python -m pytest -q --no-cov tests\test_uc_regras.py tests\test_uc_conteudo_nr.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros da UC falharam." }
            Bom "regras da UC verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes de backend ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 020 -- ANTES do push
# =====================================================================

Titulo "3. Migration 020 no RDS"

$sql    = Join-Path $Pasta "api\migrations\020_uc.sql"
$script = Join-Path $Pasta "infra\aplicar-020-uc.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    Write-Host "  A 020 cria uc_trilhas, uc_trilha_cargos, uc_aulas, uc_materiais e uc_progresso." -ForegroundColor Gray
    Write-Host "  Aditiva e idempotente -- nao exige export em CSV." -ForegroundColor Gray
    Confirmar "Aplicar a migration 020 em PRODUCAO ($Servidor)?"

    Passo "enviando os arquivos..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new $sql $script "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "arquivos em /tmp/ no servidor"

    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-020-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 020 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 020 aplicada"
}

# =====================================================================
# 4. Push -- so a entrega
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(uc): Universidade Corporativa -- conteudo e manual da funcao (UC-1)

Modulo UC sobre o 'crm' (sem modulo novo, ninguem reloga):

- Trilhas por pilar (Tecnica, Metodo, Energia), aulas com texto em
  markdown pequeno (renderizado sem innerHTML), video por LINK guardado
  como (provedor, id) -- YouTube, Vimeo, Loom, Drive -- e material de
  apoio no S3 (mesmo bucket dos anexos, prefixo uc/).
- Manual da funcao: trilha obrigatoria por cargo com prazo, contado da
  entrada no cargo ou de quando a trilha virou obrigatoria.
- Progresso por versao da aula: mudanca relevante reabre a pendencia
  sem apagar a conclusao anterior. Concluir sem quiz libera na metade
  da duracao, conferido no servidor (409).
- Tela "Universidade": proxima aula em cartao, tres pilares com
  drilldown, manual da funcao. Gestao abre a UC de qualquer pessoa em
  modo leitura (?usuario_id=).
- Estudio (Franqueado/ADM): trilhas, cargos, aulas, ordem, materiais e
  a visao do time.
- Primeira trilha: NR-01 e NR-04 (6 aulas, PDFs oficiais), carregada
  por scripts/semear_uc_nr.py; o quiz ja esta escrito para a UC-2.
- Corrige test_monitor que caia nos primeiros dias uteis do mes.

Migration 020 (aditiva, idempotente).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-029.txt"
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

$marcador = "/home/hipo/app/api/scripts/semear_uc_nr.py"
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

# =====================================================================
# 6. Carga da trilha de NR-01 e NR-04
# =====================================================================

Titulo "6. Primeira trilha: NR-01 e NR-04"

if ($Simular -or $PularCarga) {
    Aviso "pulado (simulacao ou -PularCarga). Da para rodar depois: bash /tmp/semear-uc-nr.sh"
} else {
    $pdf1 = Join-Path $Pasta "infra\uc\nr-01.pdf"
    $pdf4 = Join-Path $Pasta "infra\uc\nr-04.pdf"
    $carga = Join-Path $Pasta "infra\semear-uc-nr.sh"

    Passo "enviando o script e os PDFs..."
    & scp -i $Chave $carga "${alvo}:/tmp/semear-uc-nr.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    & scp -i $Chave $pdf1 "${alvo}:/tmp/nr-01.pdf"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da NR-01 falhou." }
    & scp -i $Chave $pdf4 "${alvo}:/tmp/nr-04.pdf"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da NR-04 falhou." }
    Bom "arquivos em /tmp/"

    & ssh -t -i $Chave $alvo "bash /tmp/semear-uc-nr.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a carga falhou (codigo $LASTEXITCODE). A UC esta no ar; a trilha nao." }
    Bom "trilha carregada"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador (assets novos). NAO precisa relogar: a
     UC vive no modulo 'crm'.
  2. Barra de cima > Universidade. O cartao "Sua proxima aula" abre na
     aula 1 da trilha de NR (obrigatoria para SDR, EV, EC, EP e ADM,
     prazo de 30 dias a partir de hoje).
  3. Abra a aula 1 e o PDF da NR-01 em "Material de apoio". Se der 503,
     o S3_BUCKET_ANEXOS nao chegou ao processo da API.
  4. Gestao: botao Estudio > aba Time mostra o andamento de cada pessoa;
     clicar abre a UC dela em modo leitura.
"@ -ForegroundColor White
