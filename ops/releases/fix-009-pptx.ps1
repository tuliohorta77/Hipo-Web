# =====================================================================
#  HIPO -- 009 corretivo: instalar python-pptx no servidor
# =====================================================================
#
#  O QUE ACONTECEU
#
#  A 009 subiu com -PularInfra. O codigo foi para producao, a migration
#  foi aplicada, os 3 jobs ficaram verdes -- e o passo de infra, que era o
#  unico do deploy que NAO passa pelo CI, ficou de fora.
#
#  Resultado: a tela funciona exatamente como projetada e avisa o que
#  falta ("o servidor esta sem a biblioteca que monta o arquivo").
#  Nada quebrou; falta uma biblioteca.
#
#  Por que o deploy do CI nao resolve sozinho: ele faz rsync do codigo e
#  reinicia o servico. NAO roda pip install. python-pptx esta pinado no
#  api/requirements.txt, mas esse arquivo so e lido num provisionamento
#  do zero.
#
#  O QUE ESTE SCRIPT FAZ
#
#  1. descobre a unit do systemd que serve o HIPO e QUAL interpretador
#     ela usa (venv ou python do sistema) -- instalar no interpretador
#     errado e o jeito mais comum de "instalar" e continuar quebrado;
#  2. instala python-pptx==1.0.2 nesse interpretador;
#  3. confere que o modelo .pptx de 16 MB chegou no rsync do deploy;
#  4. reinicia o servico -- sem isso o import continua falhando, porque
#     o sys.path do processo e montado no boot dele;
#  5. confere pela API que geracao_disponivel virou true.
#
#  NAO instala LibreOffice (o PDF segue desligado). Para isso:
#     .\deploy-009-proposta.ps1 -SomenteInfra -InstalarLibreOffice
#
#  USO
#     .\fix-009-pptx.ps1
#     .\fix-009-pptx.ps1 -SmokeEmail seu-email@dominio.com   # confere de ponta a ponta
#
#  PowerShell 5.1: ASCII puro, sem '&&', sem '2>$null' em comando externo.
# =====================================================================

