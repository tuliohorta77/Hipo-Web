# =====================================================================
#  HIPO -- diagnostico: por que o job de Deploy morreu no ssh-keyscan
# =====================================================================
#
#  CONTEXTO
#
#  Run 34298903552 (main, merge do PR #6): Backend Tests verde, Frontend
#  Tests verde, e o 'Deploy -> EC2' vermelho em 10 segundos, no passo
#  'Adicionar EC2 aos hosts conhecidos'. Esse passo e uma linha so:
#
#      ssh-keyscan -H ${{ secrets.EC2_HOST }} >> ~/.ssh/known_hosts
#
#  Ele roda ANTES de qualquer rsync. Nada foi para a producao, e nada
#  ficou pela metade la: a versao antiga continua inteira no ar.
#
#  Codigo nao tem culpa aqui -- a 011 passou nos 453 testes e no build.
#  O que quebrou e a ponte do runner para a maquina.
#
#  AS QUATRO HIPOTESES (o script separa uma da outra)
#
#    A. O secret EC2_HOST sumiu ou ficou vazio. ssh-keyscan sem host
#       imprime o modo de usar e sai com erro -- instantaneo, como foi.
#    B. O IP da EC2 mudou. Instancia reiniciada sem Elastic IP ganha IP
#       novo; o DNS acompanha se estiver certo, mas o secret nao.
#    C. A maquina esta parada ou a porta 22 fechou (Security Group
#       editado, instancia stopped).
#    D. A chave EC2_SSH_KEY venceu ou foi trocada. Menos provavel: o
#       passo anterior, o ssh-agent, ficou verde -- mas ele so carrega a
#       chave, nao conversa com o servidor.
#
#  USO
#     .\diagnostico-deploy-ec2.ps1
#     .\diagnostico-deploy-ec2.ps1 -RunId 34298903552
#     .\diagnostico-deploy-ec2.ps1 -Ip 1.2.3.4     # para testar outro
#
#  So le. Nao muda secret, nao mexe na EC2, nao dispara deploy.
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [string]$RunId    = "34298903552",
    [string]$Ip       = "63.179.88.212",
    [string]$Dominio  = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem"
)

$ProgressPreference = "SilentlyContinue"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

function Passo($texto)  { Write-Host "  -> $texto" -ForegroundColor Gray }
function Bom($texto)    { Write-Host "  OK  $texto" -ForegroundColor Green }
function Ruim($texto)   { Write-Host "  XX  $texto" -ForegroundColor Red }
function Aviso($texto)  { Write-Host "  !!  $texto" -ForegroundColor Yellow }

# Cada checagem grava aqui o que descobriu, para o veredito do fim nao
# depender de ninguem lembrar de rolar a tela para cima.
$achados = @{}

# =====================================================================
# 1. O log do passo que falhou
# =====================================================================

Titulo "1. Log do passo que falhou (run $RunId)"

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
if (-not $temGh) {
    Aviso "gh nao instalado -- veja em https://github.com/tuliohorta77/Hipo-Web/actions/runs/$RunId"
}
else {
    Passo "gh run view --log-failed"
    $log = & gh run view $RunId --log-failed
    if ($LASTEXITCODE -ne 0) {
        Aviso "nao consegui ler o log do run $RunId"
    }
    else {
        # Interessa so o bloco do keyscan. O log inteiro tem centenas de
        # linhas de setup que nao dizem nada.
        $linhas = @($log | Where-Object { $_ -match "keyscan|known_hosts|usage:|Connection|timed out|refused|No route|Permission denied|Error:|##\[error\]" })
        if ($linhas.Count -eq 0) {
            Aviso "nenhuma linha reconhecida -- despejando as 40 ultimas do log"
            $log | Select-Object -Last 40 | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
        }
        else {
            foreach ($l in $linhas) { Write-Host "     $l" -ForegroundColor DarkGray }
        }

        $textoLog = ($log -join "`n")
        if ($textoLog -match "usage: ssh-keyscan") {
            $achados["log"] = "secret-vazio"
            Ruim "o ssh-keyscan imprimiu o modo de usar -- ele rodou SEM host. EC2_HOST vazio ou inexistente."
        }
        elseif ($textoLog -match "timed out|Connection timed out|No route to host") {
            $achados["log"] = "host-mudo"
            Ruim "o ssh-keyscan nao obteve resposta do host -- maquina parada, IP velho ou porta 22 fechada."
        }
        elseif ($textoLog -match "Connection refused") {
            $achados["log"] = "porta-fechada"
            Ruim "conexao recusada na porta 22 -- o sshd nao esta escutando (ou o SG recusa)."
        }
        else {
            $achados["log"] = "indefinido"
            Aviso "o log nao cai em nenhum padrao conhecido -- leia as linhas acima"
        }
    }
}

