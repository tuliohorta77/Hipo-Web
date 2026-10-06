# =====================================================================
# HIPO -- deploy-009-proposta.ps1
#
# Entrega da 009: proposta comercial gerada dentro do HIPO.
#
#   1. aba Proposta da oportunidade: escopo, vidas, valores e validade;
#      cliente vem da conta, contato do executivo vem do cadastro
#   2. cada geracao vira uma VERSAO, baixavel em PPTX (e PDF onde o
#      servidor converte)
#   3. telefone no cadastro de usuario, que sai no slide de fechamento
#
# ---------------------------------------------------------------------
# ESTA ENTREGA MEXE NO SERVIDOR. Sao TRES coisas que o rsync do CI nao faz:
#
#   a) python-pptx     -- o deploy nao roda pip install
#   b) libreoffice     -- so para o PDF, e NAO existe nos repositorios da
#                         Amazon Linux 2023: ou se instala pelo tarball
#                         oficial (-InstalarLibreOffice, ~300 MB), ou a
#                         entrega vai sem PDF e a tela esconde o botao
#   c) fontes da marca -- Codec Pro e Poppins
#
# A (c) e a menos obvia e a que estraga o resultado em silencio: o PPTX
# leva as fontes embutidas e abre certo em qualquer PowerPoint, mas o
# LibreOffice NAO usa fonte embutida de pptx. Sem instalar, o PDF sai com
# texto transbordando as caixas e "INVESTIMENTO" partido ao meio -- e
# ninguem percebe ate o cliente receber. As fontes sao extraidas do
# proprio modelo (scripts/extrair_fontes_modelo.py) e copiadas para
# /usr/share/fonts/hipo.
#
# E TEM MIGRATION (008): coluna telefone em usuarios e a tabela propostas.
# Aditiva -- nao altera nem apaga nada existente -- mas a ordem manda:
#
#     1. testes locais
#     2. infra no servidor (pip, libreoffice, fontes)
#     3. migration em producao
#     4. push
#     5. CI + merge na main + deploy conferido
#     6. smoke
#
# Invertida, o codigo novo sobe pedindo tabela que nao existe.
# ---------------------------------------------------------------------
#
# ESTE ARQUIVO E ASCII PURO. Sem acento, sem e-comercial duplo, sem sinal
# de maior/menor solto -- ver o cabecalho do deploy-008 para o porque.
#
# E SEM '2>$null' EM COMANDO EXTERNO. Com $ErrorActionPreference = "Stop",
# o que um .exe escreve em stderr vira NativeCommandError e mata o script,
# mesmo quando aquele texto era a resposta esperada. Para "isto existe?",
# use um comando que devolva TEXTO em vez de levantar excecao.
#
# USO
#
#   .\deploy-009-proposta.ps1
#   .\deploy-009-proposta.ps1 -SomenteInfra      # so pip/libreoffice/fontes
#   .\deploy-009-proposta.ps1 -SomenteInfra -InstalarLibreOffice
#   .\deploy-009-proposta.ps1 -SomenteMigration  # so o banco
#   .\deploy-009-proposta.ps1 -PularTestes
#   .\deploy-009-proposta.ps1 -SmokeEmail voce@dominio.com
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularSmoke,
    [switch]$SomenteInfra,
    [switch]$SomenteMigration,
    [switch]$PularInfra,
    # A Amazon Linux 2023 nao tem LibreOffice nos repositorios. Com este
    # switch, o script instala pelo tarball oficial (~300 MB de download,
    # ~1,3 GB em disco). Sem ele, a entrega segue SEM PDF -- a tela esconde
    # o botao sozinha e o PPTX continua funcionando.
    [switch]$InstalarLibreOffice,

    [string]$Servidor   = "63.179.88.212",
    [string]$UsuarioSsh = "ec2-user",
    [string]$Chave      = "$HOME\Downloads\chave-hipo.pem",
    [string]$RamoAlvo   = "main",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$SmokeEmail = "",
    [string]$Mensagem   = "feat(crm): proposta comercial em PPTX e PDF, com versoes; telefone no cadastro de usuario"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

$MIGRACAO_LOCAL  = "api\migrations\008_propostas.sql"
$MIGRACAO_REMOTA = "/tmp/008_propostas.sql"
$SCRIPT_REMOTO   = "/tmp/aplicar-008.sh"
$FONTES_LOCAL    = "api\fontes-proposta"
$FONTES_REMOTAS  = "/tmp/fontes-hipo"

