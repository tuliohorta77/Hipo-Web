# =====================================================================
#  HIPO -- deploy 019: quadro de pessoal sai do LinkedIn e vai para o
#                      eSocial (Econodata -> Oportunidados)
# =====================================================================
#
#  O QUE ESTE SCRIPT FAZ, NA ORDEM QUE IMPORTA
#
#    1. pre-voo   -- arquivos no lugar, chave SSH, porta 22
#    2. testes    -- vitest e build do front (o pytest de banco fica no CI)
#    3. push      -- o CI faz rsync e reinicia o servico
#    4. espera    -- ate o codigo novo aparecer no servidor
#    5. .env      -- token da Oportunidados, depois a lista de fontes
#    6. limpeza   -- zera os estimados herdados da Econodata
#    7. CSV       -- traz o arquivo de seguranca para a sua maquina
#    8. prova     -- conta o que ficou no banco
#
#  POR QUE O .env VEM DEPOIS DO PUSH, E NUNCA ANTES
#
#  O Settings do pydantic roda com extra="forbid": variavel no .env que o
#  config.py nao declara ABORTA O IMPORT, e a API nao sobe -- nginx
#  respondendo 502 em tudo. Gravar OPORTUNIDADOS_API_TOKEN antes do
#  config.py novo chegar derruba o sistema no primeiro restart.
#
#  (O por-chave-no-env.sh do lado de la confere isso sozinho e recusa
#  gravar. Este script so respeita a ordem para nao depender da recusa.)
#
#  POR QUE A LIMPEZA VEM DEPOIS DO .env
#
#  O enriquecimento nao sobrescreve campo que ja tem valor. Os numeros da
#  Econodata ficam la para sempre a menos que virem NULL -- mas zerar
#  ANTES da fonte nova responder tira o numero errado sem por nada no
#  lugar. O script do servidor recusa rodar se a fonte nao estiver ligada.
#
#  NAO HA MIGRATION AQUI. Nenhuma coluna muda. O que muda e o CONTEUDO de
#  contas.num_funcionarios nas linhas de origem 'estimado' -- e isso sai
#  em CSV antes, que e a regra do projeto para mudanca destrutiva.
#
#  O QUE NUNCA E TOCADO: num_funcionarios_origem = 'declarado'. O numero
#  que o cliente informou e o que precifica; o filtro esta no WHERE do
#  SQL, nao numa condicao em Python.
#
#  USO
#     .\deploy-019-oportunidados.ps1 -Simular      # nao muda nada
#     .\deploy-019-oportunidados.ps1
#     .\deploy-019-oportunidados.ps1 -PularTestes
#     .\deploy-019-oportunidados.ps1 -SoLimpeza    # CI ja verde, .env ja feito
#
#  ESTE ARQUIVO E ASCII PURO.
#
#  (PowerShell 5.1 come aspas duplas ao montar linha de comando externa, e
#  comentario com acento embaralha no copiar-e-colar. As duas coisas ja
#  custaram deploy aqui -- dai a regra do ASCII e dos argumentos passados
#  como array, nunca como string montada.)
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoLimpeza,

    [string]$Pasta    = "C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0",
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    # Nome, e nao IP. A instancia nao tem Elastic IP: o endereco muda a
    # cada stop/start e ja mandei comando para o IP velho neste projeto.
    [string]$Servidor = "hipogestao.com.br",
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

if ($Simular)  { Aviso "MODO SIMULACAO -- nada sera alterado" }
if ($SoLimpeza) { Aviso "MODO -SoLimpeza -- pulando testes, push e espera" }

if (-not (Test-Path $Pasta)) { Abortar "nao achei a pasta: $Pasta" }
Set-Location $Pasta
Bom "pasta: $Pasta"

# Os arquivos da entrega. Se um sumiu, o deploy quebra la na frente --
# por isso a conferencia vem antes de qualquer coisa sair daqui.
$esperados = @(
    "api\config.py",
    "api\services\enriquecimento\fontes.py",
    "api\services\enriquecimento\modelo.py",
    "api\services\enriquecimento\persistencia.py",
    "api\scripts\zerar_funcionarios_estimados.py",
    "api\tests\test_crm_enriquecimento.py",
    "infra\zerar-funcionarios-estimados.sh",
    "infra\por-chave-no-env.sh"
)

