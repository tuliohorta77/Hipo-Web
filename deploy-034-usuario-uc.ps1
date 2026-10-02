# =====================================================================
#  HIPO -- deploy 034: conta so da UC (cargo UC) + usuario do Marcelo
# =====================================================================
#
#  Cargo novo "UC": modulo 'uc' e mais nada. Ve TODAS as trilhas
#  publicadas da Universidade (nenhuma como obrigatoria), assiste e
#  conclui aulas, troca a senha em /perfil. CRM, estudio, Monitor,
#  relatorios, RPeR, parceiros e telemetria: 403.
#  Fica fora do seletor de envolvidos, da visao do time e dos ausentes
#  da telemetria. Sem migration (cargo e VARCHAR livre). Ninguem
#  precisa relogar: os demais cargos continuam entrando na UC pelo 'crm'.
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- testes puros (o CI roda o resto)
#    3. push         -- SO os arquivos da entrega
#    4. espera       -- ate o codigo novo chegar no servidor
#    5. usuario      -- cria marcelod@controllermedseg.com.br, senha 123456
#
#  USO
#     .\deploy-034-usuario-uc.ps1 -Simular
#     .\deploy-034-usuario-uc.ps1
#     .\deploy-034-usuario-uc.ps1 -SoUsuario   (o push ja foi; so a etapa 5)
#     .\deploy-034-usuario-uc.ps1 -SoUsuario -Email x@y.com -Nome "Fulano"
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoUsuario,

    [string]$Email    = "marcelod@controllermedseg.com.br",
    [string]$Nome     = "Marcelo",
    [string]$Senha    = "123456",

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
    "api\main.py",
    "api\routers\permissions.py",
    "api\routers\uc.py",
    "api\routers\crm_dominio.py",
    "api\services\telemetria.py",
    "web\src\api.js",
    "web\src\components\Layout.jsx",
    "web\src\tests\Layout.test.jsx",
    "web\src\tests\primeiraRota.test.js"
)

# Todos os arquivos da entrega (o que vai no `git add`).
$entrega = $substituidos + @(
    "api\scripts\criar_usuario_uc.py",
    "api\tests\test_usuario_uc.py",
    "infra\criar-usuario-uc.sh",
    "deploy-034-usuario-uc.ps1"
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
Bom "arquivos da entrega conferidos"

if (-not $SoUsuario) {
    # A entrega foi feita sobre f202f0c (prospeccao).
    $base = "f202f0c"
    & git cat-file -e "$base^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
    Bom "base: $base"
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois de $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois de $base mexeu nos arquivos substituidos"
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
    Abortar "sem SSH nao da para criar o usuario."
}
Bom "porta 22 responde"

if (-not $SoUsuario) {

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
            Passo "pytest (funcoes puras do cargo UC e do script)..."
            & python -m pytest -q --no-cov tests\test_usuario_uc.py -k "TestModulosDaUc or TestValidarScript"
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "verde"
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
feat(uc): cargo UC -- conta que so enxerga a Universidade Corporativa

- permissions: CARGO_UC = "UC" -> modulos {'uc'}. Fora de
  CARGOS_VALIDOS, como o Monitor. CARGOS_DE_TELA junta os dois.
- main: /uc aceita 'crm' OU 'uc'; o estudio segue so no 'crm'.
- uc: o cargo UC ve todas as trilhas publicadas, nenhuma obrigatoria.
- crm_dominio e telemetria: contas de tela fora do seletor de
  envolvidos e da lista de ausentes.
- front: Universidade na nav para 'uc'; o cargo UC cai em /uc.
- scripts/criar_usuario_uc.py + infra/criar-usuario-uc.sh.
- Sem migration; ninguem precisa relogar.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Agp3cdeBGcCoU8RrtZAik3
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short
} else {
    Confirmar "Commitar a entrega 034 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-034.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, rode com -SoUsuario." }
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

$marcador = "/home/hipo/app/api/scripts/criar_usuario_uc.py"
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
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoUsuario."
        exit 1
    }
    Bom "codigo novo no servidor"
    # O script chega pelo rsync ANTES do restart da API; da um tempo para
    # o restart e o health check do CI terminarem.
    Passo "aguardando 60 s para o restart da API..."
    Start-Sleep -Seconds 60
}

}  # fim do if (-not $SoUsuario)

# =====================================================================
# 5. Usuario
# =====================================================================

Titulo "5. Usuario $Email (cargo UC)"

if ($Simular) {
    Aviso "simulacao: nao vou criar nada"
} else {
    & scp -i $Chave (Join-Path $Pasta "infra\criar-usuario-uc.sh") "${alvo}:/tmp/criar-usuario-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    & ssh -i $Chave $alvo "bash /tmp/criar-usuario-uc.sh '$Email' '$Nome' '$Senha'"
    if ($LASTEXITCODE -ne 0) { Abortar "a criacao falhou (codigo $LASTEXITCODE)." }
    Bom "usuario pronto"
}

Titulo "Pronto"
Write-Host @"
  1. Login com $Email / $Senha (aba anonima, para nao herdar a sua sessao).
  2. Cai direto na Universidade; a barra mostra so "Universidade".
  3. Todas as trilhas publicadas aparecem em "Outras trilhas".
  4. Trocar a senha: menu do usuario > Perfil.
"@ -ForegroundColor White