$ESPERADOS = @(
    @{ Arquivo = "api\services\proposta.py";                 Marcador = "ESCOPO_PADRAO" },
    @{ Arquivo = "api\services\proposta_render.py";          Marcador = "pptx_disponivel" },
    @{ Arquivo = "api\routers\crm_propostas.py";             Marcador = "proposta-padrao" },
    @{ Arquivo = "api\templates\proposta_modelo.pptx";       Marcador = "" },
    @{ Arquivo = "api\migrations\008_propostas.sql";         Marcador = "CREATE TABLE IF NOT EXISTS propostas" },
    @{ Arquivo = "api\scripts\conferir_modelo_proposta.py"; Marcador = "MODELO COM PROBLEMA" },
    @{ Arquivo = "api\tests\test_proposta_regras.py";        Marcador = "TestSubstituicoes" },
    @{ Arquivo = "api\tests\test_crm_propostas.py";          Marcador = "TestSnapshot" },
    @{ Arquivo = "web\src\components\crm\AbaProposta.jsx";   Marcador = "calc-investimento" },
    @{ Arquivo = "web\src\tests\AbaProposta.test.jsx";       Marcador = "hojeLocalISO" },
    @{ Arquivo = "web\src\pages\Perfil.jsx";                 Marcador = "salvarTelefone" }
)

# =====================================================================
# Utilidades
# =====================================================================

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

function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

# NAO chame de 'Ssh': o PowerShell resolve funcao antes de executavel, e o
# '& ssh' de dentro chamaria a propria funcao -- recursao infinita cujo erro
# nao menciona ssh em lugar nenhum.
function Remoto($comando) {
    & ssh.exe -i $Chave -o StrictHostKeyChecking=accept-new "$UsuarioSsh@$Servidor" $comando
}

