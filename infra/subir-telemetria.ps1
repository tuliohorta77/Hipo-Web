# =====================================================================
# HIPO - Subida da telemetria e do fechamento diario.
#
# Impoe a ordem obrigatoria do projeto:
#     testes -> migration em producao -> push
# e se recusa a chegar no push se qualquer etapa anterior falhar. O deploy
# faz rsync do codigo e reinicia o servico; ele NAO roda DDL. Invertida a
# ordem, o codigo novo sobe pedindo uso_eventos e relatorios_diarios que nao
# existem, e o middleware estoura em TODA request autenticada.
#
# ASCII PURO: PowerShell 5.1 le .ps1 sem BOM como ANSI, e um acento em
# comentario desbalanceia string e derruba o parser do arquivo inteiro.
# SEM ENCADEAMENTO estilo shell: o operador de dois E-comerciais nao existe no
# PowerShell 5.1, e como e erro de PARSE nada do arquivo roda. Cada comando
# confere $LASTEXITCODE na linha seguinte.
#
# Rodar de: C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0
# =====================================================================

[CmdletBinding()]
param(
    [string] $Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string] $Servidor = '63.179.88.212',
    [string] $Usuario  = 'ec2-user',
    [string] $Destino  = 'main',
    [switch] $PularTestes
)

$ErrorActionPreference = 'Stop'

function Titulo($t) {
    Write-Host ''
    Write-Host ('=' * 70) -ForegroundColor DarkGray
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor DarkGray
}
function Ok($t)    { Write-Host "  [ok] $t"    -ForegroundColor Green }
function Aviso($t) { Write-Host "  [!]  $t"    -ForegroundColor Yellow }
function Parar($t) { throw $t }

function Confirmar($pergunta) {
    Write-Host ''
    $r = Read-Host "  $pergunta  (digite SIM para seguir)"
    if ($r -cne 'SIM') { Parar 'Cancelado por voce. Nada foi feito nesta etapa.' }
}

function Remoto($chave, $alvo, $comando) {
    # ErrorActionPreference = 'Stop' faz o PowerShell transformar QUALQUER
    # stderr de comando nativo em NativeCommandError e abortar. O psql escreve
    # os NOTICE de "already exists, skipping" no stderr -- ou seja, a propria
    # prova de idempotencia derrubaria o script. Aqui o stderr volta a ser
    # texto; quem decide sucesso e o codigo de saida, nao o canal.
    $antigo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $linhas = & ssh -i $chave $alvo $comando 2>&1 | ForEach-Object { $_.ToString() }
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $antigo
    }
    $linhas | ForEach-Object { Write-Host "  $_" }
    return [pscustomobject]@{ Texto = ($linhas -join "`n"); Codigo = $codigo }
}

# =====================================================================
Titulo 'FASE 0 - Verificacoes antes de tocar em qualquer coisa'
# =====================================================================

if (-not (Test-Path '.git')) { Parar 'Rode da raiz do repositorio.' }
if (-not (Test-Path $Chave)) { Parar "Chave SSH nao encontrada: $Chave" }
Ok "Repositorio e chave SSH no lugar"

# A armadilha que derruba a suite inteira: o CI monta o banco de teste com
# `psql -f api/schema.sql`, NAO com as migrations. Migration que nao chegou no
# schema.sql = todo teste com db_conn morre em "relation does not exist" -- e o
# conftest ainda trunca relatorios_diarios na fixture, entao nem os testes de
# outros modulos escapam.
$schema = Get-Content 'api\schema.sql' -Raw
foreach ($tabela in @('uso_eventos', 'relatorios_diarios')) {
    if (-not $schema.Contains($tabela)) {
        Parar "api/schema.sql nao tem '$tabela'. O CI monta o banco de teste a partir dele: sem isso a suite inteira cai. Atualize o schema.sql antes."
    }
}
Ok 'schema.sql cobre as tabelas da migration 007'

$sujo = git status --porcelain
if ($sujo) {
    Write-Host $sujo
    Parar 'Working tree sujo. Commite ou guarde antes de subir.'
}
Ok 'Working tree limpo'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host ''
Write-Host "  Branch atual : $branch"
Write-Host "  Vai para     : $Destino"
Write-Host "  Servidor     : $Usuario@$Servidor"
Write-Host ''
Write-Host '  Arquivos que entram:' -ForegroundColor DarkGray
git diff --stat "$Destino...HEAD"

# =====================================================================
Titulo 'FASE 1 - Testes de logica pura (local)'
# =====================================================================

