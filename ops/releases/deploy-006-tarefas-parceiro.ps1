# =====================================================================
# HIPO -- deploy-006-tarefas-parceiro.ps1
#
# Entrega da 006: tarefa presa ao parceiro, farol semanal e mini-funil.
#
# ORDEM OBRIGATORIA, e o script impoe ela:
#
#     1. testes locais
#     2. migration em producao
#     3. push
#     4. CI
#     5. smoke test de verdade
#
# Invertida, o codigo novo sobe pedindo coluna que nao existe. O deploy do
# CI faz rsync e reinicia o servico; DDL e passo manual, sempre.
#
# Nenhuma etapa continua se a anterior falhar. O push so acontece depois de
# o banco de producao confirmar, POR CONSULTA, que a estrutura nova existe.
#
# ---------------------------------------------------------------------
# ESTE ARQUIVO E ASCII PURO, DE PROPOSITO.
#
# O PowerShell 5.1 le .ps1 sem BOM como ANSI. Um unico caractere acentuado
# -- mesmo dentro de comentario -- desbalanceia string e derruba o parser
# do arquivo inteiro. Por isso nao ha acento, cedilha nem travessao aqui.
# Nao "conserte" a grafia.
#
# Tambem nao ha encadeamento com e-comercial duplo (nao existe no 5.1, e
# como e erro de parse NADA do bloco roda) nem sinais de maior/menor soltos
# (sao operadores de redirecionamento reservados). Grepar por eles neste
# arquivo tem que devolver zero linhas.
# ---------------------------------------------------------------------
#
# USO
#
#   .\deploy-006-tarefas-parceiro.ps1
#   .\deploy-006-tarefas-parceiro.ps1 -PularTestes      # ja rodei os testes
#   .\deploy-006-tarefas-parceiro.ps1 -SomenteMigration # so o banco
#   .\deploy-006-tarefas-parceiro.ps1 -SomentePush      # migration ja aplicada
#
# A migration e idempotente: rodar de novo nao quebra nada.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$SomenteMigration,
    [switch]$SomentePush,

    [string]$Servidor  = "63.179.88.212",
    [string]$UsuarioSsh = "ec2-user",
    [string]$Chave     = "$HOME\Downloads\chave-hipo.pem",
    [string]$UrlPublica = "https://hipogestao.com.br",
    [string]$Mensagem  = "feat(crm): tarefas de parceiro, farol semanal, mini-funil e drilldown unificado"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$MIGRACAO_LOCAL  = "api\migrations\006_tarefas_parceiro.sql"

# Codigo morto da revisao: o TarefasDoParceiro virou a AbaTarefas
# compartilhada com a oportunidade. O build passa com eles no disco (ninguem
# os importa), mas o vitest roda o teste de um componente que nao existe mais
# no produto -- e teste verde de codigo morto e pior que teste vermelho.
$MORTOS = @(
    "web\src\components\crm\TarefasDoParceiro.jsx",
    "web\src\tests\TarefasDoParceiro.test.jsx"
)
$MIGRACAO_REMOTA = "/tmp/006_tarefas_parceiro.sql"
$SCRIPT_REMOTO   = "/tmp/aplicar-006.sh"

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

# Roda um comando externo e aborta se o codigo de saida nao for zero.
# Existe porque $ErrorActionPreference NAO pega falha de .exe -- so de
# cmdlet. Sem isto, um pytest vermelho passaria batido e o script seguiria
# alegremente para a migration.
function Executar($descricao, $bloco) {
    Passo $descricao
    & $bloco
    if ($LASTEXITCODE -ne 0) {
        Abortar "$descricao falhou (codigo $LASTEXITCODE)."
    }
}

function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

# NAO chame esta funcao de 'Ssh'.
#
# O PowerShell resolve nome nesta ordem: alias, FUNCAO, cmdlet, executavel.
# Uma funcao chamada Ssh vence o ssh.exe -- e como nome de comando nao
# diferencia maiuscula de minuscula, o '& ssh' de dentro dela chamaria ela
# mesma. Recursao infinita, e o erro que aparece ('estouro de capacidade da
# profundidade da chamada') nao menciona ssh em lugar nenhum.
#
# Por isso duas defesas: o nome nao colide com comando nenhum, e a chamada
# e explicita em ssh.exe / scp.exe.
function Remoto($comando) {
    & ssh.exe -i $Chave -o StrictHostKeyChecking=accept-new "$UsuarioSsh@$Servidor" $comando
}

