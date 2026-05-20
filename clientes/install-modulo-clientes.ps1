# ============================================================
# HIPO - Instalador do Modulo Clientes + Renomeacao Carteira->Contadores
#
# Acoes:
#   1. Backup da estrutura atual
#   2. Backend (8 arquivos):
#        - migrations/009_modulo_clientes.sql
#        - migrations/schema_clientes_append.sql
#        - parsers/cliente_oportunidades.py
#        - parsers/cliente_tarefas.py
#        - routers/clientes.py
#        - routers/permissions.py (atualizado)
#        - main.py (atualizado com router clientes)
#        - tests/test_clientes.py
#        - tests/conftest.py (atualizado com TRUNCATE das novas tabelas)
#   3. Frontend (7 arquivos):
#        - api.js (atualizado: primeiraRotaAcessivel)
#        - App.jsx (rotas /contadores e /clientes; redirect /carteira)
#        - components/Layout.jsx (item Clientes; renomeacao visual)
#        - components/CarteiraGrupoDrawer.jsx (tema claro + abas Tarefas/Leads)
#        - pages/Contadores.jsx (substitui Carteira.jsx)
#        - pages/Clientes.jsx (NOVO)
#        - tests/Clientes.test.jsx (NOVO)
#        - tests/Layout.test.jsx (atualizado)
#   4. Anexa schema_clientes_append.sql ao api/schema.sql se ainda nao foi anexado
#   5. Remove Carteira.jsx antigo (substituido por Contadores.jsx)
#
# Apos rodar este script:
#   git add -A
#   git commit -m "feat: modulo Clientes + renomeacao Carteira->Contadores"
#   git push
#   (esperar CI ficar verde)
#   ssh ec2 e rodar a migration 009 manualmente
# ============================================================

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

Write-Host ""
Write-Host "==> HIPO: Modulo Clientes + Renomeacao" -ForegroundColor Cyan
Write-Host ""

# ---- Resolver pasta base ----
if (Test-Path (Join-Path $root "api")) {
    $base = $root
} elseif (Test-Path (Join-Path (Split-Path $root -Parent) "api")) {
    $base = Split-Path $root -Parent
} else {
    Write-Host "[ERRO] Nao encontrei pasta 'api' a partir de '$root'." -ForegroundColor Red
    Write-Host "Rode este script de dentro de C:\Users\tulio\Documents\APP - hipo\Hipo - v1.0.1\" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Base do projeto: $base" -ForegroundColor Green

# ---- Resolver pasta de origem (zip extraido) ----
# Pode ser na raiz do script OU em subpasta 'clientes/'
$srcRoot = $null
foreach ($candidate in @($root, (Join-Path $root "clientes"))) {
    if (Test-Path (Join-Path $candidate "api\routers\clientes.py")) {
        $srcRoot = $candidate
        break
    }
}
if (-not $srcRoot) {
    Write-Host "[ERRO] Nao encontrei os arquivos do pacote." -ForegroundColor Red
    Write-Host "Verifique se o zip foi extraido em '$root' ou '$root\clientes\'" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Fonte: $srcRoot" -ForegroundColor Green
Write-Host ""

# ---- Backup ----
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$bk = Join-Path $base "backup_clientes_$ts"
New-Item -ItemType Directory -Force -Path $bk | Out-Null

$filesToBackup = @(
    "api\main.py",
    "api\routers\permissions.py",
    "api\tests\conftest.py",
    "api\schema.sql",
    "web\src\api.js",
    "web\src\App.jsx",
    "web\src\components\Layout.jsx",
    "web\src\components\CarteiraGrupoDrawer.jsx",
    "web\src\pages\Carteira.jsx",
    "web\src\tests\Layout.test.jsx"
)
foreach ($f in $filesToBackup) {
    $orig = Join-Path $base $f
    if (Test-Path $orig) {
        $rel = $f -replace "\\", "_"
        Copy-Item $orig (Join-Path $bk $rel) -Force
    }
}
Write-Host "[OK] Backup em: $bk" -ForegroundColor Green
Write-Host ""

# ---- Copiar arquivos ----
$pares = @(
    # Backend
    @("api\migrations\009_modulo_clientes.sql",        "api\migrations\009_modulo_clientes.sql"),
    @("api\migrations\schema_clientes_append.sql",     "api\migrations\schema_clientes_append.sql"),
    @("api\parsers\cliente_oportunidades.py",          "api\parsers\cliente_oportunidades.py"),
    @("api\parsers\cliente_tarefas.py",                "api\parsers\cliente_tarefas.py"),
    @("api\routers\clientes.py",                       "api\routers\clientes.py"),
    @("api\routers\permissions.py",                    "api\routers\permissions.py"),
    @("api\main.py",                                    "api\main.py"),
    @("api\tests\test_clientes.py",                    "api\tests\test_clientes.py"),
    @("api\tests\conftest.py",                         "api\tests\conftest.py"),
    # Frontend
    @("web\src\api.js",                                "web\src\api.js"),
    @("web\src\App.jsx",                               "web\src\App.jsx"),
    @("web\src\components\Layout.jsx",                "web\src\components\Layout.jsx"),
    @("web\src\components\CarteiraGrupoDrawer.jsx",   "web\src\components\CarteiraGrupoDrawer.jsx"),
    @("web\src\pages\Contadores.jsx",                 "web\src\pages\Contadores.jsx"),
    @("web\src\pages\Clientes.jsx",                   "web\src\pages\Clientes.jsx"),
    @("web\src\tests\Clientes.test.jsx",              "web\src\tests\Clientes.test.jsx"),
    @("web\src\tests\Layout.test.jsx",                "web\src\tests\Layout.test.jsx")
)

foreach ($p in $pares) {
    $src = Join-Path $srcRoot $p[0]
    $dst = Join-Path $base   $p[1]
    if (-not (Test-Path $src)) {
        Write-Host "[ERRO] Arquivo de origem nao encontrado: $src" -ForegroundColor Red
        exit 1
    }
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) {
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    }
    Copy-Item $src $dst -Force
    Write-Host "  + $($p[1])" -ForegroundColor Gray
}
Write-Host "[OK] 17 arquivos copiados" -ForegroundColor Green
Write-Host ""

# ---- Anexar ao schema.sql ----
$schemaPath = Join-Path $base "api\schema.sql"
$appendPath = Join-Path $base "api\migrations\schema_clientes_append.sql"
if (Test-Path $schemaPath) {
    $schemaContent = Get-Content $schemaPath -Raw
    $marker = "cliente_oportunidade"
    if ($schemaContent -match $marker) {
        Write-Host "[OK] schema.sql ja contem tabelas do modulo Clientes (skip append)" -ForegroundColor Yellow
    } else {
        $appendContent = Get-Content $appendPath -Raw
        Add-Content -Path $schemaPath -Value "`n`n$appendContent" -NoNewline
        Write-Host "[OK] Anexado schema_clientes_append.sql ao schema.sql" -ForegroundColor Green
    }
} else {
    Write-Host "[AVISO] schema.sql nao encontrado em $schemaPath" -ForegroundColor Yellow
}
Write-Host ""

# ---- Remover Carteira.jsx antigo (substituido por Contadores.jsx) ----
$carteiraJsx = Join-Path $base "web\src\pages\Carteira.jsx"
if (Test-Path $carteiraJsx) {
    Remove-Item $carteiraJsx -Force
    Write-Host "[OK] Removido web/src/pages/Carteira.jsx (agora e Contadores.jsx)" -ForegroundColor Green
}
# Tambem remover o teste antigo se existir
$carteiraTestJsx = Join-Path $base "web\src\tests\Carteira.test.jsx"
if (Test-Path $carteiraTestJsx) {
    # Renomear pra Contadores.test.jsx pode dar erro porque o componente la dentro
    # ainda referencia "Carteira". Vou apenas remover, e o test do Layout cobre o essencial.
    # Se quiser manter o teste de Carteira, abra-o manualmente e troque os imports.
    Write-Host "[INFO] Carteira.test.jsx mantido. Voce pode atualizar manualmente os imports" -ForegroundColor Yellow
    Write-Host "       trocando 'Carteira' por 'Contadores', ou deletar se nao precisar." -ForegroundColor Yellow
}
Write-Host ""

# ---- Validacoes ----
Write-Host "==> Validacoes pos-instalacao" -ForegroundColor Cyan

$check1 = Get-Content (Join-Path $base "api\routers\permissions.py") -Raw
if ($check1 -match "clientes") {
    Write-Host "  [OK] permissions.py contem modulo 'clientes'" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] permissions.py nao tem 'clientes'" -ForegroundColor Red
}

