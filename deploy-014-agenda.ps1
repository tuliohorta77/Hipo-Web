# =====================================================================
#  HIPO -- 014: agenda de reunioes + convite no Google Calendar
# =====================================================================
#
#  O QUE MUDA
#
#  Uma tela nova (Agenda) com a grade semanal do Executivo de Vendas:
#  slots de 30 minutos, 08:00-11:30 e 13:00-17:30, de segunda a sexta.
#  Clicar num horario livre marca a reuniao; ela vira evento no Google
#  Calendar do anfitriao e o Google manda o convite para o cliente.
#
#  A DECISAO QUE SUSTENTA TUDO: toda reuniao E uma tarefa. A tabela
#  `reunioes` nao repete horario, dono, titulo nem alvo -- ela aponta
#  para `tarefas` (tarefa_id UNIQUE NOT NULL) e acrescenta o que so a
#  agenda precisa. Por isso a producao do mes ja conta as reunioes, sem
#  endpoint novo e sem risco de contar duas vezes.
#
#  QUATRO PASSOS QUE O CI NAO FAZ
#
#  O job de deploy faz rsync + restart, e mais nada. A ordem entre os
#  passos abaixo NAO e negociavel:
#
#    1. MIGRATION (antes do deploy). Aditiva e idempotente. Tabela que
#       existe antes do codigo que a usa nunca quebra nada; o contrario,
#       sim.
#    2. BIBLIOTECAS DO GOOGLE (depois do deploy). O deploy NAO roda
#       pip install -- mesma armadilha do python-pptx da 009. Sem elas a
#       API sobe igual e a agenda funciona igual: o convite e que nao
#       sai, e a tela DIZ isso.
#    3. .env (DEPOIS do deploy). O pydantic-settings RECUSA chave do
#       .env que o Settings nao declara -- 'Extra inputs are not
#       permitted'. Escrever GOOGLE_SA_ARQUIVO com o codigo velho em
#       producao e reiniciar faz a API NAO SUBIR. Foi o acidente da 012.
#    4. RESTART, que e o unico jeito de o .env novo virar processo.
#
#  Entre o passo 1 e o 3 a integracao fica desligada por conta propria:
#  GOOGLE_SA_ARQUIVO tem default vazio, a reuniao e criada normalmente e
#  o motivo aparece em reunioes.google_erro e na tela.
#
#  PRE-REQUISITO QUE ESTE SCRIPT NAO FAZ, E NEM DEVE
#
#  A chave JSON da conta de servico do Google e uma CREDENCIAL. Voce a
#  coloca na EC2 com as suas maos:
#
#     scp -i $HOME\Downloads\chave-hipo.pem .\google-sa.json ec2-user@IP:/tmp/
#     ssh ...  "sudo install -o hipo -g hipo -m 600 /tmp/google-sa.json /home/hipo/app/google-sa.json && sudo rm -f /tmp/google-sa.json"
#
#  Este script apenas CONFERE que o arquivo existe, que e do usuario
#  certo e que esta em modo 600. Ele nunca le, copia nem imprime o
#  conteudo.
#
#  E antes disso, uma vez, no Google:
#     - Cloud Console: habilitar a Google Calendar API, criar a Service
#       Account, gerar a chave JSON, anotar o Client ID numerico.
#     - Admin Console do Workspace -> Seguranca -> Controles de API ->
#       Delegacao em todo o dominio -> adicionar aquele Client ID com o
#       escopo https://www.googleapis.com/auth/calendar.events
#  O passo a passo completo esta em api/services/google_agenda.py.
#
#  FLUXO
#     0. pre-voo (arquivos no disco, escopo do commit, SSH vivo)
#     1. testes locais (pytest das regras puras + vitest + build)
#     2. migration no RDS
#     3. push -> CI -> PR -> merge -> deploy CONFERIDO pelo nome do job
#     4. bibliotecas do Google na EC2
#     5. .env + restart
#     6. smoke (health + a rota da agenda respondendo)
#
#  USO
#     .\deploy-014-agenda.ps1
#     .\deploy-014-agenda.ps1 -PularTestes
#     .\deploy-014-agenda.ps1 -PularMigration    # se ja rodou
#     .\deploy-014-agenda.ps1 -SemGoogle         # sobe sem o convite
#
#  ESTE ARQUIVO E ASCII PURO.
# =====================================================================