function RunMaisRecente($ramoDoRun) {
    $bruto = & gh run list --workflow=ci-cd.yml --branch $ramoDoRun --limit 1 `
        --json databaseId,createdAt,event,status,conclusion
    if ($LASTEXITCODE -ne 0) { return $null }
    $lista = @($bruto | ConvertFrom-Json)
    if ($lista.Count -eq 0) { return $null }
    return $lista[0]
}

function EsperarRunNovo($ramoDoRun, $idAntes, $segundos = 45) {
    Passo "esperando ${segundos}s para o Actions acordar no ramo $ramoDoRun..."
    Start-Sleep -Seconds $segundos
    $atual = RunMaisRecente $ramoDoRun
    if (-not $atual) { return $null }
    $ehNovo = ([string]$atual.databaseId) -ne ([string]$idAntes)
    $idade  = (Get-Date) - [datetime]$atual.createdAt
    if ($ehNovo -or $idade.TotalMinutes -lt 3) { return $atual }
    return $null
}

function AcompanharRun($runId, $oQueEsperar) {
    Passo "acompanhando o run $runId ($oQueEsperar)..."
    & gh run watch $runId --exit-status
    if ($LASTEXITCODE -ne 0) {
        Abortar "o CI ficou vermelho no run $runId. A migration ja esta aplicada, e ela e ADITIVA -- nao atrapalha o codigo antigo que continua no ar. Corrija com calma. $REPO_URL"
    }
}

# Job pulado nao deixa run vermelho: um deploy que nunca rodou e um que
# funcionou sao iguais aos olhos do 'gh run watch'. Por isso, pelo nome.
function ExigirDeployFeito($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler os jobs do run $runId. $REPO_URL" }
    $deploy = @((($bruto | ConvertFrom-Json).jobs) | Where-Object { $_.name -like "Deploy*" })
    if ($deploy.Count -eq 0) { Abortar "o run $runId nao tem job de Deploy. $REPO_URL" }

    $conclusao = [string]$deploy[0].conclusion
    if ($conclusao -eq "success") { Bom "job de Deploy concluido com sucesso"; return }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. O ci-cd.yml so deploya em push na '$RamoAlvo'. O codigo esta no repositorio, mas NAO em producao."
    }
    Abortar "o job de Deploy terminou como '$conclusao' no run $runId. $REPO_URL"
}

# =====================================================================
# 0. Pre-voo
# =====================================================================

Titulo "0. Pre-voo"

if (-not (Test-Path "api\main.py")) {
    Abortar "rode a partir da raiz do repositorio (a pasta que tem api\ e web\)."
}
Bom "raiz do repositorio"

foreach ($item in $ESPERADOS) {
    if (-not (Test-Path $item.Arquivo)) {
        Abortar "arquivo da 009 nao encontrado: $($item.Arquivo)"
    }
    if ($item.Marcador) {
        $conteudo = Get-Content $item.Arquivo -Raw
        if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
            Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
        }
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 009 estao no disco"


# python-pptx TAMBEM na maquina local. O conftest importa main.py, que
# importa a cadeia inteira de routers -- sem a lib, a suite ABORTA no
# conftest e nenhum teste roda. Foi o que travou a primeira tentativa desta
# entrega.
#
# (No servidor o import e tardio de proposito, para faltar a lib nao
# derrubar a API inteira. Aqui, o pytest carrega tudo de qualquer jeito.)
#
# A checagem NAO usa 'python -c "import pptx"' com redirecionamento: com
# $ErrorActionPreference = "Stop", qualquer coisa que um .exe escreva em
# stderr vira NativeCommandError e MATA o script -- o traceback do
# ImportError, que era a resposta esperada, derrubava o deploy inteiro.
# find_spec devolve None em vez de levantar: nada em stderr, exit code 0.
Passo "conferindo python-pptx local..."
$temPptx = (& python -c "import importlib.util; print('sim' if importlib.util.find_spec('pptx') else 'nao')").Trim()
if ($temPptx -ne "sim") {
    Aviso "python-pptx nao esta instalado nesta maquina -- sem ele o pytest nao carrega"
    Confirmar "Instalar python-pptx==1.0.2 aqui agora?"
    Executar "pip install python-pptx" { python -m pip install "python-pptx==1.0.2" }
}
Bom "python-pptx disponivel localmente"

# O modelo e o coracao da feature: binario de 16 MB versionado, trocado
# sempre que o marketing entrega arte nova. Um marcador perdido no caminho
# gera proposta com campo em branco, e ninguem percebe ate o cliente
# receber. O conferidor mora em api/scripts -- NAO inline aqui: a primeira
# versao deste passo era uma linha de Python dentro de aspas duplas do
# PowerShell, e o "R$" precisou de escape, o que fez o Python receber "R\$"
# e reprovar um deploy que estava perfeito.
Push-Location "api"
try {
    $env:PYTHONPATH = (Get-Location).Path
    Executar "conferindo o modelo da proposta" {
        python -m scripts.conferir_modelo_proposta
    }
}
finally { Pop-Location }
Bom "o modelo preenche e os valores batem"

# schema.sql tem que espelhar a migration: e DELE que o CI cria o banco de
# teste. Migration sem schema deixa a suite verde na maquina de quem migrou
# a mao e derruba dezenas de testes no runner.
$schema = Get-Content "api\schema.sql" -Raw
if ($schema -notmatch "CREATE TABLE IF NOT EXISTS propostas") {
    Abortar "api\schema.sql nao tem a tabela propostas. O CI monta o banco de teste a partir dele."
}
if ($schema -notmatch "telefone\s+VARCHAR\(30\)") {
    Abortar "api\schema.sql nao tem usuarios.telefone."
}
Bom "schema.sql espelha a migration 008"

if (-not (Test-Path $MIGRACAO_LOCAL)) { Abortar "migration nao encontrada em $MIGRACAO_LOCAL" }

$precisaServidor = -not ($PularInfra -and -not $SomenteInfra -and -not $SomenteMigration)
if ($precisaServidor -and -not (Test-Path $Chave)) {
    Abortar "chave SSH nao encontrada em $Chave"
}

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
$ramo  = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"
$noAlvo = ($ramo -eq $RamoAlvo)
if (-not $noAlvo) {
    Aviso "push em '$ramo' NAO deploya: o deploy so roda na '$RamoAlvo'. O script oferece o merge depois do CI."
}

if ($precisaServidor) {
    Passo "testando SSH..."
    $eco = Remoto "echo vivo"
    if ($eco -ne "vivo") { Abortar "nao consegui falar com $Servidor." }
    Bom "servidor responde"
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes -or $SomenteInfra -or $SomenteMigration) {
    Titulo "1. Testes locais -- PULADOS"
}
else {
    Titulo "1. Testes locais"

    Push-Location "api"
    try {
        $env:PYTHONPATH   = (Get-Location).Path
        $env:DATABASE_URL = "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test"

        # As regras da proposta sao puras: formatacao de moeda, aritmetica do
        # investimento e o mapa de marcadores rodam sem Postgres. E o que
        # pega numero errado antes de virar slide.
        Executar "pytest -- regras puras (proposta incluida)" {
            python -m pytest -q --no-cov `
                tests\test_proposta_regras.py `
                tests\test_tarefa_regras.py `
                tests\test_oportunidade_regras.py `
                tests\test_cnpj.py `
                tests\test_texto.py `
                tests\test_dias_uteis.py
        }
        Bom "regras puras verdes"

    }
    finally { Pop-Location }

    Push-Location "web"
    try {
        Executar "vitest" { npx vitest run }
        Bom "frontend verde"
        Executar "vite build" { npx vite build }
        Bom "build verde"
    }
    finally { Pop-Location }
}

# =====================================================================
# 2. Infra no servidor
# =====================================================================

if ($PularInfra -or $SomenteMigration) {
    Titulo "2. Infra no servidor -- PULADA"
    Aviso "voce disse que python-pptx, LibreOffice e fontes ja estao la."
}
else {
    Titulo "2. Infra no servidor"

    # 2.1 Fontes, extraidas do proprio modelo.
    Executar "extraindo as fontes do modelo" {
        Push-Location "api"
        try {
            $env:PYTHONPATH = (Get-Location).Path
            python -m scripts.extrair_fontes_modelo "fontes-proposta"
        }
        finally { Pop-Location }
    }

    $fontes = @(Get-ChildItem "$FONTES_LOCAL\*" -Include *.ttf, *.otf -ErrorAction SilentlyContinue)
    if ($fontes.Count -eq 0) { Abortar "nenhuma fonte extraida -- o PDF sairia desalinhado." }
    Bom "$($fontes.Count) fonte(s) extraida(s)"

    Executar "enviando as fontes" {
        Remoto "mkdir -p $FONTES_REMOTAS"
        & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new `
            "$FONTES_LOCAL\*" "${UsuarioSsh}@${Servidor}:$FONTES_REMOTAS/"
    }

    # 2.2 Pacotes e fontes. Gerado aqui e executado la: 'sudo bash -c "..."'
    # quebra no primeiro ponto-e-virgula e o que roda nao e o que voce
    # escreveu. E sai com LF explicito -- editor do Windows salva CRLF e o
    # bash morre no primeiro \r com erro que nao ajuda.
    #
    # O LibreOffice NAO aborta o script se faltar: a Amazon Linux 2023 nao
    # tem o pacote, e PDF e o extra da entrega -- o PPTX, que e o principal,
    # nao depende dele. O .sh imprime SEM_LIBREOFFICE e quem decide o que
    # fazer e o passo seguinte, aqui em cima.
    $sh = @'
