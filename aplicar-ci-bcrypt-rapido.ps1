<#
.SYNOPSIS
    Acelera o job "Backend Tests" do CI: de ~10-12 min para ~3-4 min.

.DESCRIPTION
    O gargalo medido nao e o Postgres, nem a cobertura, nem o pip install:
    e o bcrypt. A suite tem 1214 testes e quase todos passam por
    criar_usuario() no conftest, que faz um hashpw e em seguida um
    POST /auth/login (que faz um checkpw). bcrypt.gensalt() sem argumento
    usa custo 12, e custo 12 num runner de 2 vCPU e ~277 ms por operacao.
    Sao ~2400 operacoes por execucao.

    Medido em container de 2 vCPU com Postgres e schema reais:
        bcrypt 12 (como esta hoje) ... 1214 passed em 8m11s
        bcrypt 4 .................... 1214 passed em 1m55s
        bcrypt 12 sem cobertura ..... praticamente igual (cobertura = ~3%)

    Este script torna o custo configuravel (BCRYPT_ROUNDS), mantendo 12 como
    padrao e deixando o CI usar 4. O hash bcrypt carrega o proprio custo
    embutido, entao as senhas ja gravadas com custo 12 continuam validando
    normalmente -- nada precisa ser remigrado.

    De quebra, remove psycopg2-binary e pandas do requirements.txt: nenhum
    .py do projeto importa qualquer um dos dois desde a remocao do pipeline
    de XLSX do CROmie, e juntos eram 34 MB dos 94 MB baixados pelo CI a cada
    invalidacao de cache.

.PARAMETER Raiz
    Raiz do repositorio Hipo-Web. Padrao: a pasta atual.

.PARAMETER Commit
    Alem de aplicar, faz git add + git commit (nao faz push).

.PARAMETER Desfazer
    Restaura os arquivos a partir da pasta de backup mais recente e sai.

.EXAMPLE
    .\aplicar-ci-bcrypt-rapido.ps1
    .\aplicar-ci-bcrypt-rapido.ps1 -Commit
    .\aplicar-ci-bcrypt-rapido.ps1 -Desfazer

.NOTES
    Todo texto inserido nos arquivos e ASCII puro, de proposito: comentario
    com acento embaralha quando o patch e aplicado por script no PowerShell,
    e os arquivos antigos do projeto ja tem encoding misto que nao se deve
    mexer. Leitura e escrita preservam BOM e finais de linha (LF ou CRLF)
    de cada arquivo, byte a byte.
#>