$faltando = @()
foreach ($f in $esperados) {
    if (-not (Test-Path (Join-Path $Pasta $f))) { $faltando += $f }
}
if ($faltando.Count -gt 0) {
    Write-Host ""
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($esperados.Count) arquivos da entrega conferidos"

# Conferencia de conteudo, nao so de presenca: um arquivo pode estar la e
# ser a versao velha (pasta restaurada de backup, copia parcial).
$provas = @{
    "api\config.py"                                = "OPORTUNIDADOS_API_TOKEN"
    "api\services\enriquecimento\fontes.py"        = "buscar_oportunidados"
    "api\services\enriquecimento\modelo.py"        = "normalizar_oportunidados"
    "api\services\enriquecimento\persistencia.py"  = "normalizar_oportunidados"
}
foreach ($arq in $provas.Keys) {
    $marca = $provas[$arq]
    if (-not (Select-String -Path (Join-Path $Pasta $arq) -Pattern $marca -Quiet)) {
        Abortar "$arq nao contem '$marca' -- a pasta esta com a versao velha."
    }
}
Bom "conteudo dos 4 arquivos de codigo conferido"

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
    Abortar "sem SSH nao da para ligar a fonte nem limpar o banco."
}
Bom "porta 22 responde"

# =====================================================================
# 2. Testes do front
# =====================================================================

Titulo "2. Testes do front"

if ($SoLimpeza -or $PularTestes) {
    Aviso "pulado (o CI roda tudo de qualquer jeito)"
}
else {
    # O pytest de banco NAO roda aqui: sem Postgres local ele falha nos
    # testes com db_conn. Quem valida o backend e o job do CI.
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

$mensagem = @"
feat(enriquecimento): quadro de pessoal passa a vir da Oportunidados

A Econodata inferia o numero de funcionarios do LinkedIn e errava por
ordem de grandeza no nosso segmento (3 onde havia 115). A Oportunidados
devolve contagem exata de origem trabalhista (RAIS/eSocial), confirmada
pelo fornecedor em 23/09/2026.

Junto, dois consertos que o caso revelou:

- faixa nunca mais e lida como contagem. `{"codigo": 3}` e
  `faixaFuncionarios: 3` eram gravados como 3 funcionarios; agora
  quantidade_de_faixa() recusa numero solto, que e indice e nao
  quantidade.
- fontes_habilitadas() deriva a lista de BUSCADORES em vez de repetir
  os nomes a mao. A `oportunidados` ja estava registrada e continuava
  sendo recusada no .env como desconhecida.

scripts/zerar_funcionarios_estimados.py zera o que a Econodata deixou
gravado -- campo vazio e o unico que o enriquecimento preenche sozinho.
Nunca toca em origem 'declarado', e exporta CSV antes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BxSMHJfYav864xun8YJPuE
"@

if ($SoLimpeza) {
    Aviso "pulado por -SoLimpeza"
}
elseif ($Simular) {
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

# O marcador NAO e "o arquivo existe": persistencia.py ja existia antes.
# E o conteudo -- so a versao nova importa o normalizador da fonte nova.
$provaRemota = "grep -q normalizar_oportunidados /home/hipo/app/api/services/enriquecimento/persistencia.py"

if ($SoLimpeza) {
    Aviso "pulado por -SoLimpeza"
}
elseif ($Simular) {
    Aviso "simulacao: nao vou esperar"
}
else {
    Write-Host ""
    Write-Host "  Os 3 jobs precisam ficar verdes (Backend + Frontend + Deploy)." -ForegroundColor Gray
    Write-Host "  Vou perguntar ao servidor ate o codigo novo aparecer la." -ForegroundColor Gray
    Write-Host ""

    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou  = $false

    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new `
            $alvo $provaRemota 2>$null
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
        Write-Host "  NADA foi alterado em producao -- nem .env, nem banco." -ForegroundColor Gray
        Write-Host "  Confira o run em github.com/tuliohorta77/Hipo-Web/actions" -ForegroundColor Gray
        Write-Host "  e, quando ficar verde, rode so o resto:" -ForegroundColor Gray
        Write-Host ""
        Write-Host "     .\deploy-019-oportunidados.ps1 -SoLimpeza" -ForegroundColor White
        Write-Host ""
        exit 0
    }
    Bom "codigo novo no servidor ($([int]$relogio.Elapsed.TotalSeconds) s)"
}

# =====================================================================
# 5. .env -- token e lista de fontes
# =====================================================================

Titulo "5. Ligando a Oportunidados no .env"

$porChave = Join-Path $Pasta "infra\por-chave-no-env.sh"
$zerar    = Join-Path $Pasta "infra\zerar-funcionarios-estimados.sh"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem rodar nada"
}
else {
    Passo "enviando os scripts..."
    & scp -i $Chave -o StrictHostKeyChecking=accept-new `
        $porChave $zerar "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp falhou." }
    Bom "scripts em /tmp/ no servidor"

    Write-Host ""
    Write-Host "  Voce vai digitar DOIS valores, um de cada vez. Nenhum dos" -ForegroundColor Gray
    Write-Host "  dois aparece na tela e nenhum passa por linha de comando --" -ForegroundColor Gray
    Write-Host "  argumento vaza no 'ps' de qualquer usuario da maquina." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  1o) o token da Oportunidados" -ForegroundColor White
    Write-Host "  2o) a lista de fontes, exatamente assim:" -ForegroundColor White
    Write-Host ""
    Write-Host "         brasilapi,oportunidados" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "     (a ordem e a precedencia: a primeira que trouxer o campo" -ForegroundColor Gray
    Write-Host "      vence. A econodata sai da lista -- se o nome dela ficar," -ForegroundColor Gray
    Write-Host "      ela continua sendo consultada e continua sendo cobrada.)" -ForegroundColor Gray
    Write-Host ""

    # O `-t` nao e detalhe: o script do lado de la le o valor de /dev/tty.
    # Sem terminal alocado ele nem tenta -- avisa e sai. (Script que chega
    # por pipe nao consegue usar `read`: o stdin do bash E o proprio
    # script.)
    Passo "token da Oportunidados..."
    & ssh -t -i $Chave $alvo "bash /tmp/por-chave-no-env.sh OPORTUNIDADOS_API_TOKEN"
    if ($LASTEXITCODE -ne 0) { Abortar "gravar o token falhou (codigo $LASTEXITCODE)." }
    Bom "token gravado e servico reiniciado"

    Passo "lista de fontes..."
    & ssh -t -i $Chave $alvo "bash /tmp/por-chave-no-env.sh ENRIQUECIMENTO_FONTES"
    if ($LASTEXITCODE -ne 0) { Abortar "gravar as fontes falhou (codigo $LASTEXITCODE)." }
    Bom "fontes gravadas e servico reiniciado"
}