[CmdletBinding()]
param(
    [switch]$PularTestes,
    [switch]$PularMigration,
    [switch]$PularSmoke,
    # Sobe a agenda com a integracao DESLIGADA: pula as bibliotecas e a
    # linha do .env. A tela funciona inteira, so nao manda convite, e diz
    # isso numa faixa amarela. E o caminho de quem ainda nao configurou a
    # delegacao no Admin Console e nao quer esperar por isso.
    [switch]$SemGoogle,

    [string]$RamoAlvo    = "main",
    [string]$UrlPublica  = "https://hipogestao.com.br",
    [string]$Ip          = "63.179.88.212",
    [string]$UsuarioSsh  = "ec2-user",
    [string]$Chave       = "$HOME\Downloads\chave-hipo.pem",
    [string]$ArquivoSa   = "/home/hipo/app/google-sa.json",
    [string]$Fuso        = "America/Sao_Paulo",
    [string]$Mensagem    = "feat(agenda): grade semanal de reunioes presa a tarefa + convite no Google Calendar"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$REPO_URL = "https://github.com/tuliohorta77/Hipo-Web/actions"

# As bibliotecas, pinadas. O deploy nao roda pip install: este pin so
# vale aqui e no provisionamento do zero.
$LIBS = "google-api-python-client==2.149.0 google-auth==2.35.0"

$ESPERADOS = @(
    @{ Arquivo = "api\migrations\010_agenda.sql";      Marcador = "reuniao_participantes" },
    @{ Arquivo = "api\services\agenda.py";             Marcador = "descricao_evento" },
    @{ Arquivo = "api\services\google_agenda.py";      Marcador = "with_subject" },
    @{ Arquivo = "api\routers\crm_agenda.py";          Marcador = "remover_evento_da_tarefa" },
    @{ Arquivo = "api\tests\test_agenda_regras.py";    Marcador = "TestSlotAncora" },
    @{ Arquivo = "api\tests\test_crm_agenda.py";       Marcador = "TestGoogleDesligado" },
    @{ Arquivo = "api\main.py";                        Marcador = "crm_agenda" },
    @{ Arquivo = "api\config.py";                      Marcador = "GOOGLE_SA_ARQUIVO" },
    @{ Arquivo = "api\schema.sql";                     Marcador = "reuniao_participantes" },
    @{ Arquivo = "api\requirements.txt";               Marcador = "google-api-python-client" },
    @{ Arquivo = "api\routers\crm_tarefas.py";         Marcador = "remover_evento_da_tarefa" },
    @{ Arquivo = "infra\aplicar-010-agenda.sh";        Marcador = "tipos_reuniao" },
    @{ Arquivo = "web\src\pages\crm\Agenda.jsx";       Marcador = "Marcar reuniao em" },
    @{ Arquivo = "web\src\components\crm\ModalReuniao.jsx";  Marcador = "Marcar e enviar convite" },
    @{ Arquivo = "web\src\components\crm\agendaComum.js";    Marcador = "FUSO_OPERACAO" },
    @{ Arquivo = "web\src\components\Layout.jsx";      Marcador = "/crm/agenda" },
    @{ Arquivo = "web\src\App.jsx";                    Marcador = "crm/agenda" },
    @{ Arquivo = "web\src\tests\Agenda.test.jsx";      Marcador = "Fora da grade" },
    @{ Arquivo = "web\src\tests\ModalReuniao.test.jsx"; Marcador = "Tentar de novo" }
)

# O marcador de Agenda.jsx e sem acento de proposito: o aria-label real e
# "Marcar reuniao em ... as ..." com acentos, e Get-Content -Raw num
# arquivo UTF-8 lido por PowerShell 5.1 pode embaralhar acento. Comparar
# so o trecho ASCII torna a checagem independente de encoding.

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
        Abortar "o CI ficou vermelho no run $runId. Nada foi para producao. $REPO_URL"
    }
}

