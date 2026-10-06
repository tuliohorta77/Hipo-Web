# =====================================================================
#  HIPO -- setup da janela SSH do deploy (uma vez so)
# =====================================================================
#
#  O PROBLEMA QUE ISTO RESOLVE
#
#  A faxina de seguranca de 09/09/2026 fechou a porta 22 da hipo-server
#  para tudo que nao seja o IP de casa. Foi a decisao certa -- antes ela
#  estava em 0.0.0.0/0. Mas o deploy do CI entrava por ali, e o runner do
#  GitHub sai de faixa da Azure, que muda a cada run.
#
#  Resultado: o job 'Deploy -> EC2' morre em 5 segundos no ssh-keyscan,
#  sem mensagem nenhuma. O SG descarta o pacote em silencio, entao nao ha
#  'connection refused' para ler no log -- so o timeout e um exit 1.
#
#  A SOLUCAO
#
#  O proprio runner abre a porta para o /32 dele, deploya, e fecha num
#  passo com if:always(). A porta nunca volta a ficar aberta ao mundo, e
#  a allowlist nao precisa adivinhar o IP de ninguem.
#
#  Para isso o CI precisa de credencial AWS com permissao de MEXER EM UM
#  UNICO SECURITY GROUP. E isso que este script cria:
#
#    1. usuario IAM 'github-actions-hipo-deploy'
#    2. politica inline que so permite authorize/revoke NAQUELE SG
#    3. access key
#    4. os tres secrets no repositorio Hipo-Web
#
#  O QUE ELE NAO PODE FAZER, de proposito: criar instancia, apagar nada,
#  ler S3, tocar em RDS, mexer no SG do Knotty. Se a chave vazar, o
#  estrago possivel e abrir e fechar a porta 22 de uma maquina.
#
#  A UNICA PERMISSAO AMPLA e o ec2:DescribeSecurityGroups, que a AWS nao
#  aceita restringir por recurso -- e leitura de metadado de rede, sem
#  poder de mudanca. Esta ali para a limpeza de regras orfas funcionar.
#
#  PRE-REQUISITOS
#     aws login   (a sessao expira em poucas horas -- ver o doc da conta)
#     gh auth status
#
#  USO
#     .\setup-janela-ssh-deploy.ps1
#     .\setup-janela-ssh-deploy.ps1 -SoInspecionar   # nao cria nada
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$SoInspecionar,

    [string]$Regao      = "eu-central-1",
    [string]$InstanciaId = "i-0b53b29dab89cecb1",   # hipo-server
    [string]$NomeUsuario = "github-actions-hipo-deploy",
    [string]$NomePolitica = "hipo-janela-ssh-deploy",
    [string]$Repo        = "tuliohorta77/Hipo-Web"
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
# 0. Ferramentas e sessao
# =====================================================================

Titulo "0. Ferramentas"

if ($null -eq (Get-Command aws -ErrorAction SilentlyContinue)) {
    Abortar "AWS CLI nao encontrado. winget install --id Amazon.AWSCLI -e"
}
Bom "aws presente"

if ($null -eq (Get-Command gh -ErrorAction SilentlyContinue)) {
    Abortar "gh nao encontrado."
}
Bom "gh presente"

Passo "conferindo a sessao AWS..."
$conta = & aws sts get-caller-identity --query 'Account' --output text
if ($LASTEXITCODE -ne 0 -or -not $conta) {
    Abortar "sessao AWS invalida ou expirada. Rode 'aws login' e tente de novo."
}
$conta = $conta.Trim()
Bom "conta AWS $conta"

# =====================================================================
# 1. Qual Security Group guarda a porta 22 da hipo-server
# =====================================================================

Titulo "1. Security Groups da hipo-server"

