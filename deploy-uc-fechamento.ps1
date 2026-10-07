# =====================================================================
# HIPO - deploy: UC "06 . Fechamento" (os tres 10 + tecnicas de
# fechamento) e botao "Guia do roteiro" dentro da reuniao da Agenda.
#
# Rodar da raiz do projeto, no PowerShell:
#   cd "C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0"
#   powershell -ExecutionPolicy Bypass -File .\deploy-uc-fechamento.ps1
#
# Sem migration. O que faz, nesta ordem:
#   1. confere que os arquivos da entrega estao no lugar
#   2. roda os testes puros do conteudo (sem banco) aqui no Windows
#   3. commit SO dos arquivos da entrega (o resto fica de fora)
#   4. push -> CI roda testes e deploy
#   5. espera voce confirmar o CI verde
#   6. carga da trilha nova na EC2 (infra/semear-uc.sh, com --atualizar)
#
# Sem "exit" de proposito: fechar o terminal no meio seria pior.
# =====================================================================

$ErrorActionPreference = "Stop"
$EC2   = "ec2-user@35.156.111.168"
$CHAVE = "$HOME\Downloads\chave-hipo.pem"
$ok = $true

function Pergunta($texto) {
    $r = Read-Host "$texto [s/N]"
    return ($r -eq "s" -or $r -eq "S")
}

# ---------------------------------------------------------------- 1
$meus = @(
    "api/scripts/uc_conteudo_fechamento.py",
    "api/scripts/uc_conteudo.py",
    "api/services/roteiro_scorecard.py",
    "api/routers/crm_avaliacao.py",
    "api/tests/test_uc_conteudo.py",
    "api/tests/test_avaliacao_roteiro.py",
    "api/tests/test_crm_avaliacao.py",
    "web/src/components/crm/GuiaRoteiro.jsx",
    "web/src/components/crm/ModalReuniao.jsx",
    "web/src/tests/GuiaRoteiro.test.jsx",
    "web/src/tests/ModalReuniao.test.jsx",
    "deploy-uc-fechamento.ps1"
)
$faltando = $meus | Where-Object { -not (Test-Path $_) }
if ($faltando) {
    Write-Host "[1] ERRO: faltam arquivos:" -ForegroundColor Red
    $faltando | ForEach-Object { Write-Host "    $_" }
    $ok = $false
} else {
    Write-Host "[1] os $($meus.Count) arquivos estao no lugar" -ForegroundColor Green
}

# ---------------------------------------------------------------- 2
if ($ok) {
    Write-Host "[2] testes puros do conteudo e do guia (sem banco)..." -ForegroundColor Cyan
    Push-Location api
    $env:PYTHONPATH = (Get-Location).Path
    $py = "python"
    if (Test-Path "venv\Scripts\python.exe") { $py = "venv\Scripts\python.exe" }
    & $py -m pytest -q -o addopts="" tests/test_uc_conteudo.py tests/test_avaliacao_roteiro.py
    $codigo = $LASTEXITCODE
    Pop-Location
    if ($codigo -ne 0) {
        Write-Host "[2] testes falharam - nada foi commitado." -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host "[2] verde" -ForegroundColor Green
    }
}

# ---------------------------------------------------------------- 3/4
if ($ok) {
    git add -- $meus

    $outros = git status --porcelain | Where-Object { $_ -notmatch '^[AMDR] ' } |
              ForEach-Object { $_.Substring(3) } |
              Where-Object { $_ -notmatch '__pycache__|\.pytest_cache|venv/|node_modules|dist/' }
    if ($outros) {
        Write-Host ""
        Write-Host "[3] Ha outras mudancas FORA desta entrega (ficam fora do commit):" -ForegroundColor Yellow
        $outros | ForEach-Object { Write-Host "    $_" }
    }

    Write-Host ""
    Write-Host "[3] Vai no commit:" -ForegroundColor Cyan
    git diff --cached --stat
    if (Pergunta "Confirmar commit e push?") {
        $msg = @(
            "UC 06 Fechamento (tres 10 + tecnicas) e Guia do roteiro na reuniao",
            "",
            "- trilha 06 . Fechamento: os tres 10 e como pedir o sim (Tecnica,",
            "  obrigatoria EV e EC, prazo 52 dias, 7 aulas com exercicio e role-play)",
            "- GET /crm/agenda/roteiro/guia: o script resumido do scorecard, com",
            "  falas de exemplo, os tres 10 e as tecnicas de fechamento",
            "- botao Guia do roteiro na reuniao com cliente (Agenda e Tarefas)",
            "",
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
            "Claude-Session: https://claude.ai/code/session_01T7M8u28wj4hqeUfVTheypc"
        ) -join "`n"
        $tmp = New-TemporaryFile
        [System.IO.File]::WriteAllText($tmp.FullName, $msg, (New-Object System.Text.UTF8Encoding($false)))
        git commit -F $tmp.FullName
        Remove-Item $tmp.FullName
        git push
        Write-Host "[4] push feito. Acompanhe: https://github.com/tuliohorta77/Hipo-Web/actions" -ForegroundColor Green
    } else {
        Write-Host "    cancelado - nada foi commitado (os arquivos seguem no stage)" -ForegroundColor Yellow
        $ok = $false
    }
}

# ---------------------------------------------------------------- 5/6
if ($ok) {
    Write-Host ""
    Write-Host "[5] Espere os 3 jobs ficarem verdes (~3 min)." -ForegroundColor Cyan
    if (Pergunta "    CI verde e deploy concluido?") {
        Write-Host "[6] carga da trilha na EC2 (ensaio e depois grava; o script pergunta)..." -ForegroundColor Cyan
        scp -i $CHAVE infra/semear-uc.sh "${EC2}:/tmp/"
        ssh -t -i $CHAVE $EC2 "bash /tmp/semear-uc.sh"
        Write-Host ""
        Write-Host "    Confira: UC > Outras / Minha UC (EV e EC veem a 06 como obrigatoria)." -ForegroundColor Green
        Write-Host "    Agenda > abrir uma reuniao com cliente > botao 'Guia do roteiro'." -ForegroundColor Green
        Write-Host "    Ctrl+Shift+R antes de testar." -ForegroundColor DarkGray
    } else {
        Write-Host "    Quando o CI ficar verde, rode so a carga:" -ForegroundColor Yellow
        Write-Host "    scp -i $CHAVE infra/semear-uc.sh ${EC2}:/tmp/"
        Write-Host "    ssh -t -i $CHAVE $EC2 bash /tmp/semear-uc.sh"
    }
}