function ExigirDeployFeito($runId) {
    $bruto = & gh run view $runId --json jobs
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui ler os jobs do run $runId. $REPO_URL" }
    $deploy = @((($bruto | ConvertFrom-Json).jobs) | Where-Object { $_.name -like "Deploy*" })
    if ($deploy.Count -eq 0) { Abortar "o run $runId nao tem job de Deploy. $REPO_URL" }

    $conclusao = [string]$deploy[0].conclusion
    if ($conclusao -eq "success") { Bom "job de Deploy concluido com sucesso"; return }
    if ($conclusao -eq "skipped" -or $conclusao -eq "") {
        Abortar "o job de Deploy foi PULADO no run $runId. O codigo esta no repositorio, mas NAO em producao."
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
        Abortar "arquivo da 014 nao encontrado: $($item.Arquivo)"
    }
    $conteudo = Get-Content $item.Arquivo -Raw
    if ($conteudo -notmatch [regex]::Escape($item.Marcador)) {
        Abortar "$($item.Arquivo) nao tem '$($item.Marcador)' -- versao ANTIGA do arquivo."
    }
}
Bom "os $($ESPERADOS.Count) arquivos da 014 estao no disco"

# A armadilha do schema.sql: o CI monta o banco de teste com
# `psql -f api/schema.sql`, NAO com as migrations. Migration que nao chega
# la derruba dezenas de testes no runner e passa verde na maquina de quem
# migrou a mao -- foi assim que a fase 'suspect' derrubou 45 de uma vez.
$schema = Get-Content "api\schema.sql" -Raw
foreach ($tabela in @("tipos_reuniao", "reunioes", "reuniao_participantes")) {
    if ($schema -notmatch [regex]::Escape("CREATE TABLE IF NOT EXISTS $tabela")) {
        Abortar "api\schema.sql nao cria '$tabela'. O CI monta o banco de teste a partir dele -- a suite inteira cairia."
    }
}
Bom "schema.sql espelha a migration 010"

# Asserts de igualdade exata em modulos_do_cargo quebram a cada modulo
# novo. Esta entrega NAO cria modulo (a agenda vive em 'crm'), entao os
# asserts tem que continuar como estavam -- este aviso existe para o dia
# em que alguem decidir o contrario.
$asserts = @(Select-String -Path "api\tests\*.py" -Pattern 'modulos_do_cargo.*==|body\["modulos"\].*==' -ErrorAction SilentlyContinue)
Passo "asserts de modulos_do_cargo encontrados: $($asserts.Count) (a 014 nao cria modulo, entao nenhum deveria mudar)"

$sujos = @(& git status --porcelain)
if ($sujos.Count -gt 0) {
    Write-Host ""
    Write-Host "  O commit vai levar:" -ForegroundColor Yellow
    foreach ($l in $sujos) { Write-Host "     $l" -ForegroundColor Gray }
    $inesperados = @($sujos | Where-Object {
        $_ -notmatch 'api/(migrations/010_agenda\.sql|services/(agenda|google_agenda)\.py|routers/(crm_agenda|crm_tarefas)\.py|tests/test_(agenda_regras|crm_agenda)\.py|main\.py|config\.py|schema\.sql|requirements\.txt|\.env\.template)' -and
        $_ -notmatch 'infra/aplicar-010-agenda\.sh' -and
        $_ -notmatch 'web/src/(App\.jsx|components/(Layout\.jsx|crm/(ModalReuniao\.jsx|agendaComum\.js|AbaTarefas\.jsx|OportunidadeDetalhe\.jsx|tarefaComum\.jsx))|pages/crm/(Agenda|Oportunidades|Tarefas)\.jsx|tests/(Agenda|ModalReuniao|Layout)\.test\.jsx)' -and
        $_ -notmatch 'deploy-014-agenda\.ps1'
    })
    if ($inesperados.Count -gt 0) {
        Write-Host ""
        Aviso "$($inesperados.Count) arquivo(s) fora do escopo desta entrega."
        Confirmar "Levar tudo isso junto mesmo assim?"
    }
    else { Bom "so os arquivos da 014" }
}
else { Aviso "arvore limpa -- nada novo para commitar." }

