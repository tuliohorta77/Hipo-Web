# =====================================================================
#  HIPO -- setup do bucket S3 de anexos (uma vez so)
# =====================================================================
#
#  PARA QUE
#
#  Anexar imagem na tarefa (o print do WhatsApp que prova o relato). Os
#  arquivos vao para o S3, nao para o disco da EC2: o EBS da t3.medium
#  nao cresce sozinho, e arquivo no disco da instancia morre com ela --
#  a mesma fragilidade que ja esta como pendencia nos backups do Knotty.
#
#  POR QUE S3 SAI BARATO AQUI
#
#  O boto3 JA esta instalado na EC2 (veio do SES). Nenhum passo de
#  servidor, nenhum pip install a mao -- ao contrario do python-pptx da
#  009, que subiu verde e quebrou na tela. Ver a secao 5 do
#  claude/armadilhas-deploy-e-fuso.md.
#
#  O QUE ESTE SCRIPT FAZ
#
#    1. cria o bucket hipo-anexos-<conta> em eu-central-1
#    2. bloqueia acesso publico (tudo privado; leitura so por presigned)
#    3. liga versionamento (exclusao acidental tem volta)
#    4. liga criptografia SSE-S3
#    5. descobre COMO a EC2 autentica na AWS e pendura a politica la
#
#  O passo 5 e o unico com surpresa. O email_ses.py usa a cadeia padrao
#  do SDK, que aceita os dois modos:
#     - role na instancia  -> politica vai na role (sem chave em lugar
#                             nenhum; e o modo bom)
#     - chave no ambiente  -> politica vai no usuario IAM dono da chave
#  Se nao houver role, o script PARA e explica as saidas em vez de
#  escolher por voce -- criar chave nova onde ja existe uma e como se
#  duplica credencial sem ninguem perceber.
#
#  SEM CORS de proposito: o upload passa pela API (browser -> FastAPI ->
#  S3), entao o navegador nunca fala direto com o bucket na escrita. Na
#  leitura ele fala, mas GET presigned em <img src> nao dispara preflight.
#
#  USO
#     .\setup-s3-anexos.ps1
#     .\setup-s3-anexos.ps1 -SoInspecionar
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$SoInspecionar,

    [string]$Regao       = "eu-central-1",
    [string]$InstanciaId = "i-0b53b29dab89cecb1",   # hipo-server
    [string]$NomePolitica = "hipo-anexos-s3",
    [string]$Bucket      = ""    # vazio = hipo-anexos-<conta>
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
# 0. Ferramentas e conta
# =====================================================================

Titulo "0. Ferramentas"

if ($null -eq (Get-Command aws -ErrorAction SilentlyContinue)) {
    Abortar "AWS CLI nao encontrado."
}
Bom "aws presente"

$conta = & aws sts get-caller-identity --query 'Account' --output text
if ($LASTEXITCODE -ne 0 -or -not $conta) {
    Abortar "sessao AWS invalida ou expirada. Rode 'aws login' e tente de novo."
}
$conta = $conta.Trim()
Bom "conta AWS $conta"

if (-not $Bucket) { $Bucket = "hipo-anexos-$conta" }
Passo "bucket alvo: $Bucket"

$arnBucket  = "arn:aws:s3:::$Bucket"
$arnObjetos = "arn:aws:s3:::$Bucket/*"

# =====================================================================
# 1. Como a EC2 autentica na AWS
# =====================================================================

Titulo "1. Como a hipo-server autentica"