# =====================================================================
# 0. Pre-voo
# =====================================================================

Titulo "0. Pre-voo"

if (-not (Test-Path "api\main.py")) {
    Abortar "rode a partir da raiz do repositorio (a pasta que tem api\ e web\)."
}
Bom "raiz do repositorio"

if (-not (Test-Path $MIGRACAO_LOCAL)) {
    Abortar "migration nao encontrada em $MIGRACAO_LOCAL"
}
Bom "migration encontrada"

if (-not (Test-Path $Chave)) {
    Abortar "chave SSH nao encontrada em $Chave"
}
Bom "chave SSH encontrada"

# schema.sql tem que espelhar a migration. E DELE que o CI cria o banco de
# teste -- migration nova sem atualizar o schema.sql deixa a suite verde na
# maquina de quem migrou a mao e derruba dezenas de testes no runner. Ja
# aconteceu: 45 de uma vez, com a fase 'suspect'.
$schema = Get-Content "api\schema.sql" -Raw
if ($schema -notmatch "ck_tarefa_alvo") {
    Abortar "api\schema.sql nao tem ck_tarefa_alvo. O CI monta o banco de teste a partir dele -- sem isso a suite quebra no runner."
}
if ($schema -notmatch "idx_tarefas_conta_concluidas") {
    Abortar "api\schema.sql nao tem os indices da 006."
}
Bom "schema.sql espelha a migration"

$apagados = 0
foreach ($morto in $MORTOS) {
    if (Test-Path $morto) {
        Remove-Item $morto -Force
        $apagados = $apagados + 1
        Passo "removido (codigo morto): $morto"
    }
}
if ($apagados -gt 0) {
    Bom "$apagados arquivo(s) de codigo morto removido(s)"
}
else {
    Bom "nenhum codigo morto sobrando"
}

$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"

$sujos = & git status --porcelain
if (-not $sujos) {
    Aviso "nao ha nada para commitar. Se o codigo ja subiu, use -SomenteMigration."
}