if ($PularTestes) {
    Aviso 'Pulados por -PularTestes. O CI ainda vai cobrar.'
} else {
    Push-Location 'api'
    try {
        $env:PYTHONPATH = (Get-Location).Path
        # Apenas os que nao precisam de Postgres. O resto valida no CI.
        #
        # test_telemetria_ruido.py NAO esta na lista de proposito: ele importa
        # middleware.telemetria, que importa config, e config exige
        # DATABASE_URL e JWT_SECRET ja no import. E o mesmo motivo pelo qual
        # test_buffer_telemetria.py -- que importa o mesmo modulo -- nunca
        # esteve aqui. Os dois validam no CI, que tem Postgres e ambiente.
        #
        # Para rodar a mao, com api/.env presente:
        #   py -m pytest tests/test_telemetria_ruido.py tests/test_buffer_telemetria.py
        py -m pytest -q -p no:cacheprovider `
            tests/test_validacao_numerica.py `
            tests/test_tarefa_regras.py `
            tests/test_parceiro_regras.py `
            tests/test_oportunidade_regras.py `
            tests/test_dias_uteis.py
        if ($LASTEXITCODE -ne 0) { Parar 'Testes locais falharam. Nada foi enviado.' }
    } finally { Pop-Location }
    Ok 'Testes de logica pura passaram'
}

# =====================================================================
Titulo 'FASE 2 - Migration 007 em PRODUCAO (antes do push)'
# =====================================================================

Write-Host '  A 007 e aditiva e idempotente: so cria tabela e indice com'
Write-Host '  IF NOT EXISTS. Nao apaga nada, entao dispensa export previo.'
Write-Host '  O script roda ela DUAS VEZES para provar a idempotencia.'
Confirmar 'Aplicar a migration 007 no banco de PRODUCAO?'

$sh = @(
    'set -e',
    'cd /home/hipo/app',
    'D=$(sudo sed -n "s/^DATABASE_URL=//p" .env)',
    'if [ -z "$D" ]; then echo "DATABASE_URL vazia"; exit 1; fi',
    'echo "--- host do banco (mascarado) ---"',
    'echo "$D" | sed "s/:[^:@]*@/:****@/"',
    'echo "--- tabelas antes ---"',
    'psql "$D" -Atc "select count(*) from information_schema.tables where table_name in (''uso_eventos'',''relatorios_diarios'');"',
    'echo "--- aplicando (1a vez) ---"',
    'psql "$D" -v ON_ERROR_STOP=1 -f /tmp/007_telemetria.sql',
    'echo "--- aplicando (2a vez, prova de idempotencia) ---"',
    'psql "$D" -v ON_ERROR_STOP=1 -f /tmp/007_telemetria.sql',
    'echo "--- tabelas depois ---"',
    'psql "$D" -Atc "select table_name from information_schema.tables where table_name in (''uso_eventos'',''relatorios_diarios'') order by 1;"',
    'rm -f /tmp/007_telemetria.sql /tmp/aplicar-007.sh',
    'echo "MIGRATION OK"'
) -join "`n"

# LF explicito e ASCII: editor do Windows salva CRLF e o bash quebra no
# primeiro \r. Por isso WriteAllBytes, e nao Set-Content.
$shLocal = Join-Path $env:TEMP 'aplicar-007.sh'
[System.IO.File]::WriteAllBytes($shLocal, [System.Text.Encoding]::ASCII.GetBytes($sh))

scp -i $Chave 'api\migrations\007_telemetria.sql' "${Usuario}@${Servidor}:/tmp/"
if ($LASTEXITCODE -ne 0) { Parar 'scp da migration falhou.' }
scp -i $Chave $shLocal "${Usuario}@${Servidor}:/tmp/"
if ($LASTEXITCODE -ne 0) { Parar 'scp do script falhou.' }

# Gravado em .sh e executado com bash: `ssh ... 'cmd1; cmd2'` quebra no
# primeiro ponto e virgula.
$r = Remoto $Chave "${Usuario}@${Servidor}" 'bash /tmp/aplicar-007.sh'
if ($r.Codigo -ne 0) { Parar 'A migration falhou. NADA foi enviado para o repositorio.' }
if (-not $r.Texto.Contains('MIGRATION OK')) { Parar 'A migration nao confirmou sucesso. Push cancelado.' }
Ok 'Migration 007 aplicada e idempotente'

# =====================================================================
Titulo 'FASE 3 - Merge e push'
# =====================================================================

Write-Host '  O deploy so dispara em push para main. Este passo publica o'
Write-Host '  middleware de telemetria, que intercepta TODA request'
Write-Host '  autenticada -- se ele tiver problema, nao e uma tela que quebra,'
Write-Host '  e o sistema inteiro.'
Write-Host ''
Write-Host '  Antes de confirmar, deixe aberto em outra janela:' -ForegroundColor Yellow
Write-Host "    ssh -i `"$Chave`" $Usuario@$Servidor" -ForegroundColor Yellow
Write-Host '    sudo journalctl -u hipo-api -f' -ForegroundColor Yellow
Confirmar "Fazer merge de '$branch' em '$Destino' e push?"

git checkout $Destino
if ($LASTEXITCODE -ne 0) { Parar "Nao consegui trocar para $Destino." }
git pull --ff-only
if ($LASTEXITCODE -ne 0) { Parar "git pull falhou. Resolva antes de mesclar." }
git merge --no-ff $branch -m "feat: telemetria de uso e fechamento diario por e-mail"
if ($LASTEXITCODE -ne 0) { Parar 'Merge com conflito. Resolva e rode de novo a partir da FASE 3.' }
git push origin $Destino
if ($LASTEXITCODE -ne 0) { Parar 'Push falhou.' }
Ok "Push para $Destino feito"

# NAO disparar workflow_dispatch aqui: dois runs simultaneos colidem no
# deploy e o `concurrency: cancel-in-progress` mata um deles.

# =====================================================================
Titulo 'FASE 4 - Acompanhar o CI'
# =====================================================================

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Aviso 'gh CLI nao encontrado. Acompanhe em:'
    Write-Host '    https://github.com/tuliohorta77/Hipo-Web/actions'
    Confirmar 'Os 3 jobs (Backend, Frontend, Deploy) ficaram verdes?'
} else {
    $ErrorActionPreference = 'Continue'

    # POR QUE BUSCAR O ID EM VEZ DE 'gh run watch' PELADO
    #
    # Sem id, o watch abre um SELETOR INTERATIVO. Enquanto rodava colado ao
    # terminal isso passava; assim que a saida comecou a ser capturada, o gh
    # perdeu o TTY e passou a morrer com 'run ID required when not running
    # interactively' -- que o script leu como CI vermelho, pela terceira vez
    # em duas semanas.
    #
    # Buscar pelo SHA elimina os dois problemas de uma vez: nao precisa de
    # TTY, e garante que estamos olhando o run DESTE push e nao de outro que
    # por acaso estivesse na fila.
    $sha = (git rev-parse HEAD).Trim()
    Write-Host "  commit: $sha"

    function Rede($texto) {
        return ($texto -match 'error connecting') -or `
               ($texto -match 'check your internet connection') -or `
               ($texto -match 'Could not resolve host') -or `
               ($texto -match 'dial tcp')
    }

    $runId    = $null
    $semRede  = $false
    foreach ($tentativa in 1..10) {
        Start-Sleep -Seconds 6
        $r = & gh run list --commit $sha --limit 1 --json databaseId --jq '.[0].databaseId' 2>&1
        $codigo = $LASTEXITCODE
        $txt = (($r | ForEach-Object { $_.ToString() }) -join "`n").Trim()
        if ($codigo -ne 0) {
            if (Rede $txt) { $semRede = $true; break }
            Write-Host "  $txt"
            continue
        }
        if ($txt -match '^\d+$') { $runId = $txt; break }
        Write-Host "  aguardando o run aparecer no GitHub... ($tentativa/10)"
    }

    if ($semRede) {
        Aviso 'O gh nao conseguiu falar com o GitHub. Isso NAO diz nada sobre'
        Aviso 'o CI -- o push ja foi feito e o deploy pode ter subido.'
        Write-Host '    https://github.com/tuliohorta77/Hipo-Web/actions'
        Confirmar 'Os 3 jobs (Backend, Frontend, Deploy) ficaram verdes?'
    } elseif (-not $runId) {
        Aviso 'Nao achei nenhum run do CI para este commit.'
        Write-Host '    https://github.com/tuliohorta77/Hipo-Web/actions'
        Confirmar 'Os 3 jobs (Backend, Frontend, Deploy) ficaram verdes?'
    } else {
        Write-Host "  run: $runId"
        # Sem captura: o watch precisa do terminal para desenhar o progresso,
        # e ja provamos que a rede esta de pe ao buscar o id.
        & gh run watch $runId --exit-status
        $codigo = $LASTEXITCODE
        if ($codigo -eq 0) {
            $ErrorActionPreference = 'Stop'
            Ok 'Os 3 jobs verdes'
        } else {
            # O watch tambem sai diferente de zero se a conexao cair no meio.
            # A CONCLUSAO do run e a resposta autoritativa: perguntar de novo
            # separa 'o CI reprovou' de 'eu perdi a conexao'.
            $c = & gh run view $runId --json conclusion --jq '.conclusion' 2>&1
            $conclusao = (($c | ForEach-Object { $_.ToString() }) -join "`n").Trim()
            $ErrorActionPreference = 'Stop'
            if ($conclusao -eq 'success') {
                Ok 'Os 3 jobs verdes (o watch caiu, a conclusao do run confirma)'
            } elseif (Rede $conclusao) {
                Aviso 'Perdi a conexao com o GitHub durante o acompanhamento.'
                Write-Host "    gh run view $runId"
                Confirmar 'Os 3 jobs ficaram verdes?'
            } else {
                Aviso "Conclusao do run: $conclusao"
                Aviso 'O CI falhou. O banco JA esta migrado (aditivo, nao atrapalha).'
                Aviso 'Corrija, commite e o proximo push refaz o deploy.'
                Write-Host "    gh run view $runId --log-failed"
                Parar 'CI vermelho.'
            }
        }
    }
    $ErrorActionPreference = 'Stop'
}