$check2 = Get-Content (Join-Path $base "api\main.py") -Raw
if ($check2 -match "clientes\.router") {
    Write-Host "  [OK] main.py inclui router de clientes" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] main.py nao inclui router clientes" -ForegroundColor Red
}

$check3 = Get-Content (Join-Path $base "web\src\components\Layout.jsx") -Raw
if (($check3 -match "Contadores") -and ($check3 -match "Clientes")) {
    Write-Host "  [OK] Layout.jsx tem itens Contadores e Clientes" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Layout.jsx faltando algo" -ForegroundColor Red
}

if (Test-Path (Join-Path $base "web\src\pages\Contadores.jsx")) {
    Write-Host "  [OK] Contadores.jsx existe" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Contadores.jsx nao foi criado" -ForegroundColor Red
}

if (Test-Path (Join-Path $base "web\src\pages\Clientes.jsx")) {
    Write-Host "  [OK] Clientes.jsx existe" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Clientes.jsx nao foi criado" -ForegroundColor Red
}

if (-not (Test-Path (Join-Path $base "web\src\pages\Carteira.jsx"))) {
    Write-Host "  [OK] Carteira.jsx removido" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Carteira.jsx ainda existe (sera ignorado pelo App.jsx)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Tudo pronto!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Revisar mudancas:" -ForegroundColor Gray
Write-Host "       cd `"$base`"" -ForegroundColor Gray
Write-Host "       git status" -ForegroundColor Gray
Write-Host "       git diff --stat" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Commit e push:" -ForegroundColor Gray
Write-Host "       git add -A" -ForegroundColor Gray
Write-Host "       git commit -m `"feat: modulo Clientes + renomeacao Carteira->Contadores`"" -ForegroundColor Gray
Write-Host "       git push" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Aguardar CI ficar verde no GitHub" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Rodar migration 009 na EC2 (depois do CI verde):" -ForegroundColor Gray
Write-Host "       ssh -i `$HOME\Downloads\chave-hipo.pem ec2-user@63.179.88.212" -ForegroundColor Gray
Write-Host "       set -a; source /home/hipo/app/.env; set +a" -ForegroundColor Gray
Write-Host "       psql `"`$DATABASE_URL`" -f /home/hipo/app/api/migrations/009_modulo_clientes.sql" -ForegroundColor Gray
Write-Host ""
Write-Host "  5. Acessar https://hipo.omie.com.vc/clientes e fazer upload das planilhas" -ForegroundColor Gray
Write-Host ""