# list-users nao serve aqui: o que decide e o instance profile da
# instancia. Sem ele, o boto3 do SES so pode estar usando chave do
# ambiente -- e a politica tem de ir no dono daquela chave.
$perfil = & aws ec2 describe-instances --region $Regao --instance-ids $InstanciaId `
    --query 'Reservations[].Instances[].IamInstanceProfile.Arn' --output text
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler a instancia $InstanciaId" }

$perfil = ($perfil | Out-String).Trim()
$temRole = $perfil -and $perfil -ne "None"

if ($temRole) {
    Bom "instance profile: $perfil"
    # O nome da role nem sempre e o nome do profile. Perguntar ao profile.
    $nomePerfil = $perfil.Split('/')[-1]
    $role = & aws iam get-instance-profile --instance-profile-name $nomePerfil `
        --query 'InstanceProfile.Roles[0].RoleName' --output text
    if ($LASTEXITCODE -ne 0 -or -not $role) {
        Abortar "o profile $nomePerfil nao tem role legivel"
    }
    $role = $role.Trim()
    Bom "role da instancia: $role"
}
else {
    Aviso "a instancia NAO tem role -- o boto3 do SES esta usando chave do ambiente"
    Write-Host ""
    Write-Host "  Duas saidas, e a escolha e sua:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  A) Pendurar a politica no usuario IAM dono da chave que ja" -ForegroundColor White
    Write-Host "     esta no /home/hipo/app/.env. Descubra qual e:" -ForegroundColor White
    Write-Host "       ssh -i `$HOME\Downloads\chave-hipo.pem ec2-user@63.179.88.212 ``" -ForegroundColor Gray
    Write-Host "         `"sudo grep -o 'AWS_ACCESS_KEY_ID=.*' /home/hipo/app/.env | cut -c1-30`"" -ForegroundColor Gray
    Write-Host "     e depois:" -ForegroundColor White
    Write-Host "       aws sts get-access-key-info --access-key-id <AKIA...>" -ForegroundColor Gray
    Write-Host "     Rode este script de novo passando -Bucket e aplique a mao," -ForegroundColor White
    Write-Host "     ou me diga o nome do usuario que eu ajusto o script." -ForegroundColor White
    Write-Host ""
    Write-Host "  B) Criar uma role e anexar a instancia (melhor a longo" -ForegroundColor White
    Write-Host "     prazo: some a chave do .env, e o SES passa a usar a role" -ForegroundColor White
    Write-Host "     tambem). Da para anexar sem reiniciar a instancia, mas e" -ForegroundColor White
    Write-Host "     mudanca de infra que merece janela e conferencia do SES" -ForegroundColor White
    Write-Host "     depois." -ForegroundColor White
    Write-Host ""
    Abortar "escolha A ou B antes de seguir -- nao vou criar credencial nova por conta propria."
}

# list-buckets e nao head-bucket: head-bucket de bucket inexistente --
# que e exatamente o caso que a inspecao quer detectar -- escreve no
# stderr, e stderr de comando nativo com $ErrorActionPreference = "Stop"
# vira NativeCommandError terminante. Nem '2>&1' salva; o redirecionamento
# acontece depois de o PowerShell ja ter decidido que aquilo era um erro.
# Mesma armadilha que matou o setup-janela-ssh-deploy no primeiro tiro.
$listaBuckets = & aws s3api list-buckets --query 'Buckets[].Name' --output text
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui listar os buckets" }
$nomes = @()
if ($listaBuckets) { $nomes = @($listaBuckets.Trim() -split '\s+' | Where-Object { $_ }) }
$existe = $nomes -contains $Bucket

if ($SoInspecionar) {
    Titulo "So inspecao"
    if ($existe) { Bom "$Bucket existe" } else { Aviso "$Bucket ainda nao existe" }
    Write-Host ""
    Write-Host "  Rode sem -SoInspecionar para criar." -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# =====================================================================
# 2. Bucket
# =====================================================================

Titulo "2. Bucket $Bucket"

if ($existe) {
    Aviso "o bucket ja existe -- vou apenas reaplicar as protecoes"
}
else {
    Confirmar "Criar o bucket $Bucket em ${Regao}?"
    # Fora de us-east-1, a criacao EXIGE LocationConstraint. Sem ele a API
    # aceita o comando e devolve um erro de regiao que nao diz isso.
    & aws s3api create-bucket --bucket $Bucket --region $Regao `
        --create-bucket-configuration "LocationConstraint=$Regao" | Out-Null
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar o bucket" }
    Bom "bucket criado"
}

