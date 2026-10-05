# =====================================================================
#  HIPO -- deploy 042: proposta com varios CNPJs e tabela de preco
# =====================================================================
#
#  Pedido do Tulio (05/10/2026):
#    - cliente com varios CNPJs = UMA oportunidade. A aba Proposta lista
#      o CNPJ principal e os adicionais; adicionar um CNPJ ali o VINCULA
#      a oportunidade (oportunidade_contas)
#    - cada CNPJ com suas vidas e sua mensalidade; mensalidade da
#      proposta = soma
#    - modalidade "Tabela por faixa" (180/220/260/300 e R$ 15/vida acima
#      de 20, editavel pela gestao) ou "Valor por vida" (a de antes)
#    - arquivo consolidado (estilo do material VARIOS CNPJs) ou por CNPJ
#    - a conta de cada CNPJ mostra a oportunidade do grupo e NAO aceita
#      oportunidade propria enquanto ela estiver aberta
#  Migration 026 (aditiva), ANTES do push. O modelo .pptx muda (2 slides
#  novos) e vai no commit.
#
#    1. pre-voo      -- arquivos no lugar, base do git, 026 livre, SSH
#    2. testes       -- regras puras da proposta + conferencia do modelo
#    3. migration    -- 026 no RDS, ANTES do push
#    4. push         -- SO os arquivos da entrega
#    5. espera       -- ate o codigo novo chegar no servidor
#
#  USO
#     .\deploy-042-proposta-multi-cnpj.ps1 -Simular
#     .\deploy-042-proposta-multi-cnpj.ps1
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,

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

# Commit sobre o qual a entrega foi feita (entrega 041 no ar).
$base = "1a675d0"

$substituidos = @(
    "api\routers\crm_contas.py",
    "api\routers\crm_oportunidades.py",
    "api\routers\crm_propostas.py",
    "api\routers\crm_prospeccao.py",
    "api\schema.sql",
    "api\scripts\conferir_modelo_proposta.py",
    "api\scripts\uc_conteudo_hipo.py",
    "api\services\atividade.py",
    "api\services\proposta.py",
    "api\services\proposta_render.py",
    "api\templates\proposta_modelo.pptx",
    "api\tests\test_proposta_regras.py",
    "web\src\components\crm\AbaProposta.jsx",
    "web\src\components\crm\ContaDetalhe.jsx",
    "web\src\components\crm\KanbanOportunidades.jsx",
    "web\src\components\crm\OportunidadeDetalhe.jsx",
    "web\src\tests\AbaProposta.test.jsx",
    "web\src\tests\ContaDetalhe.test.jsx",
    "web\src\tests\Oportunidades.test.jsx"
)

$novos = @(
    "api\migrations\026_proposta_multi_cnpj.sql",
    "api\scripts\gerar_modelo_proposta_tabela.py",
    "api\tests\test_crm_proposta_multi_cnpj.py",
    "web\src\components\crm\TabelaPrecos.jsx",
    "web\src\components\crm\propostaCalculo.js",
    "infra\aplicar-026-proposta-multi-cnpj.sh",
    "deploy-042-proposta-multi-cnpj.ps1"
)

$entrega = $substituidos + $novos

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

$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega conferidos"

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

Passo "migration 026 livre..."
$outras026 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "026_*.sql" |
    Where-Object { $_.Name -ne "026_proposta_multi_cnpj.sql" })
if ($outras026.Count -gt 0) {
    Abortar "ja existe outra migration 026 ($($outras026[0].Name)). Me avise para renumerar."
}
Bom "026 livre"

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\liberar-meu-ip-ssh.ps1 (sem -LimparAntigos)" -ForegroundColor Gray
    Abortar "sem SSH nao da para aplicar a migration."
}
Bom "porta 22 responde"

# =====================================================================
# 2. Testes puros da proposta e conferencia do modelo
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
            Passo "pytest (regras puras da proposta)..."
            & python -m pytest -q --no-cov tests\test_proposta_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes das regras da proposta falharam." }
            Passo "conferencia do modelo .pptx (as duas modalidades)..."
            & python -m scripts.conferir_modelo_proposta
            if ($LASTEXITCODE -ne 0) { Abortar "o modelo da proposta nao passou na conferencia." }
            Bom "regras e modelo verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

# =====================================================================
# 3. Migration 026 no RDS (antes do push)
# =====================================================================

Titulo "3. Migration 026 no RDS"

$sql    = Join-Path $Pasta "api\migrations\026_proposta_multi_cnpj.sql"
$script = Join-Path $Pasta "infra\aplicar-026-proposta-multi-cnpj.sh"

if ($Simular) {
    Aviso "simulacao: nao vou aplicar a migration"
} else {
    Confirmar "Aplicar a migration 026 (3 tabelas novas, aditiva) em PRODUCAO ($Servidor)?"
    & scp -i $Chave $sql "${alvo}:/tmp/026_proposta_multi_cnpj.sql"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da migration falhou." }
    & scp -i $Chave $script "${alvo}:/tmp/aplicar-026-proposta-multi-cnpj.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp do script da migration falhou." }
    & ssh -t -i $Chave $alvo "bash /tmp/aplicar-026-proposta-multi-cnpj.sh"
    if ($LASTEXITCODE -ne 0) { Abortar "a migration 026 falhou no servidor (codigo $LASTEXITCODE)." }
    Bom "migration 026 aplicada"
}

# =====================================================================
# 4. Push
# =====================================================================

Titulo "4. Push"

$mensagem = @"
feat(propostas): varios CNPJs na mesma oportunidade e tabela de preco

- oportunidade_contas: CNPJs adicionais da oportunidade. A aba Proposta
  vincula e desvincula; a conta de cada CNPJ mostra a oportunidade do
  grupo (aviso + coluna Vinculo + historico) e nao aceita oportunidade
  propria enquanto a do grupo estiver aberta (409 apontando a outra).
- proposta_itens: um item por CNPJ, com vidas e mensalidade; mensalidade
  da proposta = soma. Modalidades: tabela por faixa (sugere, negocia,
  mostra desconto) e valor por vida.
- tabela_preco_faixas: tabela editavel pela gestao (/crm/tabela-precos);
  cada proposta guarda a copia da tabela usada.
- Modelo .pptx com os slides da tabela (do material VARIOS CNPJs);
  download consolidado ou por CNPJ (?item=). Lista encolhe a fonte
  quando passa da caixa.
- Busca do funil e prospeccao enxergam os CNPJs adicionais.
- Migration 026 (aditiva; backfill de 1 item por proposta antiga).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CDPWboU41EfBiKCaZHSU5R
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 042 e dar push na main?"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-042.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
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

$marcador = "grep -q TABELA_PADRAO /home/hipo/app/api/services/proposta.py"
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
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."
        exit 1
    }
    Bom "codigo novo no servidor"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R no navegador. NAO precisa relogar (nenhuma permissao mudou).
  2. Oportunidade > aba Proposta: modalidade "Tabela por faixa", lista
     "CNPJs da proposta" com o principal, e "Adicionar CNPJ do mesmo
     cliente". Adicione um CNPJ e abra a conta dele: aviso azul no topo
     com o numero da oportunidade.
  3. Gere com 2+ CNPJs: o PPTX consolidado sai com a tabela de precos e
     uma linha por CNPJ; em "Proposta por CNPJ" cada um baixa o seu.
  4. Franqueado/ADM: "Editar" na Tabela de precos.
  5. A aula "Proposta e fechamento" da UC foi atualizada no codigo. Para
     ela chegar na tela: .\deploy-041-uc-quiz-trilha.ps1 -SoCarga
"@ -ForegroundColor White
