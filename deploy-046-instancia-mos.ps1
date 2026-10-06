# =====================================================================
#  HIPO -- deploy 046: segunda base (instancia MOS)
# =====================================================================
#
#  O que entra:
#    * Codigo: identidade da instancia (EMPRESA_NOME, EMPRESA_SIGLA,
#      PROPOSTA_MODELO_ARQUIVO no config.py). Com o .env da MedSeg intocado,
#      NADA muda na base principal -- os padroes reproduzem o que era.
#    * Selo "MOS" ao lado do logo e no titulo da aba; /health e /auth/me
#      dizem qual base respondeu.
#    * scripts/clonar_config.py e scripts/criar_usuario.py.
#    * CI: passos "Deploy do Backend (MOS)" e front da MOS, que so agem
#      quando a instancia existe.
#    * infra/mos/: units, nginx e o instalador por fases.
#
#  Ordem (cada etapa so roda com a anterior verde):
#    1. pre-voo   -- arquivos, base do git, ci-cd.yml copiado, SSH
#    2. testes    -- vitest (o CI roda o backend com Postgres)
#    3. push      -- SO os arquivos da entrega
#    4. espera    -- config.py novo no servidor + base principal intacta
#    5. DNS       -- mos.hipogestao.com.br resolvendo (Registro.br, manual)
#    6. servidor  -- fases base, app, nginx, tls, config, usuario, fechamento
#    7. smoke     -- cada dominio responde com a SUA instancia
#
#  USO
#     .\deploy-046-instancia-mos.ps1 -Simular
#     .\deploy-046-instancia-mos.ps1
#     .\deploy-046-instancia-mos.ps1 -SoServidor                 (push ja foi)
#     .\deploy-046-instancia-mos.ps1 -SoServidor -Fases tls,config
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoServidor,
    [string[]]$Fases = @("base", "app", "nginx", "tls", "config", "usuario", "fechamento"),

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [string]$DominioMos = "mos.hipogestao.com.br",
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
function Health($url) {
    try { return Invoke-RestMethod -Uri $url -TimeoutSec 20 } catch { return $null }
}

$alvo = "$Usuario@$Servidor"

# Commit sobre o qual a entrega foi feita (main em 05/10/2026, entrega 045).
$base = "a7bc8b5"

$substituidos = @(
    ".github\workflows\ci-cd.yml",
    "api\config.py",
    "api\main.py",
    "api\routers\auth.py",
    "api\services\agenda.py",
    "api\services\proposta_render.py",
    "api\services\relatorio_render.py",
    "api\services\rper_render.py",
    "web\src\components\Layout.jsx",
    "web\src\components\crm\TabelaPrecos.jsx",
    "web\src\tests\Layout.test.jsx"
)

$novos = @(
    "api\services\instancia.py",
    "api\scripts\clonar_config.py",
    "api\scripts\criar_usuario.py",
    "api\tests\test_instancia.py",
    "api\tests\test_clonar_config.py",
    "infra\mos\instalar-instancia-mos.sh",
    "infra\mos\aplicar-sql-nas-bases.sh",
    "infra\mos\hipo-mos-api.service",
    "infra\mos\hipo-mos-fechamento.service",
    "infra\mos\hipo-mos-fechamento.timer",
    "infra\mos\hipo-mos.nginx.conf",
    "deploy-046-instancia-mos.ps1"
)

$entrega = $substituidos + $novos
$infraMos = @($novos | Where-Object { $_ -like "infra\mos\*" })

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

# O ci-cd.yml e copiado a mao (a pasta .github\workflows e protegida contra
# escrita por ferramenta remota). Sem os passos da MOS o CI nunca atualiza
# a segunda base, e ela fica parada na versao da instalacao.
$ci = Get-Content (Join-Path $Pasta ".github\workflows\ci-cd.yml") -Raw
if ($ci -notmatch "hipo-mos-api") {
    Abortar "o .github\workflows\ci-cd.yml ainda e o antigo. Copie o da entrega 046 por cima."
}
Bom "ci-cd.yml com os passos da MOS"

if (-not $SoServidor) {
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
    Abortar "sem SSH nao da para instalar a instancia."
}
Bom "porta 22 responde"

if (-not $SoServidor) {

# =====================================================================
# 2. Testes
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    Push-Location (Join-Path $Pasta "web")
    try {
        Passo "vitest (Layout: selo da instancia)..."
        & npx vitest run src/tests/Layout.test.jsx
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou." }
        Bom "front verde"
    } finally { Pop-Location }
    Aviso "backend (clone entre dois bancos) so roda no CI, que tem Postgres"
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(infra): segunda base do HIPO -- instancia MOS (entrega 046)

- config: EMPRESA_NOME, EMPRESA_SIGLA, PROPOSTA_MODELO_ARQUIVO. Padroes
  reproduzem a base principal (convite, RPeR, assunto, proposta).
- services/instancia.py; /health e /auth/me dizem a instancia; selo e
  titulo da aba no front.
- scripts/clonar_config.py (configuracao -> base nova, autoria NULL,
  materiais da UC copiados no S3 com prefixo) e scripts/criar_usuario.py.
- CI: deploy da MOS (8002, /home/hipo/mos, /var/www/hipo-mos) quando a
  instancia existe.
- infra/mos: units, nginx e instalador por fases.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B72kRw5BiyP8qJMVQD3eP4
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 046 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-046.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, rode com -SoServidor." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 4. Espera o codigo novo (prova no servidor, nao no CI)
# =====================================================================

Titulo "4. Esperando o CI"

$marcador = "grep -qE '^[[:space:]]*EMPRESA_SIGLA[[:space:]]*:' /home/hipo/app/api/config.py"
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
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoServidor."
        exit 1
    }
    Bom "config.py da 046 no servidor"

    # A base principal tem que responder IGUAL a antes: empresa MedSeg e sem
    # instancia. E a prova de que os padroes nao mudaram nada.
    Start-Sleep -Seconds 10
    $h = Health "https://$Servidor/api/health"
    if (-not $h) { Abortar "https://$Servidor/api/health nao respondeu. Confira a base principal JA." }
    if ($h.empresa -ne "Controller MedSeg" -or $h.instancia) {
        Abortar "a base principal respondeu empresa='$($h.empresa)' instancia='$($h.instancia)'. Esperado: Controller MedSeg, sem instancia."
    }
    Bom "base principal intacta (empresa=$($h.empresa), sem instancia)"
}

}  # fim do if (-not $SoServidor)