# =====================================================================
# 6. Limpeza dos estimados herdados
# =====================================================================

Titulo "6. Zerando os estimados da Econodata"

if ($Simular) {
    Aviso "simulacao: nao vou rodar a limpeza"
}
else {
    Write-Host ""
    Write-Host "  O script simula primeiro: mostra quantas contas, quais, e" -ForegroundColor Gray
    Write-Host "  grava o CSV de seguranca ANTES de perguntar. So depois que" -ForegroundColor Gray
    Write-Host "  voce confirmar e que alguma coisa muda no banco." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Ele recusa rodar se a Oportunidados nao estiver no ar e" -ForegroundColor Gray
    Write-Host "  ligada -- zerar sem ter quem repreencha deixaria o campo" -ForegroundColor Gray
    Write-Host "  vazio para sempre." -ForegroundColor Gray
    Write-Host ""

    & ssh -t -i $Chave $alvo "bash /tmp/zerar-funcionarios-estimados.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a limpeza falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "limpeza concluida"
}

# =====================================================================
# 7. Trazer o CSV de seguranca
# =====================================================================

Titulo "7. CSV de seguranca"

if ($Simular) {
    Aviso "simulacao: nao ha CSV para trazer"
}
else {
    # /tmp some no reboot. O CSV e a unica copia do que foi descartado --
    # regra do projeto: mudanca destrutiva so vale com o export na mao.
    $destino = Join-Path $Pasta "backups"
    if (-not (Test-Path $destino)) { New-Item -ItemType Directory -Path $destino | Out-Null }

    Passo "procurando o CSV mais recente no servidor..."
    $remoto = & ssh -i $Chave $alvo "ls -t /tmp/funcionarios_estimados_*.csv 2>/dev/null | grep -v simulacao | head -1"

    if (-not $remoto) {
        Aviso "nenhum CSV de gravacao encontrado (a limpeza nao gravou nada?)"
    }
    else {
        $remoto = $remoto.Trim()
        & scp -i $Chave "${alvo}:$remoto" $destino
        if ($LASTEXITCODE -ne 0) {
            Aviso "o scp do CSV falhou. Traga a mao antes de reiniciar a maquina:"
            Write-Host "     scp -i `"$Chave`" ${alvo}:$remoto ." -ForegroundColor White
        }
        else {
            $nome = Split-Path $remoto -Leaf
            Bom "CSV salvo em backups\$nome"
        }
    }
}

# =====================================================================
# 8. Prova
# =====================================================================

Titulo "8. Prova"

if ($Simular) {
    Write-Host ""
    Write-Host "  Simulacao terminada. Nada foi alterado." -ForegroundColor Cyan
    Write-Host "  Para valer:  .\deploy-019-oportunidados.ps1" -ForegroundColor White
    Write-Host ""
    exit 0
}

Passo "a API responde?"
try {
    $r = Invoke-WebRequest -Uri "https://hipogestao.com.br/api/openapi.json" `
        -TimeoutSec 20 -UseBasicParsing
    if ($r.StatusCode -eq 200) { Bom "openapi.json responde 200" }
    else { Aviso "openapi.json voltou $($r.StatusCode)" }
}
catch { Aviso "nao consegui falar com a API: $($_.Exception.Message)" }

Passo "como ficou o quadro de pessoal no banco?"

# ESTE TRECHO VAI POR BASE64, E NAO COMO STRING DE ASPAS.
#
# PowerShell 5.1 remonta a linha de comando de um executavel externo e COME
# as aspas duplas. Um SQL com aspas, passado direto para o ssh, chega
# picado do outro lado e o psql estoura em erro de sintaxe. Em base64 nao
# ha aspa nenhuma para ele comer -- o que viaja e um blob ASCII.
#
# (Aqui o `| bash` e seguro. O que nao pode e um script com `read` chegar
# assim: o stdin do bash vira o proprio script e a pergunta falha em
# silencio. Este trecho so consulta.)
$remotoSql = @'
set -e
ENVV=$(sudo cat /home/hipo/app/.env 2>/dev/null \
    || sudo -iu hipo cat /home/hipo/app/.env 2>/dev/null \
    || cat /home/hipo/app/.env)
DB=$(printf '%s\n' "$ENVV" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
psql "$DB" -At <<'SQL'
SELECT 'declarado (do cliente, intocado): '
       || count(*) FILTER (WHERE num_funcionarios_origem = 'declarado'
                             AND num_funcionarios IS NOT NULL)
  FROM contas;
SELECT 'estimado ainda gravado: '
       || count(*) FILTER (WHERE num_funcionarios_origem = 'estimado'
                             AND num_funcionarios IS NOT NULL)
  FROM contas;
SELECT 'contas ativas sem quadro de pessoal: '
       || count(*) FILTER (WHERE num_funcionarios IS NULL)
       || ' de ' || count(*)
  FROM contas WHERE ativo;
SQL
'@

$b64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes(($remotoSql -replace "`r`n", "`n"))
)

& ssh -i $Chave $alvo "echo $b64 | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { Aviso "nao consegui ler os numeros -- confira pela tela" }

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host "  FALTA VOCE FAZER" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  1. Abrir UMA conta conhecida e apertar ATUALIZAR DADOS PUBLICOS." -ForegroundColor White
Write-Host "     E o teste de fogo: o numero tem que voltar da Oportunidados." -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Nao espere as outras voltarem sozinhas." -ForegroundColor White
Write-Host "     Zerar nao dispara consulta. O campo so e preenchido quando" -ForegroundColor Gray
Write-Host "     alguem abre a conta e aperta o botao, ou quando o cache de" -ForegroundColor Gray
Write-Host "     90 dias vence. Abrir a aba NAO reconsulta." -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Cancelar a Econodata." -ForegroundColor White
Write-Host "     O nome saiu do ENRIQUECIMENTO_FONTES, entao ela nao e mais" -ForegroundColor Gray
Write-Host "     consultada -- mas a assinatura continua correndo ate voce" -ForegroundColor Gray
Write-Host "     cancelar com eles. A ECONODATA_API_KEY pode ficar no .env:" -ForegroundColor Gray
Write-Host "     chave sem fonte na lista nao consulta nada." -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Guardar o CSV de backups\ fora da maquina." -ForegroundColor White
Write-Host "     E a unica copia do que foi descartado." -ForegroundColor Gray
Write-Host ""