Passo "bloqueando acesso publico..."
& aws s3api put-public-access-block --bucket $Bucket `
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui bloquear acesso publico" }
Bom "tudo privado -- leitura so por presigned URL"

Passo "ligando versionamento..."
& aws s3api put-bucket-versioning --bucket $Bucket --versioning-configuration "Status=Enabled"
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ligar o versionamento" }
Bom "versionamento ligado -- exclusao acidental tem volta"

Passo "ligando criptografia..."
$cripto = @"
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": { "SSEAlgorithm": "AES256" },
      "BucketKeyEnabled": true
    }
  ]
}
"@
$arqCripto = Join-Path $env:TEMP "hipo-cripto.json"
$cripto | Out-File -Encoding ascii $arqCripto
& aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration "file://$arqCripto"
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ligar a criptografia" }
Remove-Item $arqCripto -Force -ErrorAction SilentlyContinue
Bom "SSE-S3 ligada"

# =====================================================================
# 3. Politica na role da instancia
# =====================================================================

Titulo "3. Politica em $role"

# Sem s3:ListBucket em objeto e sem curinga de bucket: a aplicacao acha os
# anexos pelo Postgres, nunca varrendo o bucket. ListBucket entra so no
# proprio bucket, para diagnostico.
$politica = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AnexosLerEscreverApagar",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "$arnObjetos"
    },
    {
      "Sid": "AnexosListarParaDiagnostico",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "$arnBucket"
    }
  ]
}
"@

$arqPol = Join-Path $env:TEMP "hipo-politica-anexos.json"
$politica | Out-File -Encoding ascii $arqPol

Confirmar "Aplicar a politica $NomePolitica na role ${role}?"
& aws iam put-role-policy --role-name $role --policy-name $NomePolitica --policy-document "file://$arqPol"
if ($LASTEXITCODE -ne 0) { Abortar "nao consegui aplicar a politica na role" }
Remove-Item $arqPol -Force -ErrorAction SilentlyContinue
Bom "politica aplicada -- acesso so a $Bucket"

# =====================================================================
# Fim
# =====================================================================

Titulo "Bucket pronto"

Write-Host ""
Write-Host "  ATENCAO A ORDEM. Nao mexa no .env ainda." -ForegroundColor Red
Write-Host ""
Write-Host "  O pydantic-settings RECUSA chave do .env que o Settings nao" -ForegroundColor Yellow
Write-Host "  declara: 'Extra inputs are not permitted'. Com o codigo atual em" -ForegroundColor Yellow
Write-Host "  producao, escrever S3_BUCKET_ANEXOS no .env e reiniciar faz a API" -ForegroundColor Yellow
Write-Host "  NAO SUBIR. A linha vem DEPOIS do deploy, nunca antes." -ForegroundColor Yellow
Write-Host ""
Write-Host "  1) suba o codigo dos anexos (deploy normal). Ele ja sobe com o" -ForegroundColor White
Write-Host "     recurso desligado -- o campo tem default vazio, e a tela nao" -ForegroundColor White
Write-Host "     oferece o botao enquanto o bucket nao estiver configurado." -ForegroundColor White
Write-Host ""
Write-Host "  2) so entao, a linha e o restart:" -ForegroundColor White
Write-Host ""
Write-Host "     ssh -i `$HOME\Downloads\chave-hipo.pem ec2-user@63.179.88.212" -ForegroundColor Gray
Write-Host "     sudo sh -c 'echo `"S3_BUCKET_ANEXOS=$Bucket`" >> /home/hipo/app/.env'" -ForegroundColor Gray
Write-Host "     sudo systemctl restart hipo-api" -ForegroundColor Gray
Write-Host ""
Write-Host "  O restart e obrigatorio: o pydantic-settings le o .env quando o" -ForegroundColor Gray
Write-Host "  processo sobe. Editar o arquivo com a API no ar nao muda nada" -ForegroundColor Gray
Write-Host "  para quem ja esta rodando -- mesma licao do python-pptx da 009." -ForegroundColor Gray
Write-Host ""
Write-Host "  3) confira que a API voltou ANTES de sair:" -ForegroundColor White
Write-Host "     curl -s https://hipogestao.com.br/api/health" -ForegroundColor Gray
Write-Host ""
Write-Host "  Teste de fumaca da credencial, de dentro da EC2:" -ForegroundColor Gray
Write-Host "     sudo -iu hipo python3 -c `"import boto3;print(boto3.client('s3').list_objects_v2(Bucket='$Bucket').get('KeyCount'))`"" -ForegroundColor White
Write-Host "  Tem de imprimir 0. AccessDenied aqui significa que a role nao" -ForegroundColor Gray
Write-Host "  chegou no processo -- e nao que o codigo dos anexos esta errado." -ForegroundColor Gray
Write-Host ""