# =====================================================================
Titulo 'FASE 5 - Verificacao pos-deploy'
# =====================================================================

# O passo "Verificar deploy" do CI usa `curl ... || echo 'Frontend OK'`, entao
# ele passa SEMPRE, mesmo com o front quebrado. Esta verificacao e a de
# verdade.
$verificar = @(
    'set -e',
    'echo "--- servico ---"',
    'systemctl is-active hipo-api',
    'echo "--- erros no log desde o restart ---"',
    'sudo journalctl -u hipo-api --since "3 min ago" -p err --no-pager | tail -20 || true',
    'echo "--- a telemetria esta gravando? ---"',
    'cd /home/hipo/app',
    'D=$(sudo sed -n "s/^DATABASE_URL=//p" .env)',
    'psql "$D" -Atc "select count(*) from uso_eventos;"',
    'rm -f /tmp/verificar.sh'
) -join "`n"

$vLocal = Join-Path $env:TEMP 'verificar.sh'
[System.IO.File]::WriteAllBytes($vLocal, [System.Text.Encoding]::ASCII.GetBytes($verificar))
scp -i $Chave $vLocal "${Usuario}@${Servidor}:/tmp/" | Out-Null
Remoto $Chave "${Usuario}@${Servidor}" 'bash /tmp/verificar.sh' | Out-Null

