# =====================================================================
#  HIPO -- deploy 019: parceria vira ilha no Monitor
# =====================================================================
#
#  O QUE MUDA EM PRODUCAO
#
#  Reuniao de parceiro (tarefa com conta_id) para de contar em AGEN, APRE,
#  AGEND MES e no % NOSHOW. Passa a aparecer SO no quadro PARCERIAS.
#
#  Os numeros da TV VAO CAIR no dia do deploy, e isso e o conserto, nao um
#  problema: PARCERIAS era um subconjunto de APRE, ou seja, a mesma reuniao
#  era lida duas vezes na mesma tela.
#
#  SEM MIGRATION, SEM SCRIPT REMOTO, SEM CARGA.
#
#  Tres arquivos de codigo, nenhuma coluna nova, nenhum dado tocado. O
#  rollback e um `git revert` -- nao ha estado de banco para desfazer.
#
#  A ORDEM
#
#    1. pre-voo   -- arquivos no lugar E com o patch dentro
#    2. testes    -- regras puras do monitor + vitest + build
#    3. push      -- o CI faz rsync e reinicia o servico
#    4. espera    -- ate o codigo novo aparecer no servidor
#    5. prova     -- quanto do mes era parceria, para voce recalibrar as metas
#
#  POR QUE O PRE-VOO LE O CONTEUDO, E NAO SO O NOME DO ARQUIVO
#
#  Os tres arquivos ja existiam antes desta entrega. Conferir Test-Path
#  aprovaria a pasta sem o patch aplicado, e o deploy subiria o codigo
#  velho com uma mensagem de commit dizendo o contrario.
#
#  USO
#     .\deploy-019-parceria-ilha.ps1 -Simular     # nao muda nada, so confere
#     .\deploy-019-parceria-ilha.ps1
#     .\deploy-019-parceria-ilha.ps1 -PularTestes
#
#  ESTE ARQUIVO E ASCII PURO.
#
#  (PowerShell 5.1 come aspas duplas ao montar linha de comando externa, e
#  comentario com acento embaralha no copiar-e-colar. As duas coisas ja
#  custaram deploy aqui.)
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

    [string]$Pasta    = "C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0",
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "63.179.88.212",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 600
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

function Confirmar($pergunta) {
    Write-Host ""
    $r = Read-Host "  $pergunta  [digite SIM para seguir]"
    if ($r -ne "SIM") { Abortar "cancelado por voce." }
}

$alvo = "$Usuario@$Servidor"

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"

if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path $Pasta)) { Abortar "nao achei a pasta: $Pasta" }
Set-Location $Pasta
Bom "pasta: $Pasta"

# Arquivo -> trecho que SO existe depois do patch. Os padroes sao ASCII
# puro de proposito: ancorar em comentario com acento quebra no Windows por
# causa do encoding misto dos arquivos antigos.
$marcas = @(
    @{ Arquivo = "api\routers\monitor.py"
       Padrao  = 'AND t.conta_id IS NULL'
       Porque  = "o JOIN que tira parceria do AGEND MES" },
    @{ Arquivo = "api\routers\monitor.py"
       Padrao  = 'if r\["conta_id"\] is not None:'
       Porque  = "o corte antes da contagem no loop" },
    @{ Arquivo = "api\services\monitor.py"
       Padrao  = 'unico quadro onde parceria aparece'
       Porque  = "a procedencia nova do quadro PARCERIAS" },
    @{ Arquivo = "api\tests\test_monitor.py"
       Padrao  = 'test_parceria_nao_vaza_para_nenhum_quadro_comercial'
       Porque  = "o teste que trava os quatro numeros" }
)

$faltando = @()
foreach ($m in $marcas) {
    $caminho = Join-Path $Pasta $m.Arquivo
    if (-not (Test-Path $caminho)) {
        $faltando += "$($m.Arquivo)  [arquivo nao existe]"
        continue
    }
    $achou = Select-String -Path $caminho -Pattern $m.Padrao -Quiet
    if (-not $achou) { $faltando += "$($m.Arquivo)  [sem $($m.Porque)]" }
}
if ($faltando.Count -gt 0) {
    Write-Host ""
    foreach ($f in $faltando) { Write-Host "     $f" -ForegroundColor Red }
    Abortar "o patch da 019 nao esta aplicado na pasta."
}
Bom "os 3 arquivos estao com o patch da 019"