[CmdletBinding()]
param(
    [string]$Servidor   = "63.179.88.212",
    [string]$UsuarioSsh = "ec2-user",
    [string]$Chave      = "$HOME\Downloads\chave-hipo.pem",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$SmokeEmail = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

function Passo($texto)  { Write-Host "  -> $texto" -ForegroundColor Gray }
function Bom($texto)    { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto)  { Write-Host "  !!  $texto" -ForegroundColor Yellow }

function Abortar($texto) {
    Write-Host ""
    Write-Host "  ABORTADO: $texto" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Executar($descricao, $bloco) {
    Passo $descricao
    & $bloco
    if ($LASTEXITCODE -ne 0) { Abortar "$descricao falhou (codigo $LASTEXITCODE)." }
}

# NAO chame de 'Ssh': o PowerShell resolve funcao antes de executavel, e o
# '& ssh' de dentro chamaria a propria funcao -- recursao infinita.
function Remoto($comando) {
    & ssh.exe -i $Chave -o StrictHostKeyChecking=accept-new "$UsuarioSsh@$Servidor" $comando
}

# =====================================================================
# 0. Pre-voo
# =====================================================================

Titulo "0. Pre-voo"

if (-not (Test-Path $Chave)) { Abortar "chave SSH nao encontrada em $Chave" }
Bom "chave SSH"

Executar "testando o SSH" { Remoto "echo ok" | Out-Null }
Bom "servidor $Servidor responde"

# =====================================================================
# 1. Instalar no interpretador certo
# =====================================================================

Titulo "1. python-pptx no interpretador do servico"

$sh = @'
#!/bin/sh
# Instala python-pptx no interpretador que realmente serve o HIPO.
#
# 'sudo pip install' no python do sistema e um chute: se o app roda em
# venv, a biblioteca entra num lugar que o processo nunca olha, o import
# continua falhando e o sintoma nao muda. Por isso a unit do systemd e
# quem responde qual e o interpretador.
set -eu

echo "--- unit do systemd ---"
UNIT=$(systemctl list-unit-files --no-legend | awk '{print $1}' | grep -i hipo | grep '\.service$' | head -1 || true)
if [ -z "$UNIT" ]; then
    for c in hipo.service hipo-api.service hipo-web.service; do
        if systemctl cat "$c" >/dev/null 2>&1; then UNIT="$c"; break; fi
    done
fi
if [ -z "$UNIT" ]; then
    echo "ERRO_UNIT: nenhuma unit com 'hipo' no nome"
    systemctl list-units --type=service --state=running --no-legend | awk '{print "  running:", $1}'
    exit 1
fi
echo "unit: $UNIT"

EXECBIN=$(systemctl show -p ExecStart --value "$UNIT" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)
SVCUSER=$(systemctl show -p User --value "$UNIT")
[ -n "$SVCUSER" ] || SVCUSER=root
WORKDIR=$(systemctl show -p WorkingDirectory --value "$UNIT")
[ -n "$WORKDIR" ] || WORKDIR=/home/hipo/app

echo "ExecStart: ${EXECBIN:-desconhecido}"
echo "usuario:   $SVCUSER"
echo "workdir:   $WORKDIR"

# venv ou python do sistema? O pyvenv.cfg um nivel acima do bin/ e a marca.
PY=""
EMVENV="nao"
if [ -n "$EXECBIN" ]; then
    D=$(dirname "$EXECBIN")
    if [ -f "$D/../pyvenv.cfg" ]; then
        EMVENV="sim"
        if   [ -x "$D/python3" ]; then PY="$D/python3"
        elif [ -x "$D/python" ];  then PY="$D/python"
        fi
    fi
fi
if [ -z "$PY" ]; then PY=$(command -v python3); fi
echo "interpretador: $PY (venv: $EMVENV)"

echo "--- instalando python-pptx==1.0.2 ---"
if [ "$EMVENV" = "sim" ]; then
    sudo "$PY" -m pip install "python-pptx==1.0.2"
else
    # --user no HOME do usuario do servico. Com 'sudo -iu' o HOME fica
    # certo; sem o -i, o site-packages do usuario e procurado no HOME do
    # ec2-user e a instalacao vai para o lugar errado.
    sudo -iu "$SVCUSER" python3 -m pip install --user "python-pptx==1.0.2"
fi

echo "--- conferindo no ambiente do servico ---"
if sudo -iu "$SVCUSER" "$PY" -c "import pptx; print('python-pptx', pptx.__version__)"; then
    echo "PPTX_OK"
else
    echo "PPTX_FALHOU"
    exit 1
fi

echo "--- modelo da proposta (16 MB, vem pelo rsync) ---"
MOD=$(find "$WORKDIR" -maxdepth 4 -name proposta_modelo.pptx 2>/dev/null | head -1 || true)
if [ -z "$MOD" ]; then
    echo "MODELO_AUSENTE: nao achei proposta_modelo.pptx sob $WORKDIR"
else
    TAM=$(stat -c %s "$MOD")
    echo "modelo: $MOD ($TAM bytes)"
    if [ "$TAM" -gt 1000000 ]; then echo "MODELO_OK"; else echo "MODELO_SUSPEITO"; fi
fi

echo "--- reiniciando $UNIT ---"
# Obrigatorio: o sys.path do processo e montado quando ele sobe. Instalar
# com o servico no ar nao muda nada para quem ja esta rodando.
sudo systemctl restart "$UNIT"
sleep 5
if systemctl is-active --quiet "$UNIT"; then
    echo "SERVICO_ATIVO"
else
    echo "SERVICO_MORTO"
    systemctl status "$UNIT" --no-pager -l | tail -30
    exit 1
fi
'@

$sh = $sh -replace "`r`n", "`n"
$arquivoSh = Join-Path $env:TEMP "fix-009-pptx.sh"
[IO.File]::WriteAllText($arquivoSh, $sh)

Executar "enviando o script" {
    & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new $arquivoSh "${UsuarioSsh}@${Servidor}:/tmp/fix-009-pptx.sh"
}

Passo "rodando no servidor (pode levar um minuto)..."
$saida = Remoto "sh /tmp/fix-009-pptx.sh"
$saida | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
$texto = ($saida -join "`n")

if ($LASTEXITCODE -ne 0) {
    if ($texto -match "ERRO_UNIT") {
        Abortar "nao achei a unit do systemd do HIPO. Rode 'ssh' no servidor, veja 'systemctl list-units --type=service' e me diga o nome."
    }
    Abortar "a instalacao no servidor falhou. A saida acima diz onde."
}

if ($texto -notmatch "PPTX_OK")     { Abortar "python-pptx nao importou no ambiente do servico." }
if ($texto -notmatch "SERVICO_ATIVO") { Abortar "o servico nao voltou depois do restart." }
Bom "python-pptx instalado e servico no ar"

if ($texto -match "MODELO_AUSENTE") {
    Abortar "o modelo proposta_modelo.pptx NAO esta no servidor. Ele e versionado em api/templates/ -- confira se o rsync do deploy exclui .pptx (olhe o passo de deploy no ci-cd.yml)."
}
if ($texto -match "MODELO_SUSPEITO") {
    Aviso "o modelo chegou com tamanho pequeno demais -- pode ser ponteiro de Git LFS em vez do arquivo."
}
if ($texto -match "MODELO_OK") { Bom "modelo de 16 MB no lugar" }

Remoto "rm -f /tmp/fix-009-pptx.sh" | Out-Null

# =====================================================================
# 2. Smoke
# =====================================================================

Titulo "2. Smoke"

Passo "API..."
try {
    $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
    Bom "API viva -- versao $($health.version)"
}
catch { Abortar "a API nao respondeu depois do restart: $($_.Exception.Message)" }

if (-not $SmokeEmail) {
    Aviso "smoke autenticado nao rodou. Para conferir de ponta a ponta:"
    Write-Host "     .\fix-009-pptx.ps1 -SmokeEmail seu-email@dominio.com" -ForegroundColor Gray
}
elseif ($SmokeEmail -like "seu-email*" -or $SmokeEmail -like "voce@*") {
    Aviso "'$SmokeEmail' e placeholder. Use seu e-mail de verdade."
}
else {
    $segura = Read-Host "  Senha de $SmokeEmail (nao aparece na tela)" -AsSecureString
    $senha  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))
    try {
        $login = Invoke-RestMethod -Uri "$UrlPublica/api/auth/login" -Method Post `
            -Body @{ username = $SmokeEmail; password = $senha } -TimeoutSec 20
        $cab = @{ Authorization = "Bearer $($login.access_token)" }

        $lista = Invoke-RestMethod -Headers $cab -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/oportunidades?limit=1"
        $opp = @($lista.itens)[0]
        if (-not $opp) { Aviso "nenhuma oportunidade para testar -- abra uma na tela e confira la." }
        else {
            $padrao = Invoke-RestMethod -Headers $cab -TimeoutSec 30 `
                -Uri "$UrlPublica/api/crm/oportunidades/$($opp.id)/proposta-padrao"
            if ($padrao.geracao_disponivel) {
                Bom "geracao_disponivel = true -- a tela para de avisar"
            }
            else {
                Abortar "geracao_disponivel continua false. O processo que atende a API nao e o que recebeu a biblioteca -- confira se ha mais de uma unit servindo."
            }
            if (-not $padrao.pdf_disponivel) {
                Aviso "pdf_disponivel = false (esperado: o LibreOffice segue de fora). O botao de PDF fica escondido; o PPTX funciona."
            }
        }
    }
    catch { Abortar "smoke autenticado falhou: $($_.Exception.Message)" }
    finally { $senha = $null }
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Resolvido"

Write-Host ""
Write-Host "  Recarregue a aba Proposta (F5) -- o aviso vermelho sai." -ForegroundColor Green
Write-Host ""
Write-Host "  Antes de mandar a primeira para um cliente:" -ForegroundColor Yellow
Write-Host "    1. Perfil -> Contato -> preencha o telefone" -ForegroundColor White
Write-Host "       (sem ele o slide de fechamento sai com um travessao)" -ForegroundColor Gray
Write-Host "    2. Gere a v1 e ABRA o PPTX:" -ForegroundColor White
Write-Host "       slide 5 -- escopo, QTDE. VIDAS, quadro de investimento" -ForegroundColor Gray
Write-Host "       slide 6 -- cliente, seu nome, e-mail, telefone, data, validade" -ForegroundColor Gray
Write-Host ""
Write-Host "  PDF continua desligado (LibreOffice nao esta no servidor)." -ForegroundColor Gray
Write-Host "  Se precisar: .\deploy-009-proposta.ps1 -SomenteInfra -InstalarLibreOffice" -ForegroundColor Gray
Write-Host ""