if (-not $SomentePush) {
    Passo "testando SSH..."
    $eco = Remoto "echo vivo"
    if ($eco -ne "vivo") { Abortar "nao consegui falar com $Servidor." }
    Bom "servidor responde"
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($SomenteMigration -or $SomentePush -or $PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "voce escolheu pular. A suite completa de backend ainda vai rodar no CI."
}
else {
    Titulo "1. Testes locais"

    # Pytest local no Windows sem Postgres falha nos testes de banco. Os de
    # logica pura (sem a fixture db_conn) rodam aqui; o resto valida no CI.
    #
    # A DATABASE_URL e forcada para localhost ANTES de chamar o pytest: se
    # o ambiente estiver com a de producao, o safeguard do conftest aborta a
    # sessao inteira -- que e ele funcionando, mas nao e o que queremos aqui.
    Push-Location "api"
    try {
        $env:PYTHONPATH  = (Get-Location).Path
        $env:DATABASE_URL = "postgresql://hipo_test:hipo_test@localhost:5432/hipo_test"

        Executar "pytest -- regras puras" {
            python -m pytest -q --no-cov `
                tests\test_tarefa_regras.py `
                tests\test_parceiro_regras.py `
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
        Executar "vitest"     { npx vitest run }
        Bom "frontend verde"
        Executar "vite build" { npx vite build }
        Bom "build verde"
    }
    finally { Pop-Location }
}

# =====================================================================
# 2. Migration em producao
# =====================================================================

if ($SomentePush) {
    Titulo "2. Migration -- PULADA"
    Aviso "voce disse que a 006 ja esta aplicada em producao."
}
else {
    Titulo "2. Migration em producao"

    # O .sh e gerado aqui e executado la. NAO se manda 'sudo -iu hipo bash
    # -c "..."': o comando quebra no primeiro ';' e o que roda nao e o que
    # voce escreveu. Gravar em arquivo e rodar o arquivo e a regra.
    #
    # E ele sai com LF explicito. Editor do Windows salva CRLF, e o bash
    # quebra no primeiro \r com um erro que nao parece ter nada a ver.

    $sh = @'
#!/bin/sh
# Aplicado por deploy-006-tarefas-parceiro.ps1. Roda como usuario hipo.
set -eu

MIG=/tmp/006_tarefas_parceiro.sql
ENVFILE=/home/hipo/app/.env

if [ ! -f "$MIG" ]; then
    echo "ERRO: migration nao encontrada em $MIG"
    exit 1
fi
if [ ! -f "$ENVFILE" ]; then
    echo "ERRO: $ENVFILE nao encontrado"
    exit 1
fi

set -a
. "$ENVFILE"
set +a

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: DATABASE_URL vazia no .env"
    exit 1
fi

# Sempre mascarar e conferir o host antes de rodar DDL. O seed nao tem
# safeguard como o conftest tem, e nem esta migration tem.
echo "ALVO: $(echo "$DATABASE_URL" | sed 's|:[^:@]*@|:****@|')"

if ! command -v psql >/dev/null 2>&1; then
    echo "ERRO: psql nao instalado. Saia do usuario hipo e rode:"
    echo "      sudo dnf install -y postgresql15"
    exit 1
fi

ANTES=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM tarefas")
echo "tarefas antes: $ANTES"

echo "--- aplicando 006 ---"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$MIG"
echo "--- aplicada ---"

# CONFERENCIA POR RESULTADO, nao pelo eco. Colagem grande no SSH trunca
# visualmente: o que apareceu na tela nao prova o que o banco tem.
DEPOIS=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM tarefas")
CHECK=$(psql  "$DATABASE_URL" -At -c "SELECT count(*) FROM pg_constraint WHERE conrelid = 'tarefas'::regclass AND conname = 'ck_tarefa_alvo'")
COLUNA=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM information_schema.columns WHERE table_name = 'tarefas' AND column_name = 'conta_id'")
NULAVEL=$(psql "$DATABASE_URL" -At -c "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'tarefas' AND column_name = 'oportunidade_id'")
INDICES=$(psql "$DATABASE_URL" -At -c "SELECT count(*) FROM pg_indexes WHERE tablename = 'tarefas' AND indexname IN ('idx_tarefas_conta','idx_tarefas_conta_concluidas')")
FORA=$(psql   "$DATABASE_URL" -At -c "SELECT count(*) FROM tarefas WHERE num_nonnulls(oportunidade_id, conta_id) <> 1")

echo "tarefas depois: $DEPOIS"
echo "ck_tarefa_alvo: $CHECK (esperado 1)"
echo "coluna conta_id: $COLUNA (esperado 1)"
echo "oportunidade_id aceita nulo: $NULAVEL (esperado YES)"
echo "indices novos: $INDICES (esperado 2)"
echo "tarefas fora do CHECK: $FORA (esperado 0)"

# Afrouxar restricao nao apaga linha. Se a contagem mudou, alguma coisa
# muito errada aconteceu e o push NAO pode seguir.
if [ "$ANTES" != "$DEPOIS" ]; then
    echo "ERRO: a contagem de tarefas mudou de $ANTES para $DEPOIS"
    exit 1
fi
if [ "$CHECK" != "1" ];    then echo "ERRO: ck_tarefa_alvo ausente";               exit 1; fi
if [ "$COLUNA" != "1" ];   then echo "ERRO: coluna conta_id ausente";              exit 1; fi
if [ "$NULAVEL" != "YES" ];then echo "ERRO: oportunidade_id continua NOT NULL";    exit 1; fi
if [ "$INDICES" != "2" ];  then echo "ERRO: indices da 006 ausentes";              exit 1; fi
if [ "$FORA" != "0" ];     then echo "ERRO: ha tarefa sem alvo ou com dois alvos"; exit 1; fi

echo "VERIFICACAO_OK"
'@

    $shLocal = Join-Path $env:TEMP "aplicar-006.sh"
    $semBom  = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($shLocal, ($sh -replace "`r`n", "`n"), $semBom)
    Bom "script remoto gerado com LF em $shLocal"

    Executar "enviando migration" {
        scp.exe -i $Chave -o StrictHostKeyChecking=accept-new `
            $MIGRACAO_LOCAL "${UsuarioSsh}@${Servidor}:$MIGRACAO_REMOTA"
    }
    Executar "enviando script" {
        scp.exe -i $Chave -o StrictHostKeyChecking=accept-new `
            $shLocal "${UsuarioSsh}@${Servidor}:$SCRIPT_REMOTO"
    }

    # O app e do usuario hipo, mas o arquivo chega como ec2-user. Sem o
    # chmod, o hipo nao consegue ler nem a migration nem o script.
    Remoto "chmod 644 $MIGRACAO_REMOTA $SCRIPT_REMOTO"
    Bom "arquivos no servidor e legiveis pelo hipo"

    Write-Host ""
    Write-Host "  A proxima etapa roda DDL no banco de PRODUCAO." -ForegroundColor Yellow
    Write-Host "  A 006 e aditiva e idempotente: nenhum DROP, nenhum dado apagado." -ForegroundColor Gray
    Confirmar "Aplicar a 006 em producao?"

    Passo "aplicando..."
    $saida = Remoto "sudo -iu hipo bash $SCRIPT_REMOTO"
    $saida | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }

    if ($LASTEXITCODE -ne 0) {
        Abortar "a migration falhou. NADA foi enviado para o repositorio."
    }
    if (($saida -join "`n") -notmatch "VERIFICACAO_OK") {
        Abortar "a migration nao confirmou a verificacao. NADA foi enviado para o repositorio."
    }

    Bom "006 aplicada e conferida no banco de producao"
    Remoto "rm -f $MIGRACAO_REMOTA $SCRIPT_REMOTO"
}

if ($SomenteMigration) {
    Titulo "Fim -- so a migration, como voce pediu"
    Write-Host "  Rode de novo com -SomentePush quando quiser subir o codigo." -ForegroundColor Gray
    exit 0
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

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
    Aviso "arvore limpa -- nada novo para commitar, seguindo para o push."
}

Executar "git push" { git push origin $ramo }
Bom "codigo no repositorio"

# =====================================================================
# 4. CI
# =====================================================================

Titulo "4. CI"

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
if (-not $temGh) {
    Aviso "gh nao instalado -- acompanhe em https://github.com/tuliohorta77/Hipo-Web/actions"
}
else {
    # Devolve o id do run mais recente, ou string vazia. O @() em volta e
    # necessario: no PowerShell 5.1 um ConvertFrom-Json de array com UM
    # elemento devolve o objeto solto, e ai [0] indexa o objeto em vez da
    # lista. Com dois runs o codigo funcionaria e com um so quebraria --
    # exatamente o caso mais comum.
    function RunMaisRecente {
        $bruto = & gh run list --workflow=ci-cd.yml --limit 1 --json databaseId,createdAt
        if ($LASTEXITCODE -ne 0) { return $null }
        $lista = @($bruto | ConvertFrom-Json)
        if ($lista.Count -eq 0) { return $null }
        return $lista[0]
    }

    $antes = RunMaisRecente
    $idAntes = ""
    if ($antes) { $idAntes = [string]$antes.databaseId }

    # O gatilho 'push' do Actions as vezes adormece. A saida e o
    # workflow_dispatch -- MAS nunca junto com o push: dois runs simultaneos
    # colidem no deploy, e o concurrency cancela um deles no meio.
    # Por isso: espera, olha, e SO dispara se nao nasceu run nenhum.
    Passo "esperando 45s para ver se o push acordou o workflow..."
    Start-Sleep -Seconds 45

    $atual = RunMaisRecente
    $nasceu = $false
    if ($atual) {
        $ehNovo = ([string]$atual.databaseId) -ne $idAntes
        $idade  = (Get-Date) - [datetime]$atual.createdAt
        # Novo id OU criado agora ha pouco. A segunda condicao cobre o caso
        # de nao existir run anterior nenhum no repositorio.
        if ($ehNovo -or $idade.TotalMinutes -lt 3) { $nasceu = $true }
    }

    if (-not $nasceu) {
        Aviso "o gatilho push parece ter adormecido -- disparando manualmente"
        Executar "gh workflow run" { gh workflow run ci-cd.yml --ref $ramo }
        Start-Sleep -Seconds 15
        $atual = RunMaisRecente
    }
    else {
        Bom "run criado pelo push"
    }

    if (-not $atual) {
        Aviso "nao consegui identificar o run -- acompanhe em https://github.com/tuliohorta77/Hipo-Web/actions"
    }
    else {
        # Watch do run ESPECIFICO, nunca 'gh run watch' pelado: sem o id ele
        # abre um menu para escolher quando ha mais de um run em andamento,
        # e num script isso trava esperando tecla que ninguem vai apertar.
        $runId = [string]$atual.databaseId
        Passo "acompanhando o run $runId (os 3 jobs precisam ficar verdes)..."
        & gh run watch $runId --exit-status
        if ($LASTEXITCODE -ne 0) {
            Abortar "o CI ficou vermelho no run $runId. A migration ja esta aplicada, e ela e aditiva -- nao atrapalha o codigo antigo que continua no ar. Da para corrigir e empurrar de novo com calma."
        }
        Bom "Backend Tests + Frontend Tests + Deploy verdes"
    }
}

# =====================================================================
# 5. Smoke test de verdade
# =====================================================================

Titulo "5. Smoke test"

# O passo "Verificar deploy" do CI roda
#     curl -sf http://localhost/health || echo 'Frontend OK'
# e depois do Certbot o localhost cai no bloco default do nginx e devolve
# 404 -- que o '||' engole. Aquele passo passa SEMPRE, inclusive com o
# front quebrado. Este aqui bate na URL publica e falha alto.

# O PowerShell 5.1 ainda negocia TLS 1.0 por padrao, e o nginx com
# certificado Let's Encrypt so aceita 1.2 para cima. Sem esta linha o smoke
# test morre com "Could not create SSL/TLS secure channel" -- erro que
# parece problema do servidor e nao e. Vale so para este processo.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$falhou = $false

try {
    $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
    if ($health.status -eq "ok") { Bom "API viva -- versao $($health.versao)" }
    else { Aviso "API respondeu algo estranho: $($health | ConvertTo-Json -Compress)"; $falhou = $true }
}
catch {
    Aviso "API nao respondeu em $UrlPublica/api/health : $($_.Exception.Message)"
    $falhou = $true
}

try {
    $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
    if ($front.StatusCode -eq 200) { Bom "front servido (HTTP 200)" }
    else { Aviso "front devolveu HTTP $($front.StatusCode)"; $falhou = $true }
}
catch {
    Aviso "front nao respondeu: $($_.Exception.Message)"
    $falhou = $true
}

if ($falhou) {
    Abortar "o deploy subiu mas o smoke test nao passou. Olhe o servico: ssh e 'sudo systemctl status hipo'."
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Entregue"

Write-Host ""
Write-Host "  A 006 esta em producao e o codigo esta no ar." -ForegroundColor Green
Write-Host ""
Write-Host "  FALTA UMA COISA, e ela nao e automatizavel:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    FACA LOGOUT E LOGIN de novo em $UrlPublica" -ForegroundColor White
Write-Host ""
Write-Host "  O front le os modulos do localStorage.hipo_user, gravado no login." -ForegroundColor Gray
Write-Host "  Ctrl+Shift+R recarrega os assets mas NAO zera o localStorage." -ForegroundColor Gray
Write-Host ""
Write-Host "  Depois, na tela de Parceiros, confira:" -ForegroundColor Gray
Write-Host "    - a coluna Contato mostra 4 quadradinhos por linha" -ForegroundColor Gray
Write-Host "    - a coluna Em aberto mostra o mini-funil S/L/Q/A/N" -ForegroundColor Gray
Write-Host "    - o KPI 'Sem contato' aparece e filtra ao clicar" -ForegroundColor Gray
Write-Host "    - clicar numa linha abre o MESMO modal da oportunidade," -ForegroundColor Gray
Write-Host "      com trilho a esquerda e as abas Dados/Tarefas/Indicacoes/Carteira" -ForegroundColor Gray
Write-Host "    - na aba Tarefas, concluir EXIGE agendar a proxima" -ForegroundColor Gray
Write-Host "    - o campo Detalhe da tarefa e uma caixa de 4 linhas" -ForegroundColor Gray
Write-Host ""
Write-Host "  Nenhum modulo novo foi criado, entao ninguem perde acesso a nada." -ForegroundColor Gray
Write-Host ""
