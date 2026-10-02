# =====================================================================
#  HIPO -- deploy 033: UC -- pilar Metodo e tecnicas de venda
# =====================================================================
#
#  Conteudo, sem migration e sem tela nova:
#    04 Tecnicas de venda consultiva (Tecnica, 7 aulas): Sandler, SPIN,
#       GPCT + BA/C&I, Challenger, LAER, escuta e fechamento, a fundo.
#    Metodo 01 Roteiro de vendas Controller (Metodo, 10 aulas): a
#       aplicacao na Controller, do preparo ao scorecard, com o PDF do
#       roteiro anexado. Reforca a medida "roteiro" (PDI).
#  As duas sao obrigatorias para SDR, EV e EC; EP, ADM e Franqueado
#  fazem sem obrigacao. 01 a 03 nao mudam de conteudo.
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- testes puros do conteudo (o CI roda o resto)
#    3. push         -- SO os arquivos da entrega
#    4. espera       -- ate o codigo novo chegar no servidor
#    5. carga        -- as trilhas + PDFs, com --atualizar
#
#  Se a carga da 032 ainda nao tinha rodado, esta faz tudo de uma vez.
#
#  USO
#     .\deploy-033-uc-metodo.ps1 -Simular
#     .\deploy-033-uc-metodo.ps1
#     .\deploy-033-uc-metodo.ps1 -SoCarga    (o push ja foi; so a etapa 5)
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

# Arquivos EXISTENTES que a entrega substitui.
$substituidos = @(
    "api\scripts\uc_conteudo.py",
    "api\scripts\semear_uc.py",
    "api\tests\test_uc.py",
    "api\tests\test_uc_conteudo.py",
    "infra\semear-uc.sh"
)

$removidos = @()

# Todos os arquivos da entrega (o que vai no `git add`).
$entrega = $substituidos + @(
    "infra\uc\roteiro-vendas.pdf",
    "deploy-033-uc-metodo.ps1"
)

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


$faltando = @(($entrega + $pdfs) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega e PDFs conferidos"

if (-not $SoCarga) {
    # A base e o commit da 032: o ultimo que mexeu no conteudo da UC.
    $base = (& git log -1 --format=%h -- api/scripts/uc_conteudo.py).Trim()
    if (-not $base) { Abortar "a entrega 032 (trilhas iniciais) nao esta no git daqui. Rode 'git pull'." }
    Bom "base: $base (entrega 032)"
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois da 032 mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois da 032 mexeu nos arquivos substituidos"
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
    Abortar "sem SSH nao da para carregar as trilhas."
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
            Passo "pytest (conteudo e regras da UC)..."
            & python -m pytest -q --no-cov tests\test_uc_conteudo.py tests\test_uc_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes do conteudo falharam." }
            Bom "conteudo verde"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(uc): pilar Metodo -- roteiro de vendas + tecnicas de venda consultiva

- 04 Tecnicas de venda consultiva (pilar Tecnica, prazo 40 dias): as
  tecnicas a fundo -- venda consultiva, contrato de abertura (Sandler),
  SPIN (necessidade implicita x explicita), GPCT + BA/C&I, insight
  Challenger, LAER, escuta ativa, beneficio x recurso e fechamento.
- Metodo 01 Roteiro de vendas Controller (pilar Metodo, prazo 45 dias,
  reforca "roteiro"): a aplicacao na Controller a partir do roteiro de
  30/09 -- reuniao de 45 min, preparo e hipoteses de dor, abertura,
  diagnostico SPIN, GPCT com regra de avanco, apresentacao reordenada,
  9 objecoes com LAER, fechamento por situacao, pos-reuniao e cadencia
  D+2..D+21, scorecard de 10 itens, metricas e rotina de implantacao.
  PDF do roteiro anexado.
- Obrigatorias para SDR, EV e EC; abertas a EP, ADM e Franqueado.
  Cada trilha do conteudo agora declara os proprios cargos.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 033 e dar push na main?"
    foreach ($r in $removidos) {
        $g = $r.Replace("\", "/")
        & git ls-files --error-unmatch -- $g 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & git rm -q -- $g
            if ($LASTEXITCODE -ne 0) { Abortar "git rm $g falhou." }
        }
    }
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-033.txt"
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
# 4. Espera o codigo novo
# =====================================================================

Titulo "4. Esperando o CI"

$marcador = "/home/hipo/app/api/scripts/uc_conteudo.py"
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
# 5. Carga das trilhas
# =====================================================================

Titulo "5. Carga das trilhas da UC"

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
  2. Universidade (como SDR, EV ou EC): o Manual da funcao mostra 01, 02,
     03, 04 e Metodo 01. O cartao do pilar Metodo deixa de mostrar o traco.
  3. Metodo 01 > aula 1: o PDF do roteiro em Material de apoio.
  4. Estudio > Trilhas: o pilar Metodo com "Roteiro de vendas Controller".
"@ -ForegroundColor White
