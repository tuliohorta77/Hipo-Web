# =====================================================================
#  HIPO -- deploy 049: migrations aplicadas pelo CI e pelo deploy
# =====================================================================
#
#  O que entra:
#    * api/scripts/aplicar_migrations.py: aplica as pendentes em ordem,
#      registra cada uma em schema_migrations (nome + SHA-256) e trava
#      migration editada depois de aplicada, numero repetido, merge fora
#      de ordem, BEGIN/COMMIT dentro do arquivo e destrutiva sem export.
#    * CI: o banco de teste sobe pelas migrations (000 -> 029), nao mais
#      pelo schema.sql. O schema.sql vira snapshot de referencia; o CI
#      avisa quando ele diverge e publica um pg_dump como artefato.
#    * Deploy: as migrations rodam na EC2 (principal e MOS) ANTES do rsync
#      e do restart. Fim do "migration a mao antes do push".
#    * 000_base_pre_crm.sql (usuarios + dia_nao_util de antes da 001) e a
#      guarda da 001 aceitando banco novo -- sem isso a sequencia nao sobe
#      do zero. Em producao as duas sao so registradas, nunca executadas.
#    * Raiz limpa: deploy-*.ps1 e companhia vao para ops/releases/ e
#      ops/utilitarios/ (git mv, historico preservado).
#
#    1. pre-voo   -- arquivos, git, SSH
#    2. testes    -- regras puras do aplicar_migrations
#    3. adocao    -- registra 000..029 nas bases existentes (UMA VEZ),
#                    ANTES do push: sem isso o primeiro deploy trava
#    4. arquivo   -- git mv dos .ps1 da raiz
#    5. push
#    6. espera    -- o CI aplicar (nada a aplicar) e subir o codigo
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-049-migrations-automaticas.ps1 -Simular
#     .\ops\releases\deploy-049-migrations-automaticas.ps1
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

$entrega = @(
    ".github\workflows\ci-cd.yml",
    "api\migrations\000_base_pre_crm.sql",
    "api\migrations\001_drop_legado.sql",
    "api\scripts\aplicar_migrations.py",
    "api\scripts\comparar_schema.py",
    "api\scripts\gerar_schema_snapshot.sh",
    "api\tests\test_aplicar_migrations_regras.py",
    "api\schema.sql",
    "infra\adotar-migrations.sh",
    "infra\mos\instalar-instancia-mos.sh",
    "ops\releases\deploy-049-migrations-automaticas.ps1"
)

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"

foreach ($f in $entrega) {
    if (-not (Test-Path (Join-Path $Pasta $f))) { Abortar "faltando: $f (copie a entrega para a raiz do repositorio)" }
}
Bom "$($entrega.Count) arquivos da entrega presentes"

if (-not (Test-Path (Join-Path $Pasta ".git"))) { Abortar "$Pasta nao e a raiz do repositorio." }
$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne "main") { Abortar "voce esta no ramo '$ramo', nao na main." }
$ultima = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "*.sql" | Sort-Object Name)[-1].Name
if ($ultima -ne "029_confirmacao_vespera.sql") {
    Abortar "a ultima migration e $ultima, nao a 029. A adocao abaixo e para a 029 -- me avise."
}
Bom "main, ultima migration 029"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para adotar as migrations."
}
Bom "porta 22 responde"

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
            Passo "pytest (regras do aplicar_migrations)..."
            & python -m pytest -q --no-cov tests\test_aplicar_migrations_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "regras verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Adocao (antes do push)
# =====================================================================

Titulo "3. Adocao das migrations 000..029 nas bases existentes"

if ($Simular) {
    Aviso "simulacao: nao vou mexer nas bases"
} else {
    Confirmar "Registrar 000..029 como aplicadas na base principal (e na MOS, se existir)? Nada e executado no schema."
    & ssh -i $Chave $alvo "chmod -R u+w /tmp/hipo-adotar 2>/dev/null; rm -rf /tmp/hipo-adotar && mkdir -p /tmp/hipo-adotar"
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar /tmp/hipo-adotar na EC2." }
    & scp -i $Chave -r (Join-Path $Pasta "api\migrations") "${alvo}:/tmp/hipo-adotar/"
    & scp -i $Chave (Join-Path $Pasta "api\scripts\aplicar_migrations.py") "${alvo}:/tmp/hipo-adotar/"
    & scp -i $Chave (Join-Path $Pasta "infra\adotar-migrations.sh") "${alvo}:/tmp/hipo-adotar/"
    if ($LASTEXITCODE -ne 0) { Abortar "scp falhou." }
    & ssh -i $Chave $alvo "chmod -R u+rwX /tmp/hipo-adotar"
    & ssh -t -i $Chave $alvo "bash /tmp/hipo-adotar/adotar-migrations.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a adocao falhou (codigo $LASTEXITCODE). Nada foi pushado." }
    Bom "bases adotadas"
}

