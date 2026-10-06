# =====================================================================
#  HIPO -- deploy 047: temperatura do contato (quente / morno / frio)
# =====================================================================
#
#  Sinal colorido em cada contato (comite da oportunidade e ficha da
#  conta), calculado no servidor pelas tarefas CONCLUIDAS com a pessoa:
#  quantidade, recencia (14/30/60 dias) e sucesso (reuniao ou visita
#  realizada vale o dobro). Futura, aberta e cancelada (inclui no-show)
#  nao contam. Regra em api/services/temperatura_contato.py.
#
#  SEM migration: so le tarefas.contato_id, que a 028 ja criou.
#  Leva junto o infra\aplicar-028 corrigido, que ficou fora do commit 045.
#
#  TREINAMENTO NA UC (MedSeg), no mesmo deploy:
#    - 04 . Tecnicas do SDR, aula 11 (Multithreading): secao "A
#      temperatura de cada pessoa", tour e quiz atualizados.
#    - Trilhas do HIPO (SDR e EV): aula da oportunidade cita a aba
#      Contatos e o sinal, com passo novo no tour guiado.
#
#    1. pre-voo   -- arquivos, base do git, SSH
#    2. testes    -- regra pura + conteudo da UC (o CI roda o resto)
#    3. push      -- SO os arquivos da entrega
#    4. espera    -- o codigo novo chegar no servidor
#    5. carga UC  -- infra/semear-uc.sh (so a base da MedSeg)
#
#  USO
#     .\deploy-047-temperatura-contato.ps1 -Simular
#     .\deploy-047-temperatura-contato.ps1
#     .\deploy-047-temperatura-contato.ps1 -SoCarga   (push ja feito)
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

# Commit sobre o qual a entrega foi feita (entrega 045). A 046 (instancia MOS)
# veio depois e nao mexe em nenhum arquivo desta entrega.
$base = "a7bc8b5"

$substituidos = @(
    "api\routers\crm_oportunidade_contatos.py",
    "api\routers\crm_contas.py",
    "web\src\components\crm\contatoComum.jsx",
    "web\src\components\crm\AbaContatos.jsx",
    "web\src\components\crm\ContatosDaConta.jsx",
    "web\src\tests\ContatosMultithreading.test.jsx",
    "api\scripts\uc_conteudo_hipo.py",
    "api\scripts\uc_conteudo_tecnicas_sdr.py"
)

$novos = @(
    "api\services\temperatura_contato.py",
    "api\tests\test_temperatura_contato.py",
    "infra\aplicar-028-contatos-multithreading.sh",
    "deploy-047-temperatura-contato.ps1"
)

$entrega = $substituidos + $novos

$pdfs = @(
    "infra\uc\apresentacao-controller.pdf",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf",
    "infra\uc\roteiro-vendas.pdf",
    "infra\uc\energia-01.pdf"
)

$alvo = "$Usuario@$Servidor"

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

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para carregar a UC."
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
            Passo "pytest (regra da temperatura)..."
            & python -m pytest -q --no-cov tests\test_temperatura_contato.py -k TestRegra
            if ($LASTEXITCODE -ne 0) { Abortar "testes da regra falharam." }
            Bom "regra verde"
            Passo "pytest (conteudo e tour da UC)..."
            & python -m pytest -q --no-cov tests\test_uc_conteudo.py tests\test_uc_tour_conteudo.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes do conteudo da UC falharam." }
            Bom "conteudo da UC verde"
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
feat(crm): temperatura do contato -- quente, morno ou frio (entrega 047)

- services/temperatura_contato.py: pontua as tarefas CONCLUIDAS com a
  pessoa por recencia (14/30/60 dias = 3/2/1) e sucesso (reuniao ou
  visita realizada vale o dobro). Quente: >= 6 pontos e conversa nos
  ultimos 14 dias; morno: >= 2; frio: o resto. Futura, aberta e
  cancelada (inclui no-show) nao contam.
- Comite da oportunidade e ficha da conta trazem a temperatura; sinal
  colorido clicavel (mostra o porque) em AbaContatos e ContatosDaConta.
- infra/aplicar-028: entende o "s" do ssh do Windows e cancela com erro.
- UC: aula 11 (Multithreading) ensina a temperatura de cada pessoa
  (secao, tour e quiz); trilhas do HIPO SDR e EV citam a aba Contatos
  e o sinal, com passo novo no tour.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TdwP9HqjtML3bRqWFKW4Qr
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 047 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-047.txt"
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

$marcador = "test -f /home/hipo/app/api/services/temperatura_contato.py"
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
# 5. Carga das trilhas da UC (MedSeg)
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
  1. Ctrl+Shift+R. NAO precisa relogar.
  2. Oportunidade > aba Contatos: cada pessoa com Quente / Morno / Frio.
     Clique no sinal para ver quantas conversas e quando foi a ultima.
  3. Ficha da conta: o mesmo sinal ao lado do nome.
  4. UC > 04 . Tecnicas do SDR > aula 11: secao "A temperatura de cada
     pessoa" e o tour com o passo "Temperatura por pessoa".
"@ -ForegroundColor White
