# =====================================================================
#  HIPO -- deploy 045: contatos (ABM / multithreading)
# =====================================================================
#
#  O que entra:
#    * Oportunidade com LISTA de contatos (aba Contatos): papel na decisao
#      (decisor, campeao, influenciador, operacional, compras, tecnico),
#      um principal (espelho de oportunidades.contato_id) e o farol de
#      multithreading (ideal: 2 a 4 pessoas).
#    * Contato OBRIGATORIO em ligacao, reuniao, visita, WhatsApp e e-mail
#      (criar, editar, proxima tarefa e agenda). Tarefa antiga aberta so
#      pede o contato quando for editada.
#    * Editar contato no lugar (2o telefone, WhatsApp, LinkedIn) -- acabou
#      o "excluir e cadastrar de novo".
#    * UC: aulas 10 (Account Based) e 11 (Multithreading) no 04 . Tecnicas
#      do SDR na pratica.
#
#    1. pre-voo      -- arquivos, base do git, migration 028 livre, SSH
#    2. testes       -- regras puras + conteudo da UC (o CI roda o resto)
#    3. migration    -- 028 no RDS ANTES do push (aditiva, idempotente)
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#    6. carga UC     -- trilhas com --atualizar (aulas 10 e 11)
#
#  USO
#     .\deploy-045-contatos-multithreading.ps1 -Simular
#     .\deploy-045-contatos-multithreading.ps1
#     .\deploy-045-contatos-multithreading.ps1 -SoCarga   (push ja foi; so a etapa 6)
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoCarga,

    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 1800
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

# Commit sobre o qual a entrega foi feita (main local em 05/10/2026).
$base = "0b7f227"

$substituidos = @(
    "api\main.py",
    "api\routers\crm_agenda.py",
    "api\routers\crm_contas.py",
    "api\routers\crm_contatos.py",
    "api\routers\crm_oportunidades.py",
    "api\routers\crm_tarefas.py",
    "api\schema.sql",
    "api\scripts\uc_conteudo_hipo.py",
    "api\scripts\uc_conteudo_tecnicas_sdr.py",
    "api\services\atividade.py",
    "api\services\tarefa.py",
    "api\tests\conftest.py",
    "api\tests\test_crm_agenda.py",
    "api\tests\test_crm_avaliacao.py",
    "api\tests\test_crm_relatorios.py",
    "api\tests\test_crm_tarefas.py",
    "api\tests\test_crm_transcricao.py",
    "api\tests\test_monitor.py",
    "api\tests\test_tarefas_parceiro.py",
    "api\tests\test_uc_conteudo.py",
    "web\src\components\crm\AbaTarefas.jsx",
    "web\src\components\crm\ContatosDaConta.jsx",
    "web\src\components\crm\DesfechoReuniao.jsx",
    "web\src\components\crm\KanbanOportunidades.jsx",
    "web\src\components\crm\ModalReuniao.jsx",
    "web\src\components\crm\OportunidadeDetalhe.jsx",
    "web\src\components\crm\tarefaComum.jsx",
    "web\src\pages\crm\Oportunidades.jsx",
    "web\src\pages\crm\Tarefas.jsx",
    "web\src\tests\AbaTarefas.test.jsx",
    "web\src\tests\ModalReuniao.test.jsx",
    "web\src\tests\Parceiros.test.jsx",
    "web\src\tests\Tarefas.test.jsx"
)

$novos = @(
    "api\migrations\028_contatos_multithreading.sql",
    "api\routers\crm_oportunidade_contatos.py",
    "api\services\contato_oportunidade.py",
    "api\tests\test_contato_oportunidade_regras.py",
    "api\tests\test_crm_multithreading.py",
    "web\src\components\crm\AbaContatos.jsx",
    "web\src\components\crm\contatoComum.jsx",
    "web\src\tests\ContatosMultithreading.test.jsx",
    "infra\aplicar-028-contatos-multithreading.sh",
    "deploy-045-contatos-multithreading.ps1"
)

$entrega = $substituidos + $novos

$pdfs = @(
    "infra\uc\apresentacao-controller.pdf",
    "infra\uc\nr-01.pdf",
    "infra\uc\nr-04.pdf",
    "infra\uc\roteiro-vendas.pdf",
    "infra\uc\energia-01.pdf"
)

# =====================================================================
# 1. Pre-voo
# =====================================================================

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }

if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) {
    Abortar "rode de dentro da pasta do projeto (nao achei api\main.py em $Pasta)."
}
Set-Location $Pasta
Bom "pasta: $Pasta"