Write-Host ''
Write-Host '  Front (o healthcheck do CI mente, este nao):' -ForegroundColor DarkGray
try {
    $r = Invoke-WebRequest -Uri 'https://hipogestao.com.br' -UseBasicParsing -TimeoutSec 15
    Ok "https://hipogestao.com.br respondeu $($r.StatusCode)"
} catch {
    Aviso "O site nao respondeu: $($_.Exception.Message)"
}

Titulo 'PRONTO'
Write-Host '  Faltam, e sao passos manuais de proposito:'
Write-Host ''
Write-Host '   1. Navegue algumas telas do HIPO e rode de novo:'
Write-Host '      select count(*) from uso_eventos;'
Write-Host '      O numero tem que subir. Se ficar em zero, o middleware nao'
Write-Host '      esta registrando e o relatorio vai sair vazio todo dia.'
Write-Host ''
Write-Host '   2. Primeiro fechamento a seco, sem enviar e-mail:'
Write-Host '      cd /home/hipo/app/api'
Write-Host '      set -a; . /home/hipo/app/.env; set +a'
Write-Host '      python3 -m scripts.fechamento_diario --so-imprime'
Write-Host ''
Write-Host '   3. So depois de o passo 2 sair com cara boa, habilite o timer:'
Write-Host '      sudo cp infra/hipo-fechamento.* /etc/systemd/system/'
Write-Host '      sudo systemctl daemon-reload'
Write-Host '      sudo systemctl enable --now hipo-fechamento.timer'
Write-Host '      systemctl list-timers hipo-fechamento.timer'
Write-Host ''
Write-Host '   Lembrete: o OnCalendar do timer precisa do fuso como SUFIXO'
Write-Host '   (Timezone= nao existe no systemd).'
Write-Host ''