#!/bin/sh
# Aplicado por deploy-009-proposta.ps1.
set -eu

echo "--- LibreOffice ---"
if command -v soffice >/dev/null 2>&1 || [ -x /opt/libreoffice*/program/soffice ]; then
    echo "ja instalado"
elif sudo dnf install -y libreoffice-impress; then
    echo "instalado via libreoffice-impress"
elif sudo dnf install -y libreoffice; then
    echo "instalado via libreoffice"
else
    echo "SEM_LIBREOFFICE"
fi

echo "--- fontes da marca ---"
# fontconfig NAO vem instalado na Amazon Linux 2023 minima: sem ele nao ha
# fc-cache nem fc-list. Copiar as fontes ainda vale (elas ficam prontas para
# quando o LibreOffice entrar), entao a falta do fontconfig avisa e segue.
sudo mkdir -p /usr/share/fonts/hipo
sudo cp /tmp/fontes-hipo/* /usr/share/fonts/hipo/
echo "fontes copiadas para /usr/share/fonts/hipo"

if ! command -v fc-cache >/dev/null 2>&1; then
    echo "fontconfig ausente -- instalando"
    sudo dnf install -y fontconfig || echo "AVISO: nao consegui instalar fontconfig"
fi

if command -v fc-cache >/dev/null 2>&1; then
    sudo fc-cache -f
    echo "faces Codec Pro/Poppins: $(fc-list | grep -ci -e 'codec pro' -e poppins || true)"
else
    echo "AVISO: sem fc-cache. As fontes estao no disco, mas so serao vistas"
    echo "       depois que o fontconfig for instalado (ele entra junto com"
    echo "       o LibreOffice, se voce usar -InstalarLibreOffice)."
fi

echo "--- python-pptx ---"
# O app roda como usuario hipo. O deploy do CI faz rsync e reinicia o
# servico, NAO roda pip install: sem esta linha o import quebra em runtime.
sudo -iu hipo python3 -m pip install --user "python-pptx==1.0.2"
sudo -iu hipo python3 -c "import pptx; print('python-pptx', pptx.__version__)"
'@
    $sh = $sh -replace "`r`n", "`n"
    $arquivoSh = Join-Path $env:TEMP "instalar-009.sh"
    [IO.File]::WriteAllText($arquivoSh, $sh)

    Executar "enviando o script de infra" {
        & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new $arquivoSh "${UsuarioSsh}@${Servidor}:/tmp/instalar-009.sh"
    }

    Passo "instalando no servidor..."
    $saidaInfra = Remoto "sh /tmp/instalar-009.sh"
    $saidaInfra | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) { Abortar "a instalacao no servidor falhou." }
    Bom "fontes e python-pptx no lugar"

    $semLibre = ($saidaInfra -join "`n") -match "SEM_LIBREOFFICE"

    if ($semLibre) {
        Write-Host ""
        Aviso "a Amazon Linux 2023 nao tem LibreOffice nos repositorios."
        Write-Host "     Sem ele: o PPTX funciona normalmente e a tela esconde o botao" -ForegroundColor Gray
        Write-Host "     de PDF sozinha. Com ele: PDF pronto para anexar em e-mail." -ForegroundColor Gray
        Write-Host "     A instalacao e pelo tarball oficial: ~300 MB de download e" -ForegroundColor Gray
        Write-Host "     ~1,3 GB em disco na EC2." -ForegroundColor Gray

        if (-not $InstalarLibreOffice) {
            Aviso "seguindo SEM PDF. Para instalar depois: .\deploy-009-proposta.ps1 -SomenteInfra -InstalarLibreOffice"
        }
        else {
            Confirmar "Baixar e instalar o LibreOffice agora?"

            $loSh = @'
#!/bin/sh
# LibreOffice pelo tarball oficial -- a Amazon Linux 2023 nao tem o pacote.
set -eu

LIVRE=$(df -Pk /opt | awk 'NR==2 {print $4}')
if [ "$LIVRE" -lt 2000000 ]; then
    echo "ERRO: menos de 2 GB livres em /opt ($LIVRE KB). Libere espaco antes."
    exit 1
fi

VER=25.2.5
URL="https://download.documentfoundation.org/libreoffice/stable/$VER/rpm/x86_64/LibreOffice_${VER}_Linux_x86-64_rpm.tar.gz"

cd /tmp
rm -rf lo-instalacao
mkdir lo-instalacao
cd lo-instalacao

echo "baixando $VER ..."
curl -fL --retry 3 -o lo.tar.gz "$URL"
tar xzf lo.tar.gz
cd */RPMS