# O doc da conta lista DOIS SGs nessa instancia, e um deles esta como
# 'nao inspecionado'. Descobrir aqui qual tem a regra de 22 resolve essa
# pendencia e evita gravar o SG errado no secret.
$sgIds = (& aws ec2 describe-instances --region $Regao --instance-ids $InstanciaId `
    --query 'Reservations[].Instances[].SecurityGroups[].GroupId' --output text)
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler a instancia $InstanciaId" }

$sgIds = @($sgIds.Trim() -split '\s+' | Where-Object { $_ })
Passo "$($sgIds.Count) security group(s): $($sgIds -join ', ')"

$comSsh = @()
foreach ($sg in $sgIds) {
    $json = & aws ec2 describe-security-groups --region $Regao --group-ids $sg --output json
    $dados = ($json | ConvertFrom-Json).SecurityGroups[0]
    Write-Host ""
    Write-Host "     $sg  ($($dados.GroupName))" -ForegroundColor White

    $temSsh = $false
    foreach ($p in $dados.IpPermissions) {
        $de = $p.FromPort; $ate = $p.ToPort
        $porta = if ($de -eq $ate) { "$de" } else { "$de-$ate" }
        $origens = @()
        foreach ($r in $p.IpRanges) {
            $d = if ($r.Description) { " ($($r.Description))" } else { "" }
            $origens += "$($r.CidrIp)$d"
        }
        foreach ($g in $p.UserIdGroupPairs) { $origens += "sg:$($g.GroupId)" }
        if ($origens.Count -eq 0) { $origens = @("(sem origem)") }
        Write-Host "        $($p.IpProtocol)/$porta  <-  $($origens -join ', ')" -ForegroundColor DarkGray
        if ($p.IpProtocol -eq "tcp" -and $de -le 22 -and $ate -ge 22) { $temSsh = $true }
    }
    if ($temSsh) { $comSsh += $sg }
}

Write-Host ""
if ($comSsh.Count -eq 0) {
    Abortar "nenhum SG da instancia tem regra na porta 22. Sem isso nem voce entra -- confira no console."
}
if ($comSsh.Count -gt 1) {
    Aviso "mais de um SG tem regra de 22: $($comSsh -join ', ')"
    Aviso "vou usar o primeiro. Se for o errado, rode de novo com o certo a mao."
}
$sgAlvo = $comSsh[0]
Bom "SG da janela: $sgAlvo"

$arnSg = "arn:aws:ec2:${Regao}:${conta}:security-group/$sgAlvo"
Passo "ARN: $arnSg"

if ($SoInspecionar) {
    Titulo "So inspecao -- nada foi criado"
    Write-Host ""
    Write-Host "  Rode sem -SoInspecionar para criar o usuario e os secrets." -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# =====================================================================
# 2. Usuario IAM
# =====================================================================

Titulo "2. Usuario IAM $NomeUsuario"

# ${sgAlvo} com chaves: o '?' colado num nome de variavel e aceito pelo
# PowerShell COMO PARTE DO NOME. Sem as chaves, isto vira $sgAlvo? -- uma
# variavel que nunca existiu -- e a pergunta sai sem dizer em qual SG voce
# esta prestes a mexer. Errou aqui uma vez.
Confirmar "Criar o usuario IAM e a politica restrita ao ${sgAlvo}?"

# list-users em vez de get-user: o get-user de um usuario inexistente --
# que e o caso NORMAL na primeira execucao -- escreve NoSuchEntity no
# stderr. Com $ErrorActionPreference = "Stop", stderr de comando nativo
# vira NativeCommandError terminante e o script morre no caminho feliz.
# Nem '2>$null' salva: o redirecionamento acontece depois de o PowerShell
# ja ter decidido que aquilo era um erro.
$listaUsuarios = & aws iam list-users --query 'Users[].UserName' --output text
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui listar os usuarios IAM" }
$nomes = @()
if ($listaUsuarios) { $nomes = @($listaUsuarios.Trim() -split '\s+' | Where-Object { $_ }) }
$existe = $nomes -contains $NomeUsuario

if ($existe) {
    Aviso "o usuario ja existe -- vou apenas atualizar a politica e criar uma chave nova"
}
else {
    Passo "criando..."
    & aws iam create-user --user-name $NomeUsuario --tags "Key=Projeto,Value=HIPO" "Key=Uso,Value=janela-ssh-deploy" --output text | Out-Null
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar o usuario IAM" }
    Bom "usuario criado"
}

# =====================================================================
# 3. Politica minima
# =====================================================================

Titulo "3. Politica inline"

# Arquivo em disco em vez de JSON na linha de comando: aspas aninhadas
# entre PowerShell e a CLI da AWS sao uma fonte classica de erro mudo --
# a politica entra torta e so aparece quando o CI recebe AccessDenied.
$politica = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AbrirEFecharJanelaSSH",
      "Effect": "Allow",
      "Action": [
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress"
      ],
      "Resource": "$arnSg"
    },
    {
      "Sid": "LerRegrasParaLimparOrfas",
      "Effect": "Allow",
      "Action": "ec2:DescribeSecurityGroups",
      "Resource": "*"
    }
  ]
}
"@

$arquivo = Join-Path $env:TEMP "hipo-politica-janela.json"
$politica | Out-File -Encoding ascii $arquivo

Passo "aplicando em $NomeUsuario..."
& aws iam put-user-policy --user-name $NomeUsuario --policy-name $NomePolitica --policy-document "file://$arquivo"
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui aplicar a politica" }
Remove-Item $arquivo -Force -ErrorAction SilentlyContinue
Bom "politica aplicada -- authorize/revoke so no $sgAlvo"

# =====================================================================
# 4. Access key
# =====================================================================

Titulo "4. Access key"

# A AWS permite duas chaves por usuario. Se ja houver duas, criar a
# terceira falha -- e melhor dizer isso agora do que no meio.
# Usuario recem-criado nao tem chave: --output text devolve vazio, e
# .Trim() encadeado direto num nulo estoura. Testar antes de encostar.
$saidaChaves = & aws iam list-access-keys --user-name $NomeUsuario --query 'AccessKeyMetadata[].AccessKeyId' --output text
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui listar as access keys de $NomeUsuario" }
$chaves = @()
if ($saidaChaves) { $chaves = @($saidaChaves.Trim() -split '\s+' | Where-Object { $_ }) }

if ($chaves.Count -ge 2) {
    Aviso "o usuario ja tem $($chaves.Count) chaves: $($chaves -join ', ')"
    Confirmar "Apagar a mais antiga para criar uma nova?"
    & aws iam delete-access-key --user-name $NomeUsuario --access-key-id $chaves[0]
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui apagar a chave antiga" }
    Bom "chave $($chaves[0]) removida"
}

Passo "criando chave..."
$nova = (& aws iam create-access-key --user-name $NomeUsuario --output json) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar a access key" }

$idChave     = $nova.AccessKey.AccessKeyId
$segredo     = $nova.AccessKey.SecretAccessKey
Bom "chave criada: $idChave"
Aviso "o segredo aparece uma vez so na vida. Ele vai direto para o GitHub abaixo -- nao e impresso aqui."

# =====================================================================
# 5. Secrets no repositorio
# =====================================================================

Titulo "5. Secrets em $Repo"

Passo "AWS_ACCESS_KEY_ID..."
& gh secret set AWS_ACCESS_KEY_ID --repo $Repo --body $idChave
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui gravar AWS_ACCESS_KEY_ID" }

Passo "AWS_SECRET_ACCESS_KEY..."
& gh secret set AWS_SECRET_ACCESS_KEY --repo $Repo --body $segredo
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui gravar AWS_SECRET_ACCESS_KEY" }

Passo "EC2_SECURITY_GROUP_ID..."
& gh secret set EC2_SECURITY_GROUP_ID --repo $Repo --body $sgAlvo
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui gravar EC2_SECURITY_GROUP_ID" }

# Some da memoria da sessao. Nao e blindagem seria -- o PowerShell nao
# garante zerar a string -- mas evita a chave sobreviver num $segredo
# esquecido se voce continuar trabalhando neste terminal.
$segredo = $null

Bom "tres secrets gravados"

# =====================================================================
# Fim
# =====================================================================

Titulo "Pronto -- falta subir o workflow"

Write-Host ""
Write-Host "  O ci-cd.yml novo (com abrir/fechar janela) ainda precisa" -ForegroundColor Yellow
Write-Host "  chegar na main. O push na main JA dispara o deploy, entao" -ForegroundColor Yellow
Write-Host "  isto tambem sobe a 011 que ficou parada:" -ForegroundColor Yellow
Write-Host ""
Write-Host "     git checkout main" -ForegroundColor White
Write-Host "     git pull" -ForegroundColor White
Write-Host "     git add .github/workflows/ci-cd.yml" -ForegroundColor White
Write-Host "     git commit -m `"ci: janela SSH por run no security group do deploy`"" -ForegroundColor White
Write-Host "     git push origin main" -ForegroundColor White
Write-Host ""
Write-Host "  Acompanhe:" -ForegroundColor Gray
Write-Host "     gh run watch --exit-status" -ForegroundColor White
Write-Host ""
Write-Host "  O que tem de aparecer no job Deploy, nesta ordem:" -ForegroundColor Gray
Write-Host "     Abrir janela SSH no Security Group   -> 'abrindo 22/tcp para X/32'" -ForegroundColor DarkGray
Write-Host "     Adicionar EC2 aos hosts conhecidos   -> passa em vez de morrer em 5s" -ForegroundColor DarkGray
Write-Host "     Fechar janela SSH no Security Group  -> 'janela fechada'" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Depois, confira que nao sobrou porta aberta:" -ForegroundColor Gray
Write-Host "     .\setup-janela-ssh-deploy.ps1 -SoInspecionar" -ForegroundColor White
Write-Host "  A unica regra de 22 deve ser o seu /32 de casa. Se sobrar uma" -ForegroundColor DarkGray
Write-Host "  com a descricao 'github-actions-deploy', o run seguinte a" -ForegroundColor DarkGray
Write-Host "  limpa sozinho antes de abrir a dele." -ForegroundColor DarkGray
Write-Host ""