Passo "SSH..."
& ssh -i $Chave -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 `
    "$UsuarioSsh@$Ip" "echo vivo" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Abortar "SSH nao respondeu. A migration e o .env precisam dele -- resolva antes de comecar."
}
Bom "SSH vivo"

# A chave JSON e credencial: este script CONFERE, nunca le nem copia.
if (-not $SemGoogle) {
    Passo "chave da conta de servico do Google na EC2..."
    $modo = & ssh -i $Chave "$UsuarioSsh@$Ip" "sudo stat -c '%U:%G %a' $ArquivoSa 2>/dev/null || echo ausente"
    $modo = ($modo | Out-String).Trim()
    if ($modo -eq "ausente") {
        Write-Host ""
        Aviso "nao existe $ArquivoSa na EC2."
        Write-Host "     Coloque a chave com as suas maos (este script nunca toca no conteudo):" -ForegroundColor Gray
        Write-Host "       scp -i `"$Chave`" .\google-sa.json ${UsuarioSsh}@${Ip}:/tmp/" -ForegroundColor White
        Write-Host "       ssh -i `"$Chave`" $UsuarioSsh@$Ip `"sudo install -o hipo -g hipo -m 600 /tmp/google-sa.json $ArquivoSa; sudo rm -f /tmp/google-sa.json`"" -ForegroundColor White
        Write-Host ""
        Write-Host "     Ou rode com -SemGoogle: a agenda sobe inteira e so nao manda convite." -ForegroundColor Gray
        Abortar "chave ausente."
    }
    if ($modo -ne "hipo:hipo 600") {
        Aviso "a chave esta como '$modo'; o esperado e 'hipo:hipo 600'."
        Aviso "dono errado faz o config do app nem conseguir abrir o arquivo (foi o que derrubou o ensaio do fechamento diario em 31/08)."
        Confirmar "Seguir mesmo assim?"
    }
    else { Bom "chave presente, hipo:hipo 600" }
}
else {
    Aviso "-SemGoogle: subindo com o convite DESLIGADO."
}

$temGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
$ramo  = (& git rev-parse --abbrev-ref HEAD).Trim()
Passo "ramo atual: $ramo"
$noAlvo = ($ramo -eq $RamoAlvo)
if (-not $noAlvo) {
    Aviso "push em '$ramo' NAO deploya: o deploy so roda na '$RamoAlvo'."
}

# =====================================================================
# 1. Testes locais
# =====================================================================