echo "instalando ..."
sudo dnf install -y ./*.rpm

cd /tmp
rm -rf lo-instalacao

BIN=$(ls -d /opt/libreoffice*/program/soffice 2>/dev/null | head -1)
[ -n "$BIN" ] || { echo "ERRO: instalou mas nao achei o binario"; exit 1; }
echo "binario: $BIN"
"$BIN" --version
'@
            $loSh = $loSh -replace "`r`n", "`n"
            $arquivoLo = Join-Path $env:TEMP "libreoffice-009.sh"
            [IO.File]::WriteAllText($arquivoLo, $loSh)

            Executar "enviando o instalador do LibreOffice" {
                & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new $arquivoLo "${UsuarioSsh}@${Servidor}:/tmp/libreoffice-009.sh"
            }
            # Sem Executar: o download e longo e a saida e verbosa; o teste
            # de sucesso e o binario existir, conferido logo abaixo.
            Remoto "sh /tmp/libreoffice-009.sh"
            if ($LASTEXITCODE -ne 0) {
                Abortar "a instalacao do LibreOffice falhou. A entrega funciona sem ele: rode de novo sem -InstalarLibreOffice."
            }
            Bom "LibreOffice instalado"
            Remoto "rm -f /tmp/libreoffice-009.sh"
        }
    }
    else {
        Bom "LibreOffice disponivel -- o PDF vai funcionar"
    }

    Remoto "rm -rf $FONTES_REMOTAS /tmp/instalar-009.sh"
    Remove-Item "$FONTES_LOCAL" -Recurse -Force -ErrorAction SilentlyContinue
}

if ($SomenteInfra) {
    Titulo "Fim -- so a infra, como voce pediu"
    exit 0
}

# =====================================================================
# 3. Migration em producao
# =====================================================================

Titulo "3. Migration 008 em producao"