# =====================================================================
# 2. Os secrets existem?
# =====================================================================

Titulo "2. Secrets do repositorio"

if ($temGh) {
    # gh nunca mostra o VALOR de um secret. O que da para saber e se ele
    # existe e quando foi atualizado -- e e o suficiente para separar
    # 'sumiu' de 'esta la e errado'.
    $bruto = & gh secret list --json name,updatedAt
    if ($LASTEXITCODE -ne 0) {
        Aviso "nao consegui listar os secrets (precisa de permissao de admin no repo)"
    }
    else {
        $secrets = @($bruto | ConvertFrom-Json)
        foreach ($s in $secrets) {
            Write-Host ("     {0,-20} atualizado em {1}" -f $s.name, $s.updatedAt) -ForegroundColor DarkGray
        }
        foreach ($nome in @("EC2_HOST", "EC2_USER", "EC2_SSH_KEY")) {
            if ($secrets.name -contains $nome) { Bom "$nome existe" }
            else { Ruim "$nome NAO EXISTE no repositorio -- e a causa direta da falha" }
        }
        if (-not ($secrets.name -contains "EC2_HOST")) { $achados["secret"] = "ausente" }
    }
}

# =====================================================================
# 3. A maquina esta viva? A porta 22 responde?
# =====================================================================

Titulo "3. Alcance da EC2 ($Ip)"

Passo "porta 22..."
$porta22 = $false
try {
    $porta22 = Test-NetConnection -ComputerName $Ip -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
}
catch { $porta22 = $false }

if ($porta22) { Bom "porta 22 aberta em $Ip" }
else { Ruim "porta 22 NAO responde em $Ip" }
$achados["porta22"] = $porta22

Passo "porta 80..."
$porta80 = $false
try {
    $porta80 = Test-NetConnection -ComputerName $Ip -Port 80 -InformationLevel Quiet -WarningAction SilentlyContinue
}
catch { $porta80 = $false }

if ($porta80) { Bom "porta 80 aberta -- a maquina esta ligada e servindo" }
else { Aviso "porta 80 tambem nao responde" }
$achados["porta80"] = $porta80

# Porta 80 viva com 22 morta e um Security Group editado. As duas mortas
# e a maquina parada, ou o IP nao ser mais dela.
if ($porta80 -and -not $porta22) {
    Ruim "80 viva e 22 morta: isso e Security Group, nao maquina parada."
}

# =====================================================================
# 4. O IP do secret ainda e o IP da maquina?
# =====================================================================

Titulo "4. DNS de $Dominio"

try {
    $reg = @(Resolve-DnsName -Name $Dominio -Type A -ErrorAction Stop | Where-Object { $_.IPAddress })
    if ($reg.Count -eq 0) {
        Aviso "nenhum registro A para $Dominio"
    }
    else {
        foreach ($r in $reg) { Write-Host "     $Dominio -> $($r.IPAddress)" -ForegroundColor DarkGray }
        $ips = @($reg | ForEach-Object { $_.IPAddress })
        if ($ips -contains $Ip) {
            Bom "o DNS aponta para $Ip -- o IP que voce esta testando e o certo"
            $achados["dns"] = "bate"
        }
        else {
            Ruim "o DNS aponta para $($ips -join ', ') e NAO para $Ip."
            Aviso "a EC2 provavelmente ganhou IP novo (reboot sem Elastic IP). O secret EC2_HOST ficou velho."
            $achados["dns"] = "diverge"
            $achados["ipNovo"] = $ips[0]
        }
    }
}
catch { Aviso "nao consegui resolver $Dominio : $($_.Exception.Message)" }

# =====================================================================
# 5. O mesmo comando que o CI roda, da sua maquina
# =====================================================================

Titulo "5. ssh-keyscan local (o comando exato do CI)"

if ($null -eq (Get-Command ssh-keyscan -ErrorAction SilentlyContinue)) {
    Aviso "ssh-keyscan nao esta no PATH -- pule esta secao"
}
else {
    Passo "ssh-keyscan -H $Ip"
    $chaves = & ssh-keyscan -H -T 10 $Ip
    if ($chaves) {
        Bom "$(@($chaves).Count) chave(s) de host obtidas -- do SEU ponto de rede o keyscan funciona"
        $achados["keyscanLocal"] = $true
        Aviso "se aqui funciona e no CI nao, o problema NAO e a maquina: e o valor do secret."
    }
    else {
        Ruim "nenhuma chave obtida -- o host nao respondeu daqui tambem"
        $achados["keyscanLocal"] = $false
    }
}

