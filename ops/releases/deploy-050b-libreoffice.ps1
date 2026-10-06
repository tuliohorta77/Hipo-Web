# =====================================================================
#  HIPO -- 050b: LibreOffice na EC2 (proposta em PDF)
# =====================================================================
#
#  Sem LibreOffice o PPTX da proposta funciona, mas nao ha PDF -- e o
#  e-mail de proposta (entrega 050) nao tem o que anexar ("O servidor nao
#  gera PDF (LibreOffice ausente)").
#
#  O que faz:
#    1. extrai as fontes da marca do proprio modelo (aqui, no Windows)
#    2. envia fontes + instalador para a EC2
#    3. roda infra/instalar-libreoffice.sh: descobre a versao stable mais
#       nova, baixa (~300 MB), instala em /opt, instala as fontes e faz um
#       ensaio de conversao com o modelo real
#
#  NAO tem commit nem push: e so infra no servidor. Nao reinicia a API --
#  ela procura o LibreOffice a cada pedido.
#
#  Substitui o "-InstalarLibreOffice" do deploy-009, que tinha o IP velho
#  da EC2 (63.179.88.212, hoje de outra pessoa) e a versao 25.2.5 fixa.
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-050b-libreoffice.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user"
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

$alvo = "$Usuario@$Servidor"
Set-Location $Pasta

$instalador = Join-Path $Pasta "infra\instalar-libreoffice.sh"
if (-not (Test-Path (Join-Path $Pasta "api\templates\proposta_modelo.pptx"))) {
    Abortar "rode da raiz do repositorio (nao achei api\templates\proposta_modelo.pptx)."
}
if (-not (Test-Path $instalador)) { Abortar "faltando: infra\instalar-libreoffice.sh" }
if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }

# =====================================================================
# 1. Fontes do modelo
# =====================================================================

Titulo "1. Fontes da marca (extraidas do modelo)"
$fontes = Join-Path $env:TEMP "fontes-hipo"
if (Test-Path $fontes) { Remove-Item $fontes -Recurse -Force }
Push-Location (Join-Path $Pasta "api")
try {
    $env:PYTHONPATH = (Get-Location).Path
    & python -m scripts.extrair_fontes_modelo $fontes
    if ($LASTEXITCODE -ne 0) { Abortar "a extracao das fontes falhou." }
} finally { Pop-Location }
$lista = @(Get-ChildItem $fontes -Include *.ttf, *.otf -Recurse -ErrorAction SilentlyContinue)
if ($lista.Count -eq 0) {
    Aviso "nenhuma fonte extraida -- o PDF vai sair com fonte substituta."
} else {
    Bom "$($lista.Count) fonte(s) extraida(s)"
}

# =====================================================================
# 2. Envio
# =====================================================================

Titulo "2. Enviando para a EC2"
& ssh -i $Chave -o ConnectTimeout=15 $alvo "rm -rf /tmp/fontes-hipo && mkdir -p /tmp/fontes-hipo"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH."
}
if ($lista.Count -gt 0) {
    foreach ($f in $lista) {
        & scp -i $Chave $f.FullName "${alvo}:/tmp/fontes-hipo/"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp de $($f.Name) falhou." }
    }
}
& scp -i $Chave $instalador "${alvo}:/tmp/instalar-libreoffice.sh"
if ($LASTEXITCODE -ne 0) { Abortar "o scp do instalador falhou." }
Bom "fontes e instalador em /tmp"

# =====================================================================
# 3. Instalacao + ensaio
# =====================================================================

Titulo "3. Instalando (o download leva alguns minutos)"
& ssh -t -i $Chave $alvo "bash /tmp/instalar-libreoffice.sh"
$rc = $LASTEXITCODE
& ssh -i $Chave $alvo "rm -rf /tmp/fontes-hipo /tmp/instalar-libreoffice.sh" 2>$null
if ($rc -eq 3) { Aviso "cancelado por voce -- nada instalado."; exit 3 }
if ($rc -ne 0) { Abortar "a instalacao falhou (codigo $rc). Mande a saida acima." }

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R na tela da oportunidade.
  2. Aba Proposta: as versoes passam a mostrar PDF e E-mail.
  3. Baixe um PDF e confira se o texto cabe nas caixas (fontes da marca).
  4. Aba E-mails -> Envio de proposta: o aviso do LibreOffice some e o
     anexo aparece embaixo do texto.
"@ -ForegroundColor White