Executar "enviando a migration" {
    & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new $MIGRACAO_LOCAL "${UsuarioSsh}@${Servidor}:$MIGRACAO_REMOTA"
}

$sqlSh = @'
#!/bin/sh
# Aplicado por deploy-009-proposta.ps1.
#
# RODA COMO ROOT (sudo), nao como o usuario hipo.
#
# O .env do app fica em /home/hipo/app, mas o deploy do CI chega por rsync
# como ec2-user -- e o arquivo acaba com dono ec2-user e modo restrito. O
# proprio usuario hipo entao NAO consegue ler o .env, e o 'sudo -iu hipo'
# morria com "Permission denied" na linha do source. Root le em qualquer
# caso, e a migration nao precisa da identidade do app: ela fala com o RDS
# pela rede, com a credencial que esta no arquivo.
set -eu

MIG=/tmp/008_propostas.sql
ENVFILE=/home/hipo/app/.env

[ -f "$MIG" ]     || { echo "ERRO: migration nao encontrada"; exit 1; }
[ -f "$ENVFILE" ] || { echo "ERRO: $ENVFILE nao encontrado"; exit 1; }
[ -r "$ENVFILE" ] || { echo "ERRO: sem permissao de leitura em $ENVFILE (rode com sudo)"; exit 1; }

set -a
. "$ENVFILE"
set +a

[ -n "${DATABASE_URL:-}" ] || { echo "ERRO: DATABASE_URL vazia"; exit 1; }

# Mascarar e conferir o host ANTES de rodar DDL. O seed nao tem safeguard
# como o conftest tem, e esta migration tambem nao.
echo "ALVO: $(echo "$DATABASE_URL" | sed 's|:[^:@]*@|:****@|')"

command -v psql >/dev/null 2>&1 || {
    echo "ERRO: psql nao instalado. Saia do usuario hipo e rode:"
    echo "      sudo dnf install -y postgresql15"
    exit 1
}

ANTES=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM oportunidades")
echo "oportunidades antes: $ANTES"

echo "--- aplicando 008 ---"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$MIG"
echo "--- aplicada ---"