[CmdletBinding()]
param(
    [string]$Raiz = ".",
    [switch]$Commit,
    [switch]$Desfazer
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------
# Infraestrutura: leitura/escrita preservando BOM e final de linha
# ---------------------------------------------------------------------------

function Read-Arquivo {
    param([string]$Caminho)

    $bytes = [System.IO.File]::ReadAllBytes($Caminho)
    $temBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $texto  = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($temBom) { $texto = $texto.Substring(1) }

    return [pscustomobject]@{
        Texto = $texto
        Bom   = $temBom
        Crlf  = $texto.Contains("`r`n")
    }
}

function Write-Arquivo {
    param([string]$Caminho, [string]$Texto, [bool]$Bom)

    $enc = New-Object System.Text.UTF8Encoding($Bom)
    [System.IO.File]::WriteAllText($Caminho, $Texto, $enc)
}

function ConvertTo-FinalDeLinha {
    param([string]$Texto, [bool]$Crlf)

    # Normaliza para LF primeiro para nao gerar "`r`r`n" em texto ja convertido.
    $t = $Texto.Replace("`r`n", "`n")
    if ($Crlf) { $t = $t.Replace("`n", "`r`n") }
    return $t
}

# ---------------------------------------------------------------------------
# Motor de patch
# ---------------------------------------------------------------------------

$script:Aplicados   = @()
$script:Pulados     = @()
$script:PastaBackup = $null

function Get-PastaBackup {
    <#
        Backup preguicoso: so nasce quando o primeiro patch de verdade vai
        gravar. Rodar o script duas vezes nao pode criar um segundo backup
        ja contendo os arquivos patchados -- era isso que fazia o -Desfazer
        "restaurar" para o estado alterado, porque ele pega o backup mais
        recente.
    #>
    if ($null -ne $script:PastaBackup) { return $script:PastaBackup }

    $carimbo = Get-Date -Format "yyyyMMdd-HHmmss"
    $pasta = Join-Path $script:RaizRepo "_backup-bcrypt-ci-$carimbo"
    New-Item -ItemType Directory -Path $pasta -Force | Out-Null
    foreach ($a in $script:Alvos) {
        Copy-Item -LiteralPath $a -Destination $pasta -Force
    }
    Write-Host ("  Backup dos originais em: {0}" -f $pasta) -ForegroundColor DarkGray
    $script:PastaBackup = $pasta
    return $pasta
}

function Invoke-Patch {
    <#
        De -> Para, com tres garantias:
          1. Se 'Marcador' ja existe no arquivo, o patch e considerado ja
             aplicado e nada acontece (script e idempotente, pode rodar duas
             vezes sem duplicar bloco).
          2. 'De' precisa aparecer EXATAMENTE UMA VEZ. Zero ou duas ocorrencias
             abortam o script inteiro, antes de gravar qualquer coisa.
          3. Final de linha do arquivo e respeitado nos dois lados.
    #>
    param(
        [string]$Caminho,
        [string]$Rotulo,
        [string]$De,
        [string]$Para,
        [string]$Marcador
    )

    if (-not (Test-Path -LiteralPath $Caminho)) {
        throw "Arquivo nao encontrado: $Caminho"
    }

    $arq = Read-Arquivo -Caminho $Caminho

    if ($arq.Texto.Contains($Marcador)) {
        $script:Pulados += $Rotulo
        Write-Host ("  [ja aplicado] {0}" -f $Rotulo) -ForegroundColor DarkGray
        return
    }

    $deLocal   = ConvertTo-FinalDeLinha -Texto $De   -Crlf $arq.Crlf
    $paraLocal = ConvertTo-FinalDeLinha -Texto $Para -Crlf $arq.Crlf

    $ocorrencias = ([regex]::Matches($arq.Texto, [regex]::Escape($deLocal))).Count
    if ($ocorrencias -ne 1) {
        $dica = if ($null -eq $script:PastaBackup) {
            "Nenhum arquivo foi tocado ainda."
        } else {
            "Patches anteriores JA foram gravados -- rode .\aplicar-ci-bcrypt-rapido.ps1 -Desfazer para voltar tudo."
        }
        throw ("Ancora do patch '{0}' apareceu {1} vez(es) em {2} -- esperava exatamente 1. " -f $Rotulo, $ocorrencias, $Caminho) +
              "O arquivo mudou desde 09/09/2026. $dica"
    }

    Get-PastaBackup | Out-Null

    $novo = $arq.Texto.Replace($deLocal, $paraLocal)
    Write-Arquivo -Caminho $Caminho -Texto $novo -Bom $arq.Bom

    $script:Aplicados += $Rotulo
    Write-Host ("  [ok] {0}" -f $Rotulo) -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Validacao da raiz
# ---------------------------------------------------------------------------

$Raiz = (Resolve-Path -LiteralPath $Raiz).Path

$fConfig   = Join-Path $Raiz "api/config.py"
$fAuth     = Join-Path $Raiz "api/routers/auth.py"
$fSeed     = Join-Path $Raiz "api/scripts/seed_usuarios.py"
$fConftest = Join-Path $Raiz "api/tests/conftest.py"
$fReq      = Join-Path $Raiz "api/requirements.txt"
$fCi       = Join-Path $Raiz ".github/workflows/ci-cd.yml"

$alvos = @($fConfig, $fAuth, $fSeed, $fConftest, $fReq, $fCi)

foreach ($a in $alvos) {
    if (-not (Test-Path -LiteralPath $a)) {
        throw "Nao parece a raiz do Hipo-Web: faltou '$a'. Rode de dentro da pasta do repositorio ou passe -Raiz."
    }
}

# Visiveis para Get-PastaBackup, que roda tarde, dentro do Invoke-Patch.
$script:RaizRepo = $Raiz
$script:Alvos    = $alvos

# ---------------------------------------------------------------------------
# Desfazer
# ---------------------------------------------------------------------------

if ($Desfazer) {
    $backups = Get-ChildItem -LiteralPath $Raiz -Directory -Filter "_backup-bcrypt-ci-*" |
               Sort-Object Name -Descending

    if (-not $backups) { throw "Nenhuma pasta _backup-bcrypt-ci-* encontrada em $Raiz." }

    $b = $backups[0].FullName
    Write-Host "Restaurando de $b" -ForegroundColor Yellow
    Copy-Item -LiteralPath (Join-Path $b "config.py")         -Destination $fConfig   -Force
    Copy-Item -LiteralPath (Join-Path $b "auth.py")           -Destination $fAuth     -Force
    Copy-Item -LiteralPath (Join-Path $b "seed_usuarios.py")  -Destination $fSeed     -Force
    Copy-Item -LiteralPath (Join-Path $b "conftest.py")       -Destination $fConftest -Force
    Copy-Item -LiteralPath (Join-Path $b "requirements.txt")  -Destination $fReq      -Force
    Copy-Item -LiteralPath (Join-Path $b "ci-cd.yml")         -Destination $fCi       -Force
    Write-Host "Restaurado. Confira com: git diff" -ForegroundColor Green
    return
}

# ---------------------------------------------------------------------------
# Aplicacao
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "HIPO -- Backend Tests: de ~10-12 min para ~3-4 min" -ForegroundColor Cyan
Write-Host ("Raiz: {0}" -f $Raiz)
Write-Host ""

# ---------------------------------------------------------------------------
# 1/6  api/config.py -- campo BCRYPT_ROUNDS
# ---------------------------------------------------------------------------

Write-Host "api/config.py" -ForegroundColor White

Invoke-Patch -Caminho $fConfig -Rotulo "config.py: campo BCRYPT_ROUNDS" -Marcador "BCRYPT_ROUNDS: int" -De @'
    ENVIRONMENT: str = "production"
'@ -Para @'
    ENVIRONMENT: str = "production"
    # Custo do bcrypt. 12 e o padrao e o que vale em producao.
    # O CI baixa para 4 via variavel de ambiente: a suite cria e loga
    # ~1200 usuarios, e a 12 sao ~277ms por operacao (2x por teste) --
    # sozinho isso respondia por ~80% do tempo do job Backend Tests.
    # O hash guarda o proprio custo, entao hashes antigos (12) seguem
    # validando normalmente depois da mudanca.
    BCRYPT_ROUNDS: int = 12
'@

# Trava: producao nunca roda com custo rebaixado, mesmo que o .env diga isso.
Invoke-Patch -Caminho $fConfig -Rotulo "config.py: trava de producao" -Marcador "settings.BCRYPT_ROUNDS = 12" -De @'
settings = Settings()
'@ -Para @'
settings = Settings()

# Trava de seguranca: custo baixo e recurso de teste. Se o .env de
# producao vier com BCRYPT_ROUNDS rebaixado (copiado do CI, por engano),
# o valor e ignorado e volta para 12 -- em vez de subir a API gravando
# senha fraca em silencio.
if settings.ENVIRONMENT == "production" and settings.BCRYPT_ROUNDS < 12:
    settings.BCRYPT_ROUNDS = 12
'@

# ---------------------------------------------------------------------------
# 2/6  api/routers/auth.py
# ---------------------------------------------------------------------------

Write-Host "api/routers/auth.py" -ForegroundColor White

Invoke-Patch -Caminho $fAuth -Rotulo "auth.py: _hash_senha usa settings.BCRYPT_ROUNDS" -Marcador "gensalt(rounds=settings.BCRYPT_ROUNDS)" -De @'
def _hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
'@ -Para @'
def _hash_senha(senha: str) -> str:
    return bcrypt.hashpw(
        senha.encode(), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode()
'@

# ---------------------------------------------------------------------------
# 3/6  api/scripts/seed_usuarios.py
# ---------------------------------------------------------------------------

Write-Host "api/scripts/seed_usuarios.py" -ForegroundColor White

Invoke-Patch -Caminho $fSeed -Rotulo "seed_usuarios.py: _hash usa settings.BCRYPT_ROUNDS" -Marcador "gensalt(rounds=settings.BCRYPT_ROUNDS)" -De @'
def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
'@ -Para @'
def _hash(senha: str) -> str:
    from config import settings
    return bcrypt.hashpw(
        senha.encode(), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode()
'@

# ---------------------------------------------------------------------------
# 4/6  api/tests/conftest.py
# ---------------------------------------------------------------------------

Write-Host "api/tests/conftest.py" -ForegroundColor White

# As duas variaveis precisam entrar ANTES do import de config/main: o
# pydantic-settings le o ambiente uma vez, no import.
Invoke-Patch -Caminho $fConftest -Rotulo "conftest.py: ENVIRONMENT=test e BCRYPT_ROUNDS=4" -Marcador 'setdefault("BCRYPT_ROUNDS"' -De @'
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")
'@ -Para @'
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")
# Custo do bcrypt na suite. 4 e o minimo do algoritmo e derruba a
# operacao de ~277ms para ~1ms. Com 1214 testes criando usuario e
# logando (2 operacoes cada), e a diferenca entre 8m11s e 1m55s de
# pytest. Precisa vir ANTES do import de config/main, que le o
# ambiente uma vez so.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
'@

Invoke-Patch -Caminho $fConftest -Rotulo "conftest.py: constante _ROUNDS" -Marcador "_ROUNDS = int(" -De @'
_DB_URL = os.environ["DATABASE_URL"]
'@ -Para @'
_DB_URL = os.environ["DATABASE_URL"]
_ROUNDS = int(os.environ["BCRYPT_ROUNDS"])
'@

Invoke-Patch -Caminho $fConftest -Rotulo "conftest.py: criar_usuario usa _ROUNDS" -Marcador "gensalt(rounds=_ROUNDS)" -De @'
    pwd_hash = bcrypt.hashpw(_SENHA_TESTE.encode(), bcrypt.gensalt()).decode()
'@ -Para @'
    pwd_hash = bcrypt.hashpw(
        _SENHA_TESTE.encode(), bcrypt.gensalt(rounds=_ROUNDS)
    ).decode()
'@

# ---------------------------------------------------------------------------
# 5/6  api/requirements.txt -- dependencias mortas
# ---------------------------------------------------------------------------

Write-Host "api/requirements.txt" -ForegroundColor White

Invoke-Patch -Caminho $fReq -Rotulo "requirements.txt: remove psycopg2-binary e pandas" -Marcador "psycopg2-binary e pandas sairam" -De @'
psycopg2-binary==2.9.9
pandas==2.2.0
openpyxl==3.1.2
'@ -Para @'
# psycopg2-binary e pandas sairam em 09/09/2026: nenhum arquivo .py do
# projeto importa qualquer um dos dois desde a remocao do pipeline de
# XLSX do CROmie. Juntos eram 34MB dos 94MB baixados pelo CI a cada
# invalidacao de cache. O acesso ao banco e 100% asyncpg.
# openpyxl fica: scripts/dados/gerar_payloads_oraculus.py ainda usa.
openpyxl==3.1.2
'@

# ---------------------------------------------------------------------------
# 6/6  .github/workflows/ci-cd.yml
# ---------------------------------------------------------------------------

Write-Host ".github/workflows/ci-cd.yml" -ForegroundColor White

Invoke-Patch -Caminho $fCi -Rotulo "ci-cd.yml: BCRYPT_ROUNDS=4 no job de testes" -Marcador "BCRYPT_ROUNDS:" -De @'
          JWT_SECRET: test-secret-key-ci
'@ -Para @'
          JWT_SECRET: test-secret-key-ci
          ENVIRONMENT: test
          # Custo do bcrypt no CI. A 12 (padrao de producao) cada
          # hash/verificacao leva ~277ms num runner de 2 vCPU, e a
          # suite faz isso ~2400 vezes: a maior parte dos ~10-12 min
          # do job era so bcrypt. A 4 sao ~1ms. Producao nao le esta
          # variavel e config.py ignora valor < 12 quando
          # ENVIRONMENT=production.
          BCRYPT_ROUNDS: "4"
'@

# ---------------------------------------------------------------------------
# Verificacao pos-patch
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Conferindo o resultado..." -ForegroundColor White

$conferencias = @(
    @{ Arquivo = $fConfig;   Espera = "BCRYPT_ROUNDS: int = 12";                 Rotulo = "config.py tem o campo" },
    @{ Arquivo = $fConfig;   Espera = "settings.BCRYPT_ROUNDS = 12";             Rotulo = "config.py tem a trava de producao" },
    @{ Arquivo = $fAuth;     Espera = "gensalt(rounds=settings.BCRYPT_ROUNDS)";  Rotulo = "auth.py parametrizado" },
    @{ Arquivo = $fSeed;     Espera = "gensalt(rounds=settings.BCRYPT_ROUNDS)";  Rotulo = "seed_usuarios.py parametrizado" },
    @{ Arquivo = $fConftest; Espera = 'setdefault("BCRYPT_ROUNDS", "4")';        Rotulo = "conftest.py fixa custo 4" },
    @{ Arquivo = $fConftest; Espera = "gensalt(rounds=_ROUNDS)";                 Rotulo = "conftest.py usa _ROUNDS" },
    @{ Arquivo = $fCi;       Espera = 'BCRYPT_ROUNDS: "4"';                      Rotulo = "ci-cd.yml exporta a variavel" }
)

$falhas = 0
foreach ($c in $conferencias) {
    $conteudo = (Read-Arquivo -Caminho $c.Arquivo).Texto
    if ($conteudo.Contains($c.Espera)) {
        Write-Host ("  [ok] {0}" -f $c.Rotulo) -ForegroundColor Green
    } else {
        Write-Host ("  [FALHOU] {0}" -f $c.Rotulo) -ForegroundColor Red
        $falhas++
    }
}

# Nenhum gensalt() sem custo pode sobrar no caminho quente.
$sobras = @()
foreach ($f in @($fAuth, $fSeed, $fConftest)) {
    $conteudo = (Read-Arquivo -Caminho $f).Texto
    if ($conteudo.Contains("bcrypt.gensalt()")) { $sobras += $f }
}
if ($sobras.Count -gt 0) {
    Write-Host ("  [FALHOU] ainda existe bcrypt.gensalt() sem custo em: {0}" -f ($sobras -join ", ")) -ForegroundColor Red
    $falhas++
} else {
    Write-Host "  [ok] nenhum bcrypt.gensalt() sem custo sobrou" -ForegroundColor Green
}

# O py_compile pega erro de sintaxe sem precisar de Postgres nem de venv.
$python = $null
foreach ($cand in @("python", "py")) {
    $c = Get-Command $cand -ErrorAction SilentlyContinue
    if ($c) { $python = $c.Source; break }
}
if ($python) {
    Write-Host "  Compilando os .py alterados..." -ForegroundColor DarkGray
    & $python -m py_compile $fConfig $fAuth $fSeed $fConftest
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FALHOU] py_compile acusou erro de sintaxe" -ForegroundColor Red
        $falhas++
    } else {
        Write-Host "  [ok] py_compile passou nos 4 arquivos" -ForegroundColor Green
    }
} else {
    Write-Host "  [pulado] python nao encontrado no PATH -- py_compile nao rodou" -ForegroundColor DarkGray
}

if ($falhas -gt 0) {
    Write-Host ""
    Write-Host "$falhas conferencia(s) falharam. Restaure com: .\aplicar-ci-bcrypt-rapido.ps1 -Desfazer" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "----------------------------------------------------------------" -ForegroundColor Cyan
Write-Host ("Patches aplicados agora: {0}" -f $script:Aplicados.Count)
Write-Host ("Ja aplicados antes:      {0}" -f $script:Pulados.Count)
Write-Host ""
Write-Host "Esperado no proximo push:"
Write-Host "  Backend Tests:  ~10-12 min  ->  ~3-4 min"
Write-Host ""
Write-Host "Senhas ja gravadas nao precisam de nada: o hash bcrypt carrega o"
Write-Host "custo embutido, entao os hashes de custo 12 seguem validando."
Write-Host "----------------------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

if ($Commit) {
    Push-Location $Raiz
    try {
        git add api/config.py api/routers/auth.py api/scripts/seed_usuarios.py api/tests/conftest.py api/requirements.txt .github/workflows/ci-cd.yml
        $msg = @"
ci: parametriza custo do bcrypt e derruba Backend Tests de ~8min para ~2min

O job Backend Tests levava 10-12 min. O gargalo nao era Postgres, nem
cobertura, nem pip install: era bcrypt. A suite tem 1214 testes e quase
todos passam por criar_usuario(), que faz um hashpw e em seguida um
POST /auth/login (que faz um checkpw). gensalt() sem argumento usa custo
12, ~277ms por operacao num runner de 2 vCPU, ~2400 operacoes por run.

Medido em container de 2 vCPU com Postgres e schema reais:
  bcrypt 12 ............... 1214 passed em 8m11s
  bcrypt 4 ................ 1214 passed em 1m55s
  sem cobertura, bcrypt 12  praticamente igual (cobertura custa ~3%)

O custo agora vem de settings.BCRYPT_ROUNDS, padrao 12. O CI exporta 4.
config.py forca 12 de volta quando ENVIRONMENT=production, para o caso
de um .env de producao ser copiado do CI por engano.

O hash bcrypt carrega o proprio custo embutido: as senhas ja gravadas
com custo 12 continuam validando, nada a remigrar.

Junto: psycopg2-binary e pandas saem do requirements.txt. Nenhum .py do
projeto importa qualquer um dos dois desde a remocao do pipeline de XLSX
do CROmie, e juntos eram 34MB dos 94MB que o CI baixa a cada
invalidacao de cache.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Df6ihbxGuEV94M3mbywsWH
"@
        git commit -m $msg
        Write-Host ""
        Write-Host "Commitado. Falta o push:  git push" -ForegroundColor Yellow
    }
    finally {
        Pop-Location
    }
} else {
    Write-Host "Confira e depois commite:" -ForegroundColor Yellow
    Write-Host "  git diff"
    Write-Host "  .\aplicar-ci-bcrypt-rapido.ps1 -Commit"
    Write-Host "  git push"
}
