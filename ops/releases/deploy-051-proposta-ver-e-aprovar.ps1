# =====================================================================
#  HIPO -- deploy 051: proposta sem tabela, excedente, ver e aprovar
# =====================================================================
#
#  Pedido do Tulio (07/10/2026):
#    * A tabela de preco NAO vai mais para o cliente. Cada CNPJ aparece
#      com a faixa ("16 a 20 vidas - Mensalidade R$ 300,00") e a frase
#      "Mensalidade total para os N CNPJs - R$ X". O slide da tabela saiu
#      do modelo .pptx.
#    * Campo "Valor por vida excedente" (modalidade tabela), sugerido pela
#      tabela; sai no rodape da proposta.
#    * Visualizador da proposta dentro do HIPO + botao "Aprovar para
#      envio". Gerar abre o visualizador. So proposta aprovada vai anexada
#      na aba E-mails (o servidor recusa as outras).
#    * Titulo do arquivo PDF/PPTX corrigido: o modelo levava o titulo de
#      outra proposta ("SOLAR DOS PAMPAS") para todo cliente.
#    * Migration 033 (aditiva): valor_vida_excedente, aprovada_em,
#      aprovada_por. Propostas que ja existem entram APROVADAS (eram
#      conferidas fora do HIPO), para o e-mail continuar anexando.
#
#    1. pre-voo   -- arquivos, base do git, 033 livre
#    2. testes    -- regras puras + conferencia do modelo .pptx
#    3. push      -- SO os arquivos da entrega (o CI aplica a 033)
#    4. espera    -- ate o codigo novo chegar no servidor
#
#  USO (da raiz do repositorio):
#     .\ops\releases\deploy-051-proposta-ver-e-aprovar.ps1 -Simular
#     .\ops\releases\deploy-051-proposta-ver-e-aprovar.ps1
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
Set-Location $Pasta

# Commit sobre o qual a entrega foi feita (032 + CI trust, 07/10/2026).
$base = "6e965ee"

$substituidos = @(
    "api\routers\crm_emails.py",
    "api\routers\crm_propostas.py",
    "api\schema.sql",
    "api\scripts\conferir_modelo_proposta.py",
    "api\scripts\gerar_modelo_proposta_tabela.py",
    "api\scripts\uc_conteudo_hipo.py",
    "api\services\atividade.py",
    "api\services\proposta.py",
    "api\services\proposta_render.py",
    "api\templates\proposta_modelo.pptx",
    "api\tests\test_crm_emails.py",
    "api\tests\test_crm_proposta_multi_cnpj.py",
    "api\tests\test_proposta_regras.py",
    "web\src\components\crm\AbaEmails.jsx",
    "web\src\components\crm\AbaProposta.jsx",
    "web\src\tests\AbaEmails.test.jsx",
    "web\src\tests\AbaProposta.test.jsx"
)
$novos = @(
    "api\migrations\033_proposta_aprovacao_excedente.sql",
    "web\src\components\crm\VisualizadorProposta.jsx",
    "ops\releases\deploy-051-proposta-ver-e-aprovar.ps1"
)
$entrega = $substituidos + $novos

Titulo "1. Pre-voo"
if ($Simular) { Aviso "MODO SIMULACAO -- nada sera alterado" }
if (-not (Test-Path (Join-Path $Pasta "api\main.py"))) { Abortar "rode da raiz do repositorio." }
$faltando = @($entrega | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "$($entrega.Count) arquivos da entrega presentes"
$ramo = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne "main") { Abortar "voce esta no ramo '$ramo', nao na main." }
& git cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { Abortar "o commit $base nao esta no git daqui. Rode 'git pull'." }
& git merge-base --is-ancestor $base HEAD
if ($LASTEXITCODE -ne 0) { Abortar "o HEAD daqui nao contem o $base. Rode 'git pull'." }
$git_substituidos = $substituidos | ForEach-Object { $_.Replace("\", "/") }
$mexidos = & git diff --name-only $base HEAD -- $git_substituidos
if ($mexidos) {
    $mexidos | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Abortar "commits depois do $base mexeram em arquivos que a entrega substitui. Me mande os atuais."
}
Bom "base $base no HEAD, arquivos substituidos intactos"
$outras033 = @(Get-ChildItem (Join-Path $Pasta "api\migrations") -Filter "033_*.sql" |
    Where-Object { $_.Name -ne "033_proposta_aprovacao_excedente.sql" })
if ($outras033.Count -gt 0) { Abortar "ja existe outra migration 033 ($($outras033[0].Name)). Me avise para renumerar." }
Bom "033 livre"

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            & python -m pytest -q --no-cov tests\test_proposta_regras.py
            if ($LASTEXITCODE -ne 0) { Abortar "testes das regras da proposta falharam." }
            & python -m scripts.conferir_modelo_proposta
            if ($LASTEXITCODE -ne 0) { Abortar "o modelo da proposta nao passou na conferencia." }
            Bom "regras e modelo verdes"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes ficam so com o CI"
    }
}

Titulo "3. Push"
$mensagem = @"
feat(propostas): faixa no lugar da tabela, excedente, ver e aprovar (entrega 051)

- A tabela de preco nao vai mais para o cliente: o slide saiu do modelo;
  cada CNPJ mostra a faixa ("16 a 20 vidas - Mensalidade R$ 300,00") e a
  mensalidade sai como "Mensalidade total para os N CNPJs - R$ X".
- Valor por vida excedente (modalidade tabela), sugerido pela faixa
  aberta da tabela, no rodape da proposta.
- Visualizador da proposta (PDF na tela, consolidada ou por CNPJ) e
  aprovacao do EV (POST /crm/propostas/{id}/aprovar). Gerar abre o
  visualizador. So proposta aprovada vai anexada no e-mail (422 no
  servidor, filtro na aba E-mails).
- Titulo/autor do arquivo vem do cliente e do executivo (o modelo
  carregava o titulo de outra proposta).
- Migration 033 (aditiva): valor_vida_excedente, aprovada_em,
  aprovada_por; propostas existentes entram aprovadas.
- Aula "Proposta e fechamento" da UC atualizada.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CDPWboU41EfBiKCaZHSU5R
"@
if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    Confirmar "Commitar a entrega 051 e dar push na main? (o CI aplica a 033)"
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-051.txt"
    Set-Content -Path $tmpMsg -Value $mensagem -Encoding UTF8
    & git commit -F $tmpMsg
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?)." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui"
}

Titulo "4. Esperando o CI"
$marcador = "grep -q rotulo_faixa /home/hipo/app/api/services/proposta.py"
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
    if (-not $chegou) { Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions."; exit 1 }
    Bom "codigo novo no servidor"
}

Titulo "Pronto"
Write-Host @"
  1. Ctrl+Shift+R. NAO precisa relogar.
  2. Oportunidade > Proposta: campo "Valor por vida excedente" (vem com
     R$ 15,00). Gere: a proposta abre na tela. Confira e clique em
     "Aprovar para envio".
  3. No arquivo: sem slide de tabela; cada CNPJ com a faixa; "Mensalidade
     total para os N CNPJs"; rodape com o excedente.
  4. Aba E-mails: so aparecem versoes aprovadas. As propostas antigas ja
     entram aprovadas.
  5. Aula da UC atualizada no codigo. Para publicar:
     .\ops\releases\deploy-041-uc-quiz-trilha.ps1 -SoCarga
"@ -ForegroundColor White