# CONFERENCIA POR RESULTADO, nao pelo eco: colagem grande no SSH trunca na
# tela, e o que apareceu nao prova o que o banco tem.
TAB=$(psql    "$DATABASE_URL" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_name='propostas'")
COL=$(psql    "$DATABASE_URL" -At -c "SELECT count(*) FROM information_schema.columns WHERE table_name='usuarios' AND column_name='telefone'")
CHECKS=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM pg_constraint WHERE conrelid='propostas'::regclass AND conname LIKE 'ck_proposta%'")
IDX=$(psql    "$DATABASE_URL" -At -c "SELECT count(*) FROM pg_indexes WHERE tablename='propostas'")
DEPOIS=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM oportunidades")

echo "tabela propostas: $TAB | usuarios.telefone: $COL | checks: $CHECKS | indices: $IDX"
echo "oportunidades depois: $DEPOIS"

[ "$TAB" = "1" ]      || { echo "ERRO: tabela propostas nao existe"; exit 1; }
[ "$COL" = "1" ]      || { echo "ERRO: usuarios.telefone nao existe"; exit 1; }
[ "$CHECKS" -ge 5 ]   || { echo "ERRO: faltam CHECKs em propostas"; exit 1; }
[ "$ANTES" = "$DEPOIS" ] || { echo "ERRO: a contagem de oportunidades mudou"; exit 1; }

echo "OK: 008 aplicada e conferida"
'@
$sqlSh = $sqlSh -replace "`r`n", "`n"
$arquivoSql = Join-Path $env:TEMP "aplicar-008.sh"
[IO.File]::WriteAllText($arquivoSql, $sqlSh)

Executar "enviando o script da migration" {
    & scp.exe -i $Chave -o StrictHostKeyChecking=accept-new $arquivoSql "${UsuarioSsh}@${Servidor}:$SCRIPT_REMOTO"
}

Write-Host ""
Write-Host "  A 008 e ADITIVA: cria a tabela propostas e a coluna telefone." -ForegroundColor White
Write-Host "  Nao altera nem apaga nada existente." -ForegroundColor Gray
Confirmar "Aplicar a migration no banco de PRODUCAO?"

Executar "aplicando" { Remoto "sudo sh $SCRIPT_REMOTO" }
Bom "008 aplicada e conferida no banco de producao"
Remoto "rm -f $MIGRACAO_REMOTA $SCRIPT_REMOTO"

if ($SomenteMigration) {
    Titulo "Fim -- so a migration, como voce pediu"
    Write-Host "  Rode de novo sem -SomenteMigration para subir o codigo." -ForegroundColor Gray
    exit 0
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push do ramo"

$sujos = & git status --porcelain
if ($sujos) {
    Write-Host ""
    & git status --short
    Confirmar "Commitar e empurrar estes arquivos?"
    Executar "git add"    { git add -A }
    Executar "git commit" { git commit -m $Mensagem }
    Bom "commit criado"
}
else {
    Aviso "arvore limpa -- nada novo para commitar."
}

$aFrente = "0"
try   { $aFrente = (& git rev-list --count "origin/$ramo..$ramo").Trim() }
catch { $aFrente = "?" }

Executar "git push" { git push origin $ramo }
$empurrouAlgo = ($aFrente -ne "0")
Bom "codigo no repositorio, no ramo $ramo"

# =====================================================================
# 5. CI, merge e deploy
# =====================================================================

Titulo "5. CI e deploy"

if (-not $temGh) {
    Aviso "gh nao instalado -- abra o PR, mergeie e confira o job Deploy em $REPO_URL"
}
elseif ($noAlvo) {
    if ($empurrouAlgo) {
        $runMain = RunMaisRecente $RamoAlvo
        if ($runMain) {
            AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
            ExigirDeployFeito ([string]$runMain.databaseId)
        }
    }
}
else {
    if ($empurrouAlgo) {
        $antes = RunMaisRecente $ramo
        $idAntes = ""
        if ($antes) { $idAntes = [string]$antes.databaseId }
        $atual = EsperarRunNovo $ramo $idAntes
        if ($atual) {
            AcompanharRun ([string]$atual.databaseId) "Backend Tests + Frontend Tests"
            Bom "testes verdes no ramo"
        }
        else {
            Aviso "nenhum run novo no ramo -- pode ter rodado no evento de pull_request. $REPO_URL"
        }
    }

    $numeroPr = ""
    $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number
    if ($LASTEXITCODE -eq 0) {
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -gt 0) { $numeroPr = [string]$prs[0].number }
    }

    if (-not $numeroPr) {
        Passo "nenhum PR aberto -- criando"
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 009 -- proposta comercial. Migration 008 ja aplicada em producao pelo deploy-009-proposta.ps1."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se a mensagem foi 'No commits between $RamoAlvo and $ramo', o merge ja aconteceu e falta so o deploy: use o .\deploy-007-retomar.ps1."
        }
        $prs = @((& gh pr list --head $ramo --base $RamoAlvo --state open --json number) | ConvertFrom-Json)
        if ($prs.Count -eq 0) { Abortar "PR criado mas nao encontrado. $REPO_URL" }
        $numeroPr = [string]$prs[0].number
    }
    Bom "PR #$numeroPr"

    Confirmar "Mergear o PR #$numeroPr em $RamoAlvo agora?"

    $antesMain = RunMaisRecente $RamoAlvo
    $idAntesMain = ""
    if ($antesMain) { $idAntesMain = [string]$antesMain.databaseId }

    Executar "gh pr merge" { gh pr merge $numeroPr --merge }
    Bom "PR #$numeroPr mergeado"

    $runMain = EsperarRunNovo $RamoAlvo $idAntesMain 60
    if (-not $runMain) {
        Abortar "merge feito mas nao vi run novo na $RamoAlvo. Confira em $REPO_URL antes de considerar entregue."
    }
    AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
    ExigirDeployFeito ([string]$runMain.databaseId)
}

# =====================================================================
# 6. Smoke test
# =====================================================================

Titulo "6. Smoke test"

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$falhou = $false

try {
    $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
    if ($health.status -eq "ok") { Bom "API viva -- versao $($health.versao)" }
    else { Aviso "API respondeu estranho"; $falhou = $true }
}
catch { Aviso "API nao respondeu: $($_.Exception.Message)"; $falhou = $true }

try {
    $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
    if ($front.StatusCode -eq 200) { Bom "front servido (HTTP 200)" }
    else { Aviso "front devolveu HTTP $($front.StatusCode)"; $falhou = $true }
}
catch { Aviso "front nao respondeu: $($_.Exception.Message)"; $falhou = $true }