# =====================================================================
# 5. DNS
# =====================================================================

Titulo "5. DNS de $DominioMos"

function IpDe($nome) {
    try {
        return @(Resolve-DnsName -Name $nome -Type A -DnsOnly -ErrorAction Stop |
            Where-Object { $_.Type -eq "A" } | Select-Object -ExpandProperty IPAddress)[0]
    } catch { return $null }
}
$ipMed = IpDe $Servidor
$ipMos = IpDe $DominioMos
Write-Host "     $Servidor -> $ipMed"
Write-Host "     $DominioMos -> $ipMos"
$dnsOk = ($ipMos -and $ipMos -eq $ipMed)
if ($dnsOk) {
    Bom "$DominioMos aponta para a mesma maquina"
} else {
    Aviso "$DominioMos ainda nao resolve para $ipMed."
    Write-Host @"
     Registro.br -> hipogestao.com.br -> DNS -> modo avancado -> NOVA ENTRADA:
        TIPO  CNAME
        NOME  mos.hipogestao.com.br
        DADOS hipogestao.com.br
     -> SALVAR ALTERACOES. CNAME (e nao A com o IP): se o IP da EC2 mudar
        de novo, so o A de hipogestao.com.br precisa ser trocado.
     As fases base, app, config, usuario e fechamento rodam sem DNS;
     nginx e tls ficam para depois:  -SoServidor -Fases nginx,tls
"@ -ForegroundColor Gray
}

# =====================================================================
# 6. Servidor
# =====================================================================

Titulo "6. Instalacao no servidor"

if ($Simular) {
    Aviso "simulacao: fases que rodariam: $($Fases -join ', ')"
} else {
    Passo "enviando infra\mos para /tmp/mos..."
    & ssh -i $Chave $alvo "rm -rf /tmp/mos && mkdir -p /tmp/mos"
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar /tmp/mos." }
    foreach ($f in $infraMos) {
        & scp -i $Chave (Join-Path $Pasta $f) "${alvo}:/tmp/mos/"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp de $f falhou." }
    }
    # CRLF do Windows quebra o bash ("$'\r': command not found").
    & ssh -i $Chave $alvo "sed -i 's/\r$//' /tmp/mos/*"
    Bom "instalador em /tmp/mos"

    foreach ($fase in $Fases) {
        if (-not $dnsOk -and ($fase -eq "nginx" -or $fase -eq "tls")) {
            Aviso "fase $fase pulada: DNS ainda nao esta no ar"
            continue
        }
        Titulo "6.$fase"
        & ssh -t -i $Chave $alvo "bash /tmp/mos/instalar-instancia-mos.sh $fase"
        if ($LASTEXITCODE -eq 3) { Abortar "fase $fase cancelada por voce. Retome com -SoServidor -Fases $fase,..." }
        if ($LASTEXITCODE -ne 0) { Abortar "fase $fase falhou (codigo $LASTEXITCODE). Corrija e retome com -SoServidor -Fases $fase,..." }
        Bom "fase $fase concluida"
    }
}

# =====================================================================
# 7. Smoke
# =====================================================================

Titulo "7. Smoke"

if ($Simular) {
    Aviso "simulacao: sem smoke"
} else {
    $hMed = Health "https://$Servidor/api/health"
    if (-not $hMed -or $hMed.instancia) { Abortar "a base principal nao respondeu como ela mesma: $($hMed | ConvertTo-Json -Compress)" }
    Bom "https://$Servidor -> $($hMed.empresa)"

    if ($dnsOk) {
        $hMos = Health "https://$DominioMos/api/health"
        if (-not $hMos) {
            Aviso "https://$DominioMos/api/health nao respondeu (certificado ainda nao emitido?)"
        } elseif ($hMos.instancia -ne "MOS") {
            Abortar "https://$DominioMos respondeu instancia='$($hMos.instancia)'. O nginx esta mandando para a base errada."
        } else {
            Bom "https://$DominioMos -> $($hMos.empresa) (instancia $($hMos.instancia))"
        }
    }
}

Titulo "Pronto"
Write-Host @"
  1. Abra https://$DominioMos e entre com o usuario criado (senha 123456;
     o sistema pede a troca). O selo MOS aparece ao lado do logo.
  2. Na base principal NAO precisa relogar -- nada mudou la.
  3. Migration futura roda nas DUAS bases:
       bash /tmp/mos/aplicar-sql-nas-bases.sh /tmp/NNN_x.sql
  4. Pendencias da MOS (doc claude/instancia-mos.md): modelo de proposta,
     roteiro do scorecard, Google Calendar, destinatarios do e-mail.
"@ -ForegroundColor White