# =====================================================================
# 6. SSH de verdade, com a chave
# =====================================================================

Titulo "6. SSH com a chave"

if (-not (Test-Path $Chave)) {
    Aviso "chave nao encontrada em $Chave -- pulando"
}
elseif (-not $porta22) {
    Aviso "porta 22 fechada -- nao adianta tentar o SSH"
}
else {
    Passo "ssh $Usuario@$Ip"
    $saida = & ssh -i $Chave -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$Usuario@$Ip" "echo CONECTOU; systemctl is-active hipo-api; systemctl is-active nginx"
    if ($LASTEXITCODE -eq 0) {
        Bom "SSH funciona com a sua chave"
        foreach ($l in @($saida)) { Write-Host "     $l" -ForegroundColor DarkGray }
        Aviso "sua chave entra. Se o CI nao entra, confira o secret EC2_SSH_KEY (privada inteira, com as linhas BEGIN/END)."
    }
    else {
        Ruim "SSH falhou (codigo $LASTEXITCODE)"
        foreach ($l in @($saida)) { Write-Host "     $l" -ForegroundColor DarkGray }
    }
}

# =====================================================================
# Veredito
# =====================================================================

Titulo "Veredito"

Write-Host ""
if ($achados["log"] -eq "secret-vazio" -or $achados["secret"] -eq "ausente") {
    Write-Host "  O secret EC2_HOST esta vazio ou nao existe." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Regrave e redeploye:" -ForegroundColor Yellow
    Write-Host "     gh secret set EC2_HOST --body `"$Ip`"" -ForegroundColor White
    Write-Host "     gh secret set EC2_USER --body `"$Usuario`"" -ForegroundColor White
    Write-Host "     .\deploy-007-retomar.ps1" -ForegroundColor White
}
elseif ($achados["dns"] -eq "diverge") {
    Write-Host "  A EC2 mudou de IP. O secret aponta para o endereco antigo." -ForegroundColor Red
    Write-Host ""
    Write-Host "  IP novo pelo DNS: $($achados['ipNovo'])" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "     gh secret set EC2_HOST --body `"$($achados['ipNovo'])`"" -ForegroundColor White
    Write-Host "     .\deploy-007-retomar.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "  Depois, para nao acontecer de novo: associe um Elastic IP a" -ForegroundColor Gray
    Write-Host "  instancia. Sem ele, todo stop/start sorteia um IP novo e o" -ForegroundColor Gray
    Write-Host "  deploy quebra de novo, sempre no mesmo passo." -ForegroundColor Gray
}
elseif ($achados["porta80"] -and -not $achados["porta22"]) {
    Write-Host "  A maquina esta viva (porta 80 responde) mas a 22 esta fechada." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Isso e Security Group: alguem tirou a regra de SSH, ou ela" -ForegroundColor Yellow
    Write-Host "  esta restrita a um IP que nao inclui os runners do GitHub" -ForegroundColor Yellow
    Write-Host "  (que saem de faixas publicas e variaveis da Azure)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Console AWS -> EC2 -> hipo-server -> Security -> Inbound" -ForegroundColor White
    Write-Host "  A regra de deploy precisa ser 22/tcp aberta, ou a faixa dos" -ForegroundColor White
    Write-Host "  runners. Depois: .\deploy-007-retomar.ps1" -ForegroundColor White
}
elseif (-not $achados["porta22"] -and -not $achados["porta80"]) {
    Write-Host "  A maquina nao responde em nenhuma porta." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Ou a instancia esta parada, ou esse IP nao e mais dela." -ForegroundColor Yellow
    Write-Host "  Console AWS -> EC2 -> hipo-server: confira o estado e o IP" -ForegroundColor White
    Write-Host "  publico atual. Se mudou, regrave o secret e retome:" -ForegroundColor White
    Write-Host "     gh secret set EC2_HOST --body `"<ip novo>`"" -ForegroundColor White
    Write-Host "     .\deploy-007-retomar.ps1" -ForegroundColor White
}
else {
    Write-Host "  Nao fechei o diagnostico sozinho." -ForegroundColor Yellow
    Write-Host "  Me mande as linhas da secao 1 e o que apareceu na 3 e na 4." -ForegroundColor White
}

Write-Host ""
Write-Host "  Em qualquer um dos casos: NADA foi para producao e nada ficou" -ForegroundColor Gray
Write-Host "  pela metade la. O keyscan e o primeiro passo, antes do rsync." -ForegroundColor Gray
Write-Host "  O codigo da 011 ja esta na main -- falta so o deploy rodar." -ForegroundColor Gray
Write-Host ""