# Smoke autenticado: LE os padroes da proposta numa oportunidade real. Nao
# gera proposta de proposito -- criaria uma versao de teste na base do
# cliente, que alguem teria que explicar depois.
if ($PularSmoke) {
    Aviso "smoke autenticado pulado"
}
elseif (-not $SmokeEmail) {
    Aviso "smoke autenticado nao rodou. Rode com -SmokeEmail seu-email@dominio.com"
}
elseif ($SmokeEmail -like "*@empresa.com" -or $SmokeEmail -like "seu-email*" -or $SmokeEmail -like "voce@*") {
    Aviso "'$SmokeEmail' e placeholder de exemplo. Use seu e-mail de verdade."
}
else {
    $segura = Read-Host "  Senha de $SmokeEmail (nao aparece na tela)" -AsSecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    $senha  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

    try {
        $login = Invoke-RestMethod -Uri "$UrlPublica/api/auth/login" -Method Post `
            -Body @{ username = $SmokeEmail; password = $senha } `
            -ContentType "application/x-www-form-urlencoded" -TimeoutSec 20
        $cab = @{ Authorization = "Bearer $($login.access_token)" }
        Bom "login em producao"

        $eu = Invoke-RestMethod -Uri "$UrlPublica/api/auth/me" -Headers $cab -TimeoutSec 20
        if ($eu.PSObject.Properties.Name -contains "telefone") {
            Bom "o /me ja traz telefone: '$($eu.telefone)'"
        }
        else {
            Aviso "o /me nao trouxe o campo telefone -- o deploy pegou o codigo novo?"
            $falhou = $true
        }

        $lista = Invoke-RestMethod -Headers $cab -TimeoutSec 30 `
            -Uri "$UrlPublica/api/crm/oportunidades?limit=1"
        if ($lista.total -eq 0) {
            Aviso "nao ha oportunidade em producao para exercitar a proposta"
        }
        else {
            $opp = $lista.itens[0]
            $padrao = Invoke-RestMethod -Headers $cab -TimeoutSec 30 `
                -Uri "$UrlPublica/api/crm/oportunidades/$($opp.id)/proposta-padrao"
            Bom "proposta-padrao respondeu para $($opp.numero) -- cliente '$($padrao.cliente_razao_social)', $(@($padrao.escopo_padrao).Count) itens de escopo"

            if ($padrao.pdf_disponivel) { Bom "o servidor converte para PDF" }
            else {
                Aviso "pdf_disponivel = false: o LibreOffice nao esta acessivel ao processo do app. O PPTX funciona; o PDF nao."
                $falhou = $true
            }
        }
    }
    catch {
        Aviso "smoke autenticado falhou: $($_.Exception.Message)"
        $falhou = $true
    }
    finally { $senha = $null }
}

if ($falhou) {
    Abortar "o deploy subiu mas o smoke nao passou. Olhe o servico: ssh e 'sudo systemctl status hipo'."
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Entregue"

Write-Host ""
Write-Host "  A 009 esta em producao." -ForegroundColor Green
Write-Host ""
Write-Host "  PRIMEIRO PASSO, e vale para cada vendedor:" -ForegroundColor Yellow
Write-Host "    Perfil -> Contato -> preencha o telefone." -ForegroundColor White
Write-Host "    Sem ele, o slide de fechamento sai com um travessao." -ForegroundColor Gray
Write-Host ""
Write-Host "  Depois, numa oportunidade -> aba Proposta:" -ForegroundColor Gray
Write-Host "    - o escopo ja vem com os 6 itens do modelo; ajuste o que mudar" -ForegroundColor Gray
Write-Host "    - vidas x valor por vida calcula a mensalidade na hora" -ForegroundColor Gray
Write-Host "    - a validade nasce com 10 dias e e editavel" -ForegroundColor Gray
Write-Host "    - Gerar cria a v1 e baixa o PPTX" -ForegroundColor Gray
Write-Host "    - gere de novo com outro valor: vira v2, e a v1 continua la" -ForegroundColor Gray
Write-Host ""
Write-Host "  ABRA O PPTX E O PDF ANTES DE MANDAR PARA UM CLIENTE:" -ForegroundColor Yellow
Write-Host "    - slide 5: escopo, QTDE. VIDAS e o quadro de investimento" -ForegroundColor Gray
Write-Host "    - slide 6: cliente, seu nome, e-mail, telefone, data e validade" -ForegroundColor Gray
Write-Host "    O PPTX e fiel sempre (as fontes vao embutidas). O PDF depende" -ForegroundColor Gray
Write-Host "    das fontes que este script instalou no servidor." -ForegroundColor Gray
Write-Host ""