# =====================================================================
# 4. Arquivo dos .ps1 da raiz
# =====================================================================

Titulo "4. ops/releases e ops/utilitarios"

$soltos = @(& git ls-files -- "*.ps1" | Where-Object { $_ -notmatch "/" })
$releases = @($soltos | Where-Object { $_ -match "^(deploy|aplicar|fix|hotfix)-" })
$utilitarios = @($soltos | Where-Object { $_ -match "^(setup|diagnostico|liberar|avaliar)-" })
$resto = @($soltos | Where-Object { ($releases -notcontains $_) -and ($utilitarios -notcontains $_) })

Passo "$($releases.Count) para ops/releases, $($utilitarios.Count) para ops/utilitarios"
if ($resto.Count -gt 0) { Aviso "ficam na raiz (nao reconheci): $($resto -join ', ')" }

if ($Simular) {
    Aviso "simulacao: nao vou mover"
} else {
    New-Item -ItemType Directory -Force -Path (Join-Path $Pasta "ops\releases"), (Join-Path $Pasta "ops\utilitarios") | Out-Null
    foreach ($f in $releases)    { & git mv -k -- $f "ops/releases/$f" }
    foreach ($f in $utilitarios) { & git mv -k -- $f "ops/utilitarios/$f" }
    Bom "movidos (git mv: o historico de cada arquivo segue)"
}

# =====================================================================
# 5. Push
# =====================================================================

Titulo "5. Push"

$mensagem = @"
ci: migrations aplicadas pelo CI e pelo deploy (entrega 049)

- api/scripts/aplicar_migrations.py: aplica as pendentes em ordem, uma
  transacao por arquivo, e registra nome + SHA-256 em schema_migrations.
  Trava antes de aplicar: migration editada depois de aplicada, arquivo
  sumido, numero repetido, pendente atras da ultima aplicada, banco
  existente sem adocao e, da 030 em diante, BEGIN/COMMIT no arquivo ou
  DROP/TRUNCATE/DELETE sem o marcador de export. Advisory lock.
- 000_base_pre_crm.sql + guarda da 001 aceitando banco novo: a sequencia
  sobe do zero. Em producao as duas foram adotadas, nunca executadas.
- CI: banco de teste pelas migrations (e segunda passada vazia). O
  schema.sql vira snapshot de referencia; scripts/comparar_schema.py
  avisa quando diverge e o run publica o pg_dump como artefato.
- Deploy: migrations na EC2 (principal e MOS) antes do rsync e do
  restart; workflow_dispatch com pular_migrations para emergencia; sem
  cancel-in-progress na main.
- instalar-instancia-mos.sh cria banco novo pelas migrations.
- .ps1 da raiz arquivados em ops/releases e ops/utilitarios.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Ghjro4iAeg9g8fVcM8Wou9
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 049 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-049.txt"
    [System.IO.File]::WriteAllText($tmpMsg, $mensagem, (New-Object System.Text.UTF8Encoding($false)))
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 6. Espera o codigo novo
# =====================================================================

Titulo "6. Esperando o CI"

$marcador = "test -f /home/hipo/app/api/scripts/aplicar_migrations.py"
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
        Abortar "o codigo nao chegou em $EsperaMax s. Veja: gh run list --limit 3"
    }
    Bom "codigo da 049 no servidor -- o passo 'Aplicar migrations' passou"
    Write-Host ""
    Write-Host "  Confira no log do run: 'nada a aplicar' nas duas bases." -ForegroundColor Gray
    Write-Host "  Proxima migration: 030_*.sql, sem BEGIN/COMMIT. So dar push." -ForegroundColor Gray
}
