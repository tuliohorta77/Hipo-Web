# =====================================================================
#  HIPO -- libera o SEU IP atual na porta 22
# =====================================================================
#
#  QUANDO USAR
#
#  O SSH parou de conectar e o erro e TIMEOUT ("Connection timed out"),
#  nao "Connection refused". Essa diferenca e o diagnostico inteiro:
#
#    timed out  -> o Security Group descartou o pacote em silencio. Seu
#                  IP nao esta na lista. E este script.
#    refused    -> chegou na maquina e o sshd nao atendeu. Problema no
#                  servidor, nao no SG -- este script nao ajuda.
#
#  POR QUE ISTO E RECORRENTE
#
#  Desde a faxina de 09/09/2026 a porta 22 so aceita IP conhecido. Seu IP
#  residencial e dinamico: a operadora troca sozinha, e no dia seguinte o
#  deploy para no pre-voo. O runner do GitHub resolve o proprio caso
#  abrindo e fechando a janela a cada run; voce precisa deste.
#
#  A REGRA DE OURO, que este script respeita: o authorize do IP novo vem
#  ANTES do revoke do antigo. Na ordem inversa, uma falha no meio tranca
#  voce do lado de fora da propria maquina.
#
#  USO
#     .\liberar-meu-ip-ssh.ps1
#     .\liberar-meu-ip-ssh.ps1 -LimparAntigos    # remove /32 que nao sao o seu
#     .\liberar-meu-ip-ssh.ps1 -IncluirKnotty    # libera nos dois projetos
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$LimparAntigos,
    [switch]$IncluirKnotty,

    [string]$Regao    = "eu-central-1",
    [string]$SgHipo   = "sg-09a195baadebed788",
    [string]$SgKnotty = "sg-09f5e0b3ba83555a7",
    [string]$IpHipo   = "63.179.88.212"
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

function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

# =====================================================================
# 1. Qual e o seu IP agora
# =====================================================================

Titulo "1. Seu IP publico"

if ($null -eq (Get-Command aws -ErrorAction SilentlyContinue)) {
    Abortar "AWS CLI nao encontrado."
}

& aws sts get-caller-identity --query 'Account' --output text | Out-Null
if ($LASTEXITCODE -ne 0) {
    Abortar "sessao AWS invalida ou expirada. Rode 'aws login' e tente de novo."
}

try {
    $meuIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 20).Trim()
}
catch { Abortar "nao consegui descobrir seu IP: $($_.Exception.Message)" }

if ($meuIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    Abortar "resposta inesperada de checkip: '$meuIp'"
}
Bom "seu IP: $meuIp"

$meuCidr = "$meuIp/32"

# =====================================================================
# 2. O que ja esta liberado
# =====================================================================

$grupos = @(@{ Id = $SgHipo; Nome = "hipo-s (HIPO)" })
if ($IncluirKnotty) {
    $grupos += @{ Id = $SgKnotty; Nome = "launch-wizard-1 (Knotty)" }
}

foreach ($g in $grupos) {
    Titulo "2. $($g.Nome) -- $($g.Id)"

    $json = & aws ec2 describe-security-groups --region $Regao --group-ids $g.Id --output json
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler o $($g.Id)" }
    $dados = ($json | ConvertFrom-Json).SecurityGroups[0]

    $regras22 = @()
    foreach ($p in $dados.IpPermissions) {
        if ($p.IpProtocol -ne "tcp") { continue }
        if ($p.FromPort -gt 22 -or $p.ToPort -lt 22) { continue }
        foreach ($r in $p.IpRanges) {
            $regras22 += [pscustomobject]@{
                Cidr = $r.CidrIp
                Desc = $r.Description
            }
        }
    }

    if ($regras22.Count -eq 0) { Aviso "nenhuma regra na porta 22" }
    foreach ($r in $regras22) {
        $marca = ""
        if ($r.Cidr -eq $meuCidr) { $marca = "  <== voce, agora" }
        $d = if ($r.Desc) { " ($($r.Desc))" } else { "" }
        Write-Host "     22/tcp <- $($r.Cidr)$d$marca" -ForegroundColor DarkGray
    }

    # -- authorize ANTES do revoke. Sempre. --
    if ($regras22.Cidr -contains $meuCidr) {
        Bom "seu IP ja esta liberado aqui"
    }
    else {
        Passo "liberando $meuCidr..."
        $desc = "tulio-$(Get-Date -Format 'yyyy-MM-dd')"
        & aws ec2 authorize-security-group-ingress --region $Regao --group-id $g.Id `
            --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$meuCidr,Description=$desc}]" | Out-Null
        if ($LASTEXITCODE -ne 0) { Abortar "nao consegui liberar $meuCidr no $($g.Id)" }
        Bom "liberado"
    }

    # -- limpeza opcional dos antigos --
    if ($LimparAntigos) {
        # NUNCA toca nas regras do CI: elas nascem e morrem dentro de um
        # run, e remover uma no meio derruba o deploy de quem esta
        # esperando. O nome da descricao e o contrato entre os dois
        # scripts.
        $antigos = @($regras22 | Where-Object {
            $_.Cidr -ne $meuCidr -and
            $_.Cidr -ne "0.0.0.0/0" -and
            $_.Desc -ne "github-actions-deploy"
        })

        if ($antigos.Count -eq 0) {
            Bom "nada antigo para limpar"
        }
        else {
            Write-Host ""
            Aviso "regras de 22 que NAO sao o seu IP atual:"
            foreach ($a in $antigos) {
                $d = if ($a.Desc) { " ($($a.Desc))" } else { "" }
                Write-Host "     $($a.Cidr)$d" -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "  Pode ser seu IP de ontem -- ou o de outra pessoa que" -ForegroundColor Gray
            Write-Host "  precisa entrar. Removendo, ela perde o acesso." -ForegroundColor Gray
            Confirmar "Remover essas $($antigos.Count) regra(s) do $($g.Id)?"

            foreach ($a in $antigos) {
                Passo "removendo $($a.Cidr)..."
                & aws ec2 revoke-security-group-ingress --region $Regao --group-id $g.Id `
                    --protocol tcp --port 22 --cidr $a.Cidr | Out-Null
                if ($LASTEXITCODE -ne 0) { Aviso "falhou remover $($a.Cidr) -- seguindo" }
                else { Bom "$($a.Cidr) removido" }
            }
        }
    }
}

# =====================================================================
# 3. Prova
# =====================================================================

Titulo "3. Prova"

Passo "porta 22 em $IpHipo..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $IpHipo -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
}
catch { $aberta = $false }

if ($aberta) {
    Bom "a porta 22 responde -- pode rodar o deploy"
    Write-Host ""
    Write-Host "     .\deploy-012-anexos-backend.ps1" -ForegroundColor White
    Write-Host ""
}
else {
    Aviso "ainda nao responde."
    Write-Host ""
    Write-Host "  A regra do SG vale em segundos, entao espere ~10s e tente de" -ForegroundColor Gray
    Write-Host "  novo. Se continuar mudo, o problema nao e o seu IP:" -ForegroundColor Gray
    Write-Host "    - a instancia pode estar parada (console EC2 -> hipo-server)" -ForegroundColor Gray
    Write-Host "    - ou voce esta atras de uma rede que faz NAT com IP" -ForegroundColor Gray
    Write-Host "      diferente do que o checkip enxergou (VPN, 4G do celular)." -ForegroundColor Gray
    Write-Host ""
}
