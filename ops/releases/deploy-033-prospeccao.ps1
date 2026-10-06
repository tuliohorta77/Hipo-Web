# =====================================================================
#  HIPO -- deploy 033: Prospeccao a partir da base da Receita
# =====================================================================
#
#  Tela nova (Prospeccao) para SDR e gestao: fatia a base de Dados
#  Abertos do CNPJ por UF, CNAE e cidade e PUXA empresas para o CRM
#  (conta + oportunidade em suspect + tarefa de primeiro contato).
#
#  TEM MIGRATION (022, aditiva). Ninguem precisa relogar: a permissao e
#  por cargo dentro do modulo 'crm', sem mexer em modulos_do_cargo.
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- testes puros (o CI roda o resto)
#    3. migration    -- 022 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga        -- opcional (-Carga): a primeira base da Receita
#
#  USO
#     .\deploy-033-prospeccao.ps1 -Simular
#     .\deploy-033-prospeccao.ps1
#     .\deploy-033-prospeccao.ps1 -SoCarga -Ufs SP -Referencia 2026-09 -Espelho https://...
#
#  A carga pode rodar a qualquer momento depois do push; sem ela a tela
#  mostra "a base ainda nao foi carregada". Rodar fora do horario.
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoCarga,
    [switch]$Carga,

    [string]$Ufs        = "SP",
    [string]$Referencia = "",
    [string]$Espelho    = "",

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
$BASE_GIT = "eab75a2"

# Arquivos EXISTENTES que a entrega substitui.
$substituidos = @(
    "api\main.py",
    "api\schema.sql",
    "api\routers\crm_oportunidades.py",
    "api\routers\crm_tarefas.py",
    "api\routers\permissions.py",
    "api\services\atividade.py",
    "api\tests\conftest.py",
    "web\src\App.jsx",
    "web\src\components\Layout.jsx",
    "web\src\tests\Layout.test.jsx"
)

$entrega = $substituidos + @(
    "api\migrations\022_base_receita.sql",
    "api\routers\crm_prospeccao.py",
    "api\services\prospeccao.py",
    "api\services\receita_carga.py",
    "api\scripts\carregar_base_receita.py",
    "api\tests\test_prospeccao_regras.py",
    "api\tests\test_receita_carga.py",
    "api\tests\test_crm_prospeccao.py",
    "web\src\pages\crm\Prospeccao.jsx",
    "web\src\components\crm\SeletorComBusca.jsx",
    "web\src\tests\Prospeccao.test.jsx",
    "infra\aplicar-022-base-receita.sh",
    "infra\carregar-base-receita.sh",
    "deploy-033-prospeccao.ps1"
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

if ($Carga -or $SoCarga) {
    if (-not $Referencia) { Abortar "a carga precisa de -Referencia (ex.: 2026-09)." }
}

if (-not $SoCarga) {
    $faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
    if ($faltando.Count -gt 0) {
        foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
        Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
    }
    Bom "arquivos da entrega conferidos"

    & git cat-file -e "$BASE_GIT^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) { Abortar "o commit base $BASE_GIT nao esta no git daqui. Rode 'git pull'." }
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $BASE_GIT HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois de $BASE_GIT mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois de $BASE_GIT mexeu nos arquivos substituidos"
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
    Abortar "sem SSH nao da para aplicar a migration."
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
            Passo "pytest (regras da prospeccao e parser da Receita)..."
            & python -m pytest -q --no-cov tests\test_prospeccao_regras.py tests\test_receita_carga.py -k "not TestCarga"
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "testes puros verdes (os de banco ficam com o CI)"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 022 (ANTES do push)
# =====================================================================

Titulo "3. Migration 022"
if ($Simular) {
    Aviso "simulacao: nao vou mandar nem aplicar nada"
} else {
    & scp -i $Chave (Join-Path $Pasta "api\migrations\022_base_receita.sql") "${alvo}:/tmp/022_base_receita.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da migration falhou." }
    & scp -i $Chave (Join-Path $Pasta "infra\aplicar-022-base-receita.sh") "${alvo}:/tmp/aplicar-022-base-receita.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-022-base-receita.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration falhou (codigo $LASTEXITCODE). Nada foi enviado ao git." }
    Bom "migration 022 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(prospeccao): fatia da base da Receita e puxar para o HIPO

Tela nova para SDR e gestao. A base de Dados Abertos do CNPJ (so
ativas, sem MEI, recortada pelas UFs de atuacao) fica ao lado do CRM
como fonte de CONSULTA; nada dela vira registro sem um gesto
autenticado.

- Migration 022: receita_estabelecimentos, receita_municipios,
  receita_cnaes e receita_cargas. Aditiva, idempotente.
- scripts/carregar_base_receita.py: carga mensal a partir dos ZIPs
  (pasta local ou espelho). Monta a tabela nova ao lado e troca numa
  transacao curta; falha no meio deixa a base anterior intacta.
- /crm/prospeccao: fatia por UF + CNAE (prefixo vira faixa), cidade,
  porte, regime, idade e capital; resumo com a situacao de cada CNPJ
  no CRM (nova, sem negocio, em negociacao, cliente, bloqueada).
- POST /crm/prospeccao/puxar: ate 50 por vez. Conta (ou a existente),
  oportunidade em suspect com o SDR envolvido e origem "Base da
  Receita", tarefa de primeiro contato. Enriquecimento BrasilAPI em
  segundo plano. Nunca abre segunda oportunidade, nem em cliente nem
  em conta bloqueada.
- Permissao por cargo (SDR + gestao) dentro do modulo 'crm': ninguem
  precisa relogar.
- crm_oportunidades: o INSERT virou inserir_oportunidade(), usado pelo
  POST e pela prospeccao.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 033 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-033.txt"
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

$marcador = "/home/hipo/app/api/routers/crm_prospeccao.py"
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
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."
        exit 1
    }
    Bom "codigo novo no servidor"
}

}  # fim do if (-not $SoCarga)

# =====================================================================
# 6. Carga da base (opcional)
# =====================================================================

if ($Carga -or $SoCarga) {
    Titulo "6. Carga da base da Receita ($Ufs, $Referencia)"
    if ($Simular) {
        Aviso "simulacao: nao vou carregar nada"
    } else {
        & scp -i $Chave (Join-Path $Pasta "infra\carregar-base-receita.sh") "${alvo}:/tmp/carregar-base-receita.sh"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp do script de carga falhou." }
        $cmd = "bash /tmp/carregar-base-receita.sh $Ufs $Referencia"
        if ($Espelho) { $cmd = "$cmd $Espelho" }
        & ssh -t -i $Chave $alvo $cmd
        if ($LASTEXITCODE -ne 0) { Abortar "a carga falhou (codigo $LASTEXITCODE). A base anterior continua no ar." }
        Bom "base carregada"
    }
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador. NAO precisa relogar.
  2. SDR e gestao veem 'Prospeccao' abrindo a barra. EV, EC e EP nao.
  3. Sem a carga, a tela diz que a base ainda nao foi carregada:
       .\deploy-033-prospeccao.ps1 -SoCarga -Ufs SP -Referencia 2026-09 [-Espelho URL]
  4. Depois da carga: UF SP, CNAE 41, puxar 2 empresas e conferir em
     Tarefas os dois 'Primeiro contato'.
"@ -ForegroundColor White
