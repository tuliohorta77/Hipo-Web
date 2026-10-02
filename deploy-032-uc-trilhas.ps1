# =====================================================================
#  HIPO -- deploy 032: UC -- trilhas iniciais 01, 02 e 03
# =====================================================================
#
#  Conteudo + um ajuste na regra da proxima aula. Sem migration, sem
#  tela nova, ninguem precisa relogar.
#    01 Boas-vindas a Controller (4 aulas, apresentacao institucional)
#    02 Conceitos gerais de SST  (4 aulas)
#    03 Produto e normas         (1 aula de produto + as 6 de NR da 029)
#
#  A trilha de NR carregada na 029 VIRA a 03 (mesmo id): ninguem perde
#  conclusao. A carga antiga (semear_uc_nr.py) sai do repositorio.
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- testes puros do conteudo (o CI roda o resto)
#    3. push         -- SO os arquivos da entrega (+ git rm dos antigos)
#    4. espera       -- ate o codigo novo chegar no servidor
#    5. carga        -- as tres trilhas + PDFs, com --atualizar
#
#  USO
#     .\deploy-032-uc-trilhas.ps1 -Simular
#     .\deploy-032-uc-trilhas.ps1
#     .\deploy-032-uc-trilhas.ps1 -SoCarga    (o push ja foi; so a etapa 5)
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
    "api\services\uc.py",
    "api\tests\test_uc.py",
    "api\tests\test_uc_regras.py"
)

# Arquivos da 029 que saem do repositorio.
$removidos = @(
    "api\scripts\semear_uc_nr.py",
    "api\tests\test_uc_conteudo_nr.py",
    "infra\semear-uc-nr.sh"
)

# Todos os arquivos da entrega (o que vai no `git add`).
$entrega = $substituidos + @(
    "api\scripts\uc_conteudo.py",
    "api\scripts\semear_uc.py",
    "api\tests\test_uc_conteudo.py",
    "infra\semear-uc.sh",
    "infra\uc\apresentacao-controller.pdf",
    "deploy-032-uc-trilhas.ps1"
)

$pdfs = @(
    "infra\uc\apresentacao-controller.pdf",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf"
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

# Esta entrega nasceu com o numero 030, que ja era do scorecard. A copia
# com o nome antigo nao e de nenhum commit: sai daqui para nao confundir.
$antigo = Join-Path $Pasta "deploy-030-uc-trilhas.ps1"
if ((Test-Path $antigo) -and -not $Simular) {
    Remove-Item $antigo
    Bom "removido deploy-030-uc-trilhas.ps1 (nome antigo desta entrega)"
}

$faltando = @(($entrega + $pdfs) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega e PDFs conferidos"

if (-not $SoCarga) {
    # A base e o commit da 029: o ultimo que mexeu em api/routers/uc.py.
    $base = (& git log -1 --format=%h -- api/routers/uc.py).Trim()
    if (-not $base) { Abortar "a entrega 029 (UC-1) nao esta no git daqui. Rode 'git pull'." }
    Bom "base: $base (entrega 029)"
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois da 029 mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois da 029 mexeu nos arquivos substituidos"
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
feat(uc): trilhas iniciais -- 01 Boas-vindas, 02 Conceitos de SST, 03 Produto e normas

Conteudo da Universidade Corporativa, todas no pilar Tecnica e
obrigatorias para SDR, EV, EC, EP e ADM (abertas ao Franqueado):

- 01 Boas-vindas a Controller (prazo 10 dias): historia desde 1991,
  numeros, as quatro frentes do portfolio, diferenciais e como se
  trabalha no HIPO. Apresentacao institucional anexada.
- 02 Conceitos gerais de SST (prazo 20 dias): NRs e quem faz o que,
  PGR/PCMSO/ASO/LTCAT e laudos, exames ocupacionais, eventos de SST do
  eSocial.
- 03 Produto e normas (prazo 30 dias): cada servico ligado a norma que
  o exige + as 6 aulas de NR-01 e NR-04. Mesmo id da trilha de NR da
  029: a carga renomeia e nao apaga conclusao de ninguem.

scripts/semear_uc.py (com uc_conteudo.py) substitui semear_uc_nr.py:
upsert por id, aulas do conteudo nas posicoes 1..n, aula criada no
estudio vai para o fim, cargo e prazo mudados no estudio ficam.

Proxima aula: toda obrigatoria em dia fica na mesma faixa e o PRAZO
decide. O manual anda na ordem da gestao (01 antes da 03) mesmo com
aula da 03 ja adiantada.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TAbGttNS1xApzbCt2KPjpb
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 032 e dar push na main?"
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
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-032.txt"
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

Titulo "5. Carga das trilhas 01, 02 e 03"

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
  2. Universidade: o Manual da funcao mostra 01, 02 e 03, nessa ordem.
     A proxima aula e "Bem-vindo(a) a Controller" (prazo de 10 dias).
  3. Voce (Franqueado) ve as tres em "Outras trilhas", sem prazo.
  4. Estudio > Time: SDR, EV e EC com 0/3 no manual.
"@ -ForegroundColor White