# Rede de seguranca: o vazamento tambem vivia no count solto de AGEND MES.
# Se essa linha sobreviveu, o patch foi aplicado pela metade.
$sobrou = Select-String -Path (Join-Path $Pasta "api\routers\monitor.py") `
    -Pattern 'SELECT count\(\*\) FROM reunioes WHERE criado_em' -Quiet
if ($sobrou) {
    Abortar "o count antigo de AGEND MES ainda esta la -- patch pela metade."
}
Bom "o count antigo de AGEND MES sumiu"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Bom "chave SSH encontrada"

Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
}
catch { $aberta = $false }

if (-not $aberta) {
    Write-Host ""
    Write-Host "  A porta 22 nao respondeu. Se o erro for TIMEOUT, seu IP saiu" -ForegroundColor Gray
    Write-Host "  do Security Group (IP residencial e dinamico):" -ForegroundColor Gray
    Write-Host "     .\liberar-meu-ip-ssh.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "  Esta entrega NAO precisa de SSH para subir -- quem faz o" -ForegroundColor Gray
    Write-Host "  deploy e o CI. O SSH so serve para eu confirmar que o codigo" -ForegroundColor Gray
    Write-Host "  chegou e para contar quanto do mes era parceria." -ForegroundColor Gray
    Confirmar "Seguir mesmo assim, sem as etapas 4 e 5?"
    $SemSsh = $true
}
else {
    Bom "porta 22 responde"
    $SemSsh = $false
}

# =====================================================================
# 2. Testes
# =====================================================================

Titulo "2. Testes"

if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
}
else {
    # As regras puras do monitor rodam sem Postgres. Os testes com db_conn
    # (inclusive o test_parceria_nao_vaza...) ficam com o CI -- e por isso
    # que os 3 jobs precisam ficar verdes antes de dar a entrega por feita.
    Passo "pytest das regras puras do monitor..."
    # Get-Command antes de chamar: com ErrorActionPreference=Stop, um
    # `python` que nao existe no PATH derruba o script com excecao em vez
    # da mensagem daqui.
    $temPython = $null -ne (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $temPython) {
        Aviso "python nao esta no PATH -- quem valida e o CI"
    }
    else {
        Push-Location (Join-Path $Pasta "api")
        try {
            # Sem isto o import de `services` falha: o pytest roda com o
            # cwd fora do sys.path em algumas versoes.
            $env:PYTHONPATH = (Get-Location).Path
            & python -m pytest --version 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Aviso "pytest indisponivel aqui -- quem valida e o CI"
            }
            else {
                & python -m pytest tests\test_monitor_regras.py -q
                if ($LASTEXITCODE -ne 0) { Abortar "as regras puras do monitor falharam." }
                Bom "regras puras verdes"
            }
        }
        finally { Pop-Location }
    }

    # O front nao mudou nesta entrega (sigla, rotulo e procedencia vem do
    # payload). Mas o job Frontend Tests tem que ficar verde igual, e
    # descobrir isso pelo CI custa uma viagem.
    Passo "vitest..."
    Push-Location (Join-Path $Pasta "web")
    try {
        & npm.cmd run test -- --run
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Corrija antes de subir." }
        Bom "vitest verde"

        Passo "vite build..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Abortar "o build do front falhou." }
        Bom "build ok"
    }
    finally { Pop-Location }
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

Write-Host ""
Write-Host "  Sem migration nesta entrega: nenhuma coluna nova, nenhum dado" -ForegroundColor Gray
Write-Host "  tocado. Rollback e um git revert." -ForegroundColor Gray

$mensagem = @"
fix(monitor): parceria conta so no quadro PARCERIAS

Reuniao de parceiro (tarefa com conta_id) saia em AGEN, APRE, AGEND MES
e nos dois lados do % NOSHOW, e ainda aparecia em PARCERIAS -- que era um
subconjunto de APRE. Em setembro/2026 a TV mostrava APRE 44 com PARCERIAS
24: a operacao comercial tinha feito 20.

O corte e exato, nao heuristico: ck_tarefa_alvo garante alvo unico por
tarefa, entao conta_id IS NULL e a definicao de reuniao comercial. Filtro
em dois pontos -- um continue no inicio do loop de _reunioes, antes de
qualquer contagem, e o JOIN tarefas no count de AGEND MES, que era o unico
numero do painel que nao passava por tarefas.

No-show de parceiro deixa de aparecer no painel: e assunto da carteira de
parceiros, nao do funil.

As metas do mes foram calibradas com os numeros inflados -- revisar em
Metas e calendario junto com este deploy.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UKbZ6PDvLZYKXBbevJz7TS
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    Write-Host ""
    Write-Host "  git status --short:" -ForegroundColor DarkGray
    & git status --short
}
else {
    $sujo = & git status --porcelain
    if (-not $sujo) {
        Aviso "nada para commitar -- o codigo ja esta versionado"
    }
    else {
        Write-Host ""
        Write-Host "  O que vai no commit:" -ForegroundColor DarkGray
        & git status --short
        Write-Host ""
        Write-Host "  Confira se nao ha lixo junto. No commit 789937e foram" -ForegroundColor Gray
        Write-Host "  tres arquivos de fora da entrega por causa de um git add ." -ForegroundColor Gray
        Write-Host "  (o monitor.patch da raiz e um deles, e continua la)" -ForegroundColor Gray
        Confirmar "Commitar e dar push na main?"

        & git add -A
        if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }

        # A mensagem vai por arquivo, e nao por -m: PowerShell 5.1 come as
        # aspas ao montar a linha de comando externa, e a mensagem sai
        # picada em pedacos.
        $tmpMsg = Join-Path $env:TEMP "hipo-commit-019.txt"
        Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
        & git commit -F $tmpMsg
        if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou." }
        Remove-Item $tmpMsg -ErrorAction SilentlyContinue
        Bom "commit criado"

        & git push
        if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
        Bom "push feito -- o CI assumiu daqui"
    }
}

# =====================================================================
# 4. Espera o codigo novo chegar no servidor
# =====================================================================

Titulo "4. Esperando o CI"

# Nao ha arquivo novo nesta entrega, entao o marcador e o CONTEUDO. Um
# `test -f` aprovaria o servidor com o codigo velho.
#
# Vai por base64 pelo mesmo motivo do SQL la embaixo: o grep precisa de
# aspas simples em volta do padrao (ele tem espacos), e o PowerShell 5.1
# remonta a linha de comando do ssh e embaralha as aspas. Em base64 nao
# sobra aspa nenhuma para ele mexer.
$provaSh = "grep -q 'AND t.conta_id IS NULL' /home/hipo/app/api/routers/monitor.py"
$provaB64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($provaSh))
$prova = "echo $provaB64 | base64 -d | bash"

if ($Simular -or $SemSsh) {
    Aviso "nao vou esperar (simulacao ou sem SSH)"
    Write-Host ""
    Write-Host "  Acompanhe em github.com/tuliohorta77/Hipo-Web/actions --" -ForegroundColor Gray
    Write-Host "  os 3 jobs precisam ficar verdes." -ForegroundColor Gray
}
else {
    Write-Host ""
    Write-Host "  Os 3 jobs precisam ficar verdes (Backend + Frontend + Deploy)." -ForegroundColor Gray
    Write-Host "  Vou perguntar ao servidor ate o codigo novo estar la." -ForegroundColor Gray
    Write-Host ""

    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou  = $false

    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new `
            $alvo $prova 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        $s = [int]$relogio.Elapsed.TotalSeconds
        Write-Host "     ainda nao ($s s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 15
    }
    $relogio.Stop()

    if (-not $chegou) {
        Write-Host ""
        Aviso "o codigo novo nao chegou em $EsperaMax s."
        Write-Host ""
        Write-Host "  Nada a desfazer -- esta entrega nao mexe em banco." -ForegroundColor Gray
        Write-Host "  Confira o run em github.com/tuliohorta77/Hipo-Web/actions." -ForegroundColor Gray
        Write-Host ""
        Write-Host "  Deploy que morre no meio deixa estado misto (backend novo," -ForegroundColor Gray
        Write-Host "  tela velha). Aqui a tela nao mudou, entao backend novo ja" -ForegroundColor Gray
        Write-Host "  e a entrega inteira." -ForegroundColor Gray
        Write-Host ""
        exit 0
    }
    Bom "codigo novo no servidor ($([int]$relogio.Elapsed.TotalSeconds) s)"

    Passo "a API respondeu depois do restart?"
    try {
        $r = Invoke-WebRequest -Uri "https://hipogestao.com.br/api/openapi.json" `
            -TimeoutSec 20 -UseBasicParsing
        if ($r.StatusCode -eq 200) { Bom "openapi.json responde 200" }
        else { Aviso "openapi.json voltou $($r.StatusCode)" }
    }
    catch { Aviso "nao consegui falar com a API: $($_.Exception.Message)" }
}

# =====================================================================
# 5. Quanto do mes era parceria
# =====================================================================

Titulo "5. Quanto do mes era parceria"

if ($Simular) {
    Write-Host ""
    Write-Host "  Simulacao terminada. Nada foi alterado." -ForegroundColor Cyan
    Write-Host "  Para valer:  .\deploy-019-parceria-ilha.ps1" -ForegroundColor White
    Write-Host ""
    exit 0
}

if ($SemSsh) {
    Aviso "sem SSH -- pule para o que falta voce fazer, abaixo"
}
else {
    Write-Host ""
    Write-Host "  Contagem BRUTA por alvo, do dia 1o ate agora. Nao e o painel:" -ForegroundColor Gray
    Write-Host "  aqui ninguem olha desfecho, entao o numero nao vai bater com" -ForegroundColor Gray
    Write-Host "  AGEN nem com APRE. Serve para dimensionar o tamanho da queda" -ForegroundColor Gray
    Write-Host "  e recalibrar as metas -- o numero que vale e o da TV." -ForegroundColor Gray
    Write-Host ""

    # ESTE TRECHO VAI POR BASE64, E NAO COMO STRING DE ASPAS.
    #
    # PowerShell 5.1 remonta a linha de comando de um executavel externo e
    # COME as aspas duplas. Um SQL com aspas, passado direto para o ssh,
    # chega picado e o psql estoura em erro de sintaxe. Em base64 nao ha
    # aspa para ele comer -- o que viaja e um blob ASCII.
    #
    # O .env e 600 e o dono NAO e necessariamente `hipo` -- em producao e
    # do ec2-user. A cascata cobre os tres estados.
    $remoto = @'
set -e
ENVV=$(sudo cat /home/hipo/app/.env 2>/dev/null \
    || sudo -iu hipo cat /home/hipo/app/.env 2>/dev/null \
    || cat /home/hipo/app/.env)
DB=$(printf '%s\n' "$ENVV" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
psql "$DB" -At <<'SQL'
SELECT 'reunioes com prazo no mes -- cliente: '
       || count(*) FILTER (WHERE t.conta_id IS NULL)
       || ' | parceria: '
       || count(*) FILTER (WHERE t.conta_id IS NOT NULL)
  FROM reunioes r JOIN tarefas t ON t.id = r.tarefa_id
 WHERE t.prazo >= date_trunc('month', now() AT TIME ZONE 'America/Sao_Paulo');
SELECT 'agendadas no mes           -- cliente: '
       || count(*) FILTER (WHERE t.conta_id IS NULL)
       || ' | parceria: '
       || count(*) FILTER (WHERE t.conta_id IS NOT NULL)
  FROM reunioes r JOIN tarefas t ON t.id = r.tarefa_id
 WHERE r.criado_em >= date_trunc('month', now() AT TIME ZONE 'America/Sao_Paulo');
SELECT 'metas gravadas para este mes: ' || count(*)
  FROM monitor_metas
 WHERE ano = extract(year from now() AT TIME ZONE 'America/Sao_Paulo')::int
   AND mes = extract(month from now() AT TIME ZONE 'America/Sao_Paulo')::int;
SQL
'@

    $b64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes(($remoto -replace "`r`n", "`n"))
    )

    & ssh -i $Chave $alvo "echo $b64 | base64 -d | bash"
    if ($LASTEXITCODE -ne 0) { Aviso "nao consegui ler os numeros -- confira pela tela" }
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host "  FALTA VOCE FAZER" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  1. Abra /monitor e confira a queda." -ForegroundColor White
Write-Host "     APRE, AGEN e AGEND MES vao cair, e o % NOSHOW muda de base." -ForegroundColor Gray
Write-Host "     PARCERIAS fica igual -- e o unico quadro que nao mexeu." -ForegroundColor Gray
Write-Host "     Nao precisa de logout: nenhum modulo novo nesta entrega." -ForegroundColor Gray
Write-Host ""
Write-Host "  2. RECALIBRE AS METAS do mes (botao Metas e calendario)." -ForegroundColor White
Write-Host "     As de setembro foram feitas com o numero inflado: 48 AGEN," -ForegroundColor Gray
Write-Host "     72 APRE, 48 AGEND MES. Sem ajustar, a TV fica vermelha sem a" -ForegroundColor Gray
Write-Host "     operacao ter piorado -- e carinha brava que ninguem acredita" -ForegroundColor Gray
Write-Host "     e pior do que quadro sem meta." -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Avise a equipe ANTES de eles verem a TV." -ForegroundColor White
Write-Host "     Quem acompanha o painel todo dia vai ver APRE cair pela" -ForegroundColor Gray
Write-Host "     metade. A explicacao de uma linha: parceria saiu do funil" -ForegroundColor Gray
Write-Host "     comercial e agora conta so no quadro dela." -ForegroundColor Gray
Write-Host ""
Write-Host "  4. O relatorio diario CONTINUA misturando." -ForegroundColor White
Write-Host "     services/relatorio_reunioes.py lista reuniao de parceiro" -ForegroundColor Gray
Write-Host "     junto com as de cliente. Ate decidir isso, o e-mail da manha" -ForegroundColor Gray
Write-Host "     e a TV vao discordar de proposito." -ForegroundColor Gray
Write-Host ""