if ($PularTestes) {
    Titulo "1. Testes locais -- PULADOS"
    Aviso "o CI ainda roda tudo."
}
else {
    Titulo "1. Testes locais"

    # As regras da agenda sao PURAS: sem banco, sem rede, sem Google.
    # Rodam no Windows sem Postgres, ao contrario de test_crm_agenda.py,
    # que so valida no CI.
    Push-Location "api"
    try {
        $env:PYTHONPATH = (Get-Location).Path
        Executar "pytest (regras da agenda)" { python -m pytest tests/test_agenda_regras.py -q }
        Bom "regras da agenda verdes"
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
# 2. Migration no RDS
# =====================================================================

if ($PularMigration) {
    Titulo "2. Migration -- PULADA"
    Aviso "so use isto se a 010 JA foi aplicada; sem as tabelas, a agenda da 500."
}
else {
    Titulo "2. Migration 010_agenda no RDS"

    Write-Host ""
    Write-Host "  ADITIVA e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS e um" -ForegroundColor Gray
    Write-Host "  INSERT com ON CONFLICT DO NOTHING. Nenhum DROP, nenhum ALTER" -ForegroundColor Gray
    Write-Host "  destrutivo -- por isso nao exige o export em CSV que as" -ForegroundColor Gray
    Write-Host "  migrations destrutivas exigem." -ForegroundColor Gray
    Write-Host "  Roda ANTES do deploy: tabela que existe antes do codigo que a" -ForegroundColor Gray
    Write-Host "  usa nunca quebra nada; o contrario, sim." -ForegroundColor Gray

    Confirmar "Aplicar a 010 no RDS de producao?"

    Executar "enviando a migration" {
        scp -i $Chave "api\migrations\010_agenda.sql" "${UsuarioSsh}@${Ip}:/tmp/010_agenda.sql"
    }
    Executar "enviando o aplicador" {
        scp -i $Chave "infra\aplicar-010-agenda.sh" "${UsuarioSsh}@${Ip}:/tmp/aplicar-010-agenda.sh"
    }
    Executar "aplicando" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo bash /tmp/aplicar-010-agenda.sh /tmp/010_agenda.sql"
    }
    Bom "tabelas da agenda criadas"
}

# =====================================================================
# 3. Push, CI e deploy
# =====================================================================

Titulo "3. Push e deploy"

$sujos = & git status --porcelain
if ($sujos) {
    Confirmar "Commitar e empurrar?"
    Executar "git add"    { git add -A }
    Executar "git commit" { git commit -m $Mensagem }
    Bom "commit criado"
}

$aFrente = "0"
try   { $aFrente = (& git rev-list --count "origin/$ramo..$ramo").Trim() }
catch { $aFrente = "?" }

# O id do run ANTES do push. Sem ele nao ha como distinguir "o Actions ja
# criou o run novo" de "ainda nao criou, e estou olhando o anterior" -- e o
# anterior esta verde, entao a diferenca e entre conferir o deploy e
# inventar que ele aconteceu.
$idAntesDoPush = ""
if ($temGh) {
    $anterior = RunMaisRecente $ramo
    if ($anterior) { $idAntesDoPush = [string]$anterior.databaseId }
}

Executar "git push" { git push origin $ramo }
$empurrouAlgo = ($aFrente -ne "0")
Bom "codigo no repositorio, no ramo $ramo"

if (-not $temGh) {
    Aviso "gh nao instalado -- abra o PR, mergeie e confira o job Deploy em $REPO_URL"
}
elseif ($noAlvo) {
    if ($empurrouAlgo) {
        $runMain = EsperarRunNovo $RamoAlvo $idAntesDoPush 60
        if (-not $runMain) {
            Abortar "push feito mas nao vi run novo na $RamoAlvo. NAO siga para o passo do .env sem conferir o deploy em $REPO_URL"
        }
        AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
        ExigirDeployFeito ([string]$runMain.databaseId)
    }
    else {
        Aviso "nada empurrado -- pulando a conferencia do CI"
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
        else { Aviso "nenhum run novo no ramo. $REPO_URL" }
    }

    $numeroPr = ""
    $bruto = & gh pr list --head $ramo --base $RamoAlvo --state open --json number
    if ($LASTEXITCODE -eq 0) {
        $prs = @($bruto | ConvertFrom-Json)
        if ($prs.Count -gt 0) { $numeroPr = [string]$prs[0].number }
    }

    if (-not $numeroPr) {
        Passo "nenhum PR aberto -- criando"
        & gh pr create --base $RamoAlvo --head $ramo --title $Mensagem --body "Entrega 014 -- agenda de reunioes. Toda reuniao E uma tarefa (tarefa_id UNIQUE NOT NULL): horario, dono, titulo e alvo continuam em tarefas. Migration 010 (aditiva) aplicada antes do deploy. As bibliotecas do Google e a linha GOOGLE_SA_ARQUIVO no .env entram DEPOIS do deploy -- o pydantic-settings recusa chave que o Settings nao declara."
        if ($LASTEXITCODE -ne 0) {
            Abortar "nao consegui criar o PR. Se foi 'No commits between', o merge ja aconteceu: use .\deploy-007-retomar.ps1."
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
        Abortar "merge feito mas nao vi run novo na $RamoAlvo. $REPO_URL"
    }
    AcompanharRun ([string]$runMain.databaseId) "os 3 jobs, deploy incluido"
    ExigirDeployFeito ([string]$runMain.databaseId)
}

# =====================================================================
# 4. Bibliotecas do Google na EC2 -- SO AGORA
# =====================================================================

if ($SemGoogle) {
    Titulo "4. Bibliotecas do Google -- PULADAS (-SemGoogle)"
}
else {
    Titulo "4. Bibliotecas do Google na EC2"

    Write-Host ""
    Write-Host "  O deploy faz rsync e reinicia, NAO roda pip install -- mesma" -ForegroundColor Gray
    Write-Host "  armadilha do python-pptx da 009. Sem estas duas, a API sobe" -ForegroundColor Gray
    Write-Host "  igual e a agenda funciona igual: o convite e que nao sai." -ForegroundColor Gray

    # `sudo -iu hipo`, e nao `sudo -u`: o pip precisa do HOME do usuario
    # do app para achar o mesmo site-packages que a unit usa. Mesma linha
    # que a 009 usou para o python-pptx.
    Executar "instalando" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo -iu hipo pip install --quiet $LIBS"
    }

    # Conferir pelo IMPORT, e nao pela saida do pip: pip que instalou no
    # site-packages errado sai com 0 e o import continua falhando -- foi
    # exatamente o sintoma do python-pptx.
    Passo "conferindo o import de dentro do usuario do app..."
    $prova = & ssh -i $Chave "$UsuarioSsh@$Ip" "sudo -iu hipo python3 -c 'import googleapiclient, google.oauth2.service_account; print(\"import ok\")' 2>&1 || true"
    $prova = ($prova | Out-String).Trim()
    if ($prova -notmatch "import ok") {
        Write-Host $prova -ForegroundColor DarkGray
        Abortar "as bibliotecas nao importam como o usuario 'hipo'. O pip pode ter instalado no site-packages errado -- confira o interpretador da unit."
    }
    Bom "googleapiclient e google-auth importam como 'hipo'"
}

# =====================================================================
# 5. .env e restart
# =====================================================================

Titulo "5. GOOGLE_SA_ARQUIVO no .env"

Write-Host ""
Write-Host "  Este passo so pode acontecer com o codigo novo JA em producao." -ForegroundColor Yellow
Write-Host "  O pydantic-settings recusa chave do .env que o Settings nao" -ForegroundColor Yellow
Write-Host "  declara ('Extra inputs are not permitted'), e a API nao sobe." -ForegroundColor Yellow

# A prova DIRETA, olhando o arquivo que esta na maquina -- e nao a
# conclusao de um run do CI, que ja se provou possivel de ler errado.
Passo "conferindo que o codigo em producao ja conhece o campo..."
$temCampo = & ssh -i $Chave "$UsuarioSsh@$Ip" `
    "grep -c 'GOOGLE_SA_ARQUIVO' /home/hipo/app/api/config.py || true"
$temCampo = ($temCampo | Out-String).Trim()

if ($temCampo -eq "0" -or -not $temCampo) {
    Abortar @"
o config.py em producao NAO tem GOOGLE_SA_ARQUIVO -- o deploy do codigo novo
    nao chegou na maquina. Gravar a chave no .env agora derrubaria a API.
    Confira o run em $REPO_URL e rode de novo com -PularTestes -PularMigration.
"@
}
Bom "config.py em producao conhece o campo ($temCampo ocorrencia(s))"

if ($SemGoogle) {
    Aviso "-SemGoogle: nao vou gravar GOOGLE_SA_ARQUIVO. A agenda sobe com o convite desligado."
    Passo "reiniciando a API mesmo assim (o codigo novo precisa do restart)..."
    Executar "reiniciando a API" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo systemctl restart hipo-api"
    }
}
else {
    Confirmar "Gravar GOOGLE_SA_ARQUIVO e GOOGLE_CALENDAR_FUSO no .env e reiniciar a API?"

    # Idempotente: rodar de novo nao duplica a linha. Aspas SIMPLES por
    # fora -- o PowerShell 5.1 come aspas duplas nao escapadas ao montar a
    # linha de comando de um executavel nativo (ssh.exe), e os valores
    # aqui nao tem espaco nem caractere especial.
    $cmdSa = "sudo grep -q '^GOOGLE_SA_ARQUIVO=' /home/hipo/app/.env " +
             "&& echo 'ja existia' " +
             "|| sudo sh -c 'echo GOOGLE_SA_ARQUIVO=$ArquivoSa >> /home/hipo/app/.env'"
    Executar "gravando GOOGLE_SA_ARQUIVO" { ssh -i $Chave "$UsuarioSsh@$Ip" $cmdSa }

    $cmdFuso = "sudo grep -q '^GOOGLE_CALENDAR_FUSO=' /home/hipo/app/.env " +
               "&& echo 'ja existia' " +
               "|| sudo sh -c 'echo GOOGLE_CALENDAR_FUSO=$Fuso >> /home/hipo/app/.env'"
    Executar "gravando GOOGLE_CALENDAR_FUSO" { ssh -i $Chave "$UsuarioSsh@$Ip" $cmdFuso }

    # Conferir o que FICOU no arquivo, e nao so que o comando saiu com 0.
    $linha = & ssh -i $Chave "$UsuarioSsh@$Ip" "sudo grep '^GOOGLE_SA_ARQUIVO=' /home/hipo/app/.env"
    $linha = ($linha | Out-String).Trim()
    if ($linha -ne "GOOGLE_SA_ARQUIVO=$ArquivoSa") {
        Abortar "a linha gravada ficou '$linha', e nao 'GOOGLE_SA_ARQUIVO=$ArquivoSa'. Corrija a mao antes de reiniciar a API."
    }
    Bom "linha conferida no .env: $linha"

    Executar "reiniciando a API" {
        ssh -i $Chave "$UsuarioSsh@$Ip" "sudo systemctl restart hipo-api"
    }
}
Bom "hipo-api reiniciado"

Passo "esperando a API voltar..."
Start-Sleep -Seconds 6

# =====================================================================
# 6. Smoke
# =====================================================================

Titulo "6. Smoke"

if ($PularSmoke) {
    Aviso "smoke pulado"
}
else {
    Passo "API..."
    try {
        $health = Invoke-RestMethod -Uri "$UrlPublica/api/health" -TimeoutSec 20
        if (-not $health.versao) { Abortar "/health respondeu sem o campo 'versao': $($health | ConvertTo-Json -Compress)" }
        Bom "API viva -- versao $($health.versao)"
    }
    catch {
        Abortar "a API NAO respondeu depois do restart: $($_.Exception.Message). Veja 'sudo journalctl -u hipo-api -n 50' -- se for 'Extra inputs are not permitted', o .env ganhou a chave antes do codigo."
    }

    # A versao do app nao e bumpada, entao /health nao diz o que esta no
    # ar. As ROTAS dizem: se /crm/agenda/semana esta no openapi, o deploy
    # chegou. Foi assim que se confirmou anexos e propostas em 09/09.
    Passo "rotas da agenda no openapi..."
    try {
        $spec = Invoke-RestMethod -Uri "$UrlPublica/api/openapi.json" -TimeoutSec 20
        $rotas = $spec.paths.PSObject.Properties.Name
        foreach ($r in @("/crm/agenda/semana", "/crm/agenda/reunioes", "/crm/agenda/tipos")) {
            if ($rotas -notcontains $r) { Abortar "a rota $r NAO esta em producao. O deploy do codigo novo nao chegou." }
        }
        Bom "as 3 rotas da agenda estao no ar"
    }
    catch {
        Abortar "nao consegui ler o openapi: $($_.Exception.Message)"
    }

    Passo "front..."
    try {
        $front = Invoke-WebRequest -Uri $UrlPublica -TimeoutSec 20 -UseBasicParsing
        if ($front.StatusCode -ne 200) { Abortar "o front respondeu HTTP $($front.StatusCode)" }
        Bom "front servido (HTTP 200)"
    }
    catch { Abortar "o front nao respondeu: $($_.Exception.Message)" }
}

# =====================================================================
# Fim
# =====================================================================

Titulo "Agenda no ar"

Write-Host ""
Write-Host "  RELOGUE ANTES DE PROCURAR O ITEM 'Agenda' NA BARRA." -ForegroundColor Yellow
Write-Host "  O front le os modulos do localStorage.hipo_user, gravado no" -ForegroundColor Gray
Write-Host "  login. Ctrl+Shift+R recarrega os assets mas nao zera o" -ForegroundColor Gray
Write-Host "  localStorage -- so logout/login forca um /auth/me novo." -ForegroundColor Gray
Write-Host "  (A agenda vive no modulo 'crm', que todo cargo ja tem, entao" -ForegroundColor Gray
Write-Host "  desta vez o relogin e por causa do BUNDLE, nao da permissao.)" -ForegroundColor Gray
Write-Host ""
Write-Host "  O primeiro teste de ponta a ponta, com o cliente de verdade:" -ForegroundColor Gray
Write-Host "     1. Agenda -> escolha uma pessoa no seletor da direita" -ForegroundColor White
Write-Host "     2. clique num horario livre" -ForegroundColor White
Write-Host "     3. escolha a oportunidade, o tipo e o contato" -ForegroundColor White
Write-Host "     4. 'Marcar e enviar convite'" -ForegroundColor White
Write-Host "     5. confira o evento na agenda do Google do anfitriao" -ForegroundColor White
Write-Host ""
if ($SemGoogle) {
    Write-Host "  O convite esta DESLIGADO (-SemGoogle): a tela avisa numa faixa" -ForegroundColor Yellow
    Write-Host "  amarela e cada reuniao guarda o motivo em google_erro. Quando" -ForegroundColor Yellow
    Write-Host "  a delegacao estiver pronta, rode de novo sem -SemGoogle e use" -ForegroundColor Yellow
    Write-Host "  'Tentar de novo' nas reunioes ja marcadas." -ForegroundColor Yellow
    Write-Host ""
}
Write-Host "  Se o convite nao sair, o erro aparece NA TELA, em portugues," -ForegroundColor Gray
Write-Host "  com botao de tentar de novo. Os dois mais comuns:" -ForegroundColor Gray
Write-Host "     - 'O Google recusou o acesso'  -> falta a delegacao no Admin" -ForegroundColor DarkGray
Write-Host "       Console, ou o escopo calendar.events nao esta na lista" -ForegroundColor DarkGray
Write-Host "     - 'Bibliotecas do Google nao instaladas' -> o passo 4" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  AJUSTE OS TIPOS DE REUNIAO. A semente e um palpite, menos" -ForegroundColor Yellow
Write-Host "  'Apresentacao', que veio de um convite real. O nome vai para o" -ForegroundColor Yellow
Write-Host "  TITULO do evento que o cliente le. Corrigir e um UPDATE:" -ForegroundColor Yellow
Write-Host "     UPDATE tipos_reuniao SET nome = 'nome certo' WHERE sigla = 'CF';" -ForegroundColor White
Write-Host ""