$faltando = @(($entrega + $pdfs + @("infra\semear-uc.sh")) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega e PDFs conferidos"

if (-not $SoCarga) {
    & git cat-file -e "$base^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
    & git merge-base --is-ancestor $base HEAD
    if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
    Bom "base: $base esta no HEAD"
    $git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
    $mexidos = & git diff --name-only $base HEAD -- $git_substituidos
    if ($mexidos) {
        $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
        Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
    }
    Bom "nenhum commit depois do $base mexeu nos arquivos substituidos"

    Passo "migration 028 livre..."
    $outras028 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "028_*.sql" |
        Where-Object { $_.Name -ne "028_contatos_multithreading.sql" })
    if ($outras028.Count -gt 0) {
        Abortar "ja existe outra migration 028 ($($outras028[0].Name)). Me avise para renumerar."
    }
    Bom "028 livre"
}

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para aplicar a migration nem carregar a UC."
}
Bom "porta 22 responde"

if (-not $SoCarga) {

# =====================================================================
# 2. Testes puros
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            Passo "pytest (regras de tarefa e comite, conteudo e tour da UC)..."
            & python -m pytest -q --no-cov tests\test_contato_oportunidade_regras.py tests\test_tarefa_regras.py tests\test_uc_conteudo.py tests\test_uc_tour_conteudo.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes puros falharam." }
            Bom "regras e conteudo verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 028 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 028 no RDS"

$sql    = Join-Path $Pasta "api\migrations\028_contatos_multithreading.sql"
$script = Join-Path $Pasta "infra\aplicar-028-contatos-multithreading.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 028 (aditiva, com backfill do contato principal) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/028_contatos_multithreading.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do SQL falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-028-contatos-multithreading.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-028-contatos-multithreading.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration falhou (codigo $LASTEXITCODE). Nada foi pushado." }
    Bom "migration 028 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(crm): contatos -- ABM e multithreading (entrega 045)

- Oportunidade com lista de contatos (oportunidade_contatos): papel na
  decisao, um principal espelhado em oportunidades.contato_id, farol de
  multithreading (2 a 4) no cartao, na lista e na aba Contatos.
- Contato obrigatorio em ligacao, reuniao, visita, WhatsApp e e-mail
  (criar, editar, proxima e agenda); tarefa entra no comite; reuniao e
  tarefa com o mesmo contato. GET /crm/contatos/por-alvo.
- Contato editavel no lugar: 2o telefone, WhatsApp, LinkedIn.
- Migration 028 (aditiva) + schema.sql.
- UC: aulas 10 (Account Based) e 11 (Multithreading) no 04 . Tecnicas
  do SDR na pratica.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TdwP9HqjtML3bRqWFKW4Qr
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 045 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-045.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, rode com -SoCarga." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

# =====================================================================
# 5. Espera o codigo novo
# =====================================================================

Titulo "5. Esperando o CI"

$marcador = "test -f /home/hipo/app/api/routers/crm_oportunidade_contatos.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo $marcador 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoCarga."
        exit 1
    }
    Bom "codigo novo no servidor"
}

}  # fim do if (-not $SoCarga)

# =====================================================================
# 6. Carga das trilhas da UC (aulas 10 e 11)
# =====================================================================

Titulo "6. Carga das trilhas da UC"

if ($Simular) {
    Aviso "simulacao: nao vou mandar nem carregar nada"
} else {
    Passo "enviando o script e os PDFs..."
    & ssh -i $Chave $alvo "mkdir -p /tmp/uc"
    if ($LASTEXITCODE -ne 0) { Abortar "nao consegui criar /tmp/uc no servidor." }
    & scp -i $Chave (Join-Path $Pasta "infra\semear-uc.sh") "${alvo}:/tmp/semear-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
    foreach ($p in $pdfs) {
        & scp -i $Chave (Join-Path $Pasta $p) "${alvo}:/tmp/uc/"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp de $p falhou." }
    }
    Bom "arquivos em /tmp/ no servidor"

    & ssh -t -i $Chave $alvo "bash /tmp/semear-uc.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a carga falhou (codigo $LASTEXITCODE). Rode de novo com -SoCarga depois de corrigir." }
    Bom "trilhas carregadas"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R. NAO precisa relogar (nenhuma permissao mudou).
  2. Abra uma oportunidade: aba Contatos, farol, incluir pessoa, papel.
  3. Nova tarefa do tipo Ligacao: o botao so libera com o contato.
  4. Na ficha da conta, 'Editar' no contato troca telefone sem recriar.
  5. A carga da UC lista o 04 . Tecnicas do SDR com 11 aulas.
"@ -ForegroundColor White
