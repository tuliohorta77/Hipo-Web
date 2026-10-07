# =====================================================================
# HIPO - deploy da entrega 032 (limite de login + Sentry + trilha LGPD)
#
# Rodar da raiz do projeto, no PowerShell:
#   cd "C:\Users\tulio\Documents\APP - hipo\Hipo - v1.4.0"
#   powershell -ExecutionPolicy Bypass -File .\deploy-032.ps1
#
# O que faz, nesta ordem:
#   1. apaga a copia velha 031_seguranca_login_auditoria.sql
#   2. confere que os arquivos da 032 estao no lugar
#   3. commit SO dos arquivos da 032 (pergunta antes de levar o resto)
#   4. push -> CI roda testes, migrations e deploy
#   5. espera voce confirmar o CI verde
#   6. instala o sentry-sdk na EC2 e grava o SENTRY_DSN no .env
#
# Sem "exit" de proposito: fechar o terminal no meio seria pior.
# =====================================================================

$ErrorActionPreference = "Stop"
$EC2  = "ec2-user@35.156.111.168"
$CHAVE = "$HOME\Downloads\chave-hipo.pem"
$ok = $true

function Pergunta($texto) {
    $r = Read-Host "$texto [s/N]"
    return ($r -eq "s" -or $r -eq "S")
}

# ---------------------------------------------------------------- 1
$velha = "api\migrations\031_seguranca_login_auditoria.sql"
if (Test-Path $velha) {
    Remove-Item $velha
    Write-Host "[1] removida a copia velha: $velha" -ForegroundColor Green
} else {
    Write-Host "[1] copia velha ja nao existe" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- 2
$meus = @(
    "api/.env.template",
    "api/config.py",
    "api/main.py",
    "api/requirements.txt",
    "api/schema.sql",
    "api/migrations/032_seguranca_login_auditoria.sql",
    "api/routers/auth.py",
    "api/routers/crm_contatos.py",
    "api/routers/crm_enriquecimento.py",
    "api/routers/crm_oportunidade_contatos.py",
    "api/routers/telemetria.py",
    "api/scripts/fechamento_diario.py",
    "api/services/auditoria.py",
    "api/services/login_limite.py",
    "api/services/observabilidade.py",
    "api/tests/conftest.py",
    "api/tests/test_auditoria_leitura.py",
    "api/tests/test_observabilidade.py",
    "api/tests/test_seguranca_login.py",
    "infra/instalar-sentry.sh"
)
$faltando = $meus | Where-Object { -not (Test-Path $_) }
if ($faltando) {
    Write-Host "[2] ERRO: faltam arquivos da 032:" -ForegroundColor Red
    $faltando | ForEach-Object { Write-Host "    $_" }
    $ok = $false
} else {
    Write-Host "[2] os $($meus.Count) arquivos da 032 estao no lugar" -ForegroundColor Green
}

# Duas migrations com o mesmo numero travam o aplicar_migrations.
if ($ok) {
    $nums = Get-ChildItem "api\migrations\*.sql" | ForEach-Object { $_.Name.Substring(0,3) }
    $dup = $nums | Group-Object | Where-Object { $_.Count -gt 1 }
    if ($dup) {
        Write-Host "[2] ERRO: numero de migration repetido: $($dup.Name -join ', ')" -ForegroundColor Red
        $ok = $false
    }
}

# ---------------------------------------------------------------- 3
if ($ok) {
    git add -- $meus

    # O que mais esta modificado e NAO e da 032 (ex.: a entrega 031 de
    # e-mail -> tarefa, que estava sendo feita em paralelo).
    $outros = git status --porcelain | Where-Object { $_ -notmatch '^[AMDR] ' } |
              ForEach-Object { $_.Substring(3) } |
              Where-Object { $_ -notmatch '__pycache__|\.pytest_cache|venv/' }
    if ($outros) {
        Write-Host ""
        Write-Host "[3] Tambem ha mudancas FORA da 032:" -ForegroundColor Yellow
        $outros | ForEach-Object { Write-Host "    $_" }
        Write-Host "    ATENCAO: o schema.sql ja leva a coluna emails_enviados.tarefa_id da 031."
        Write-Host "    Se a 031 nao for junto, o CI so da um WARNING de schema.sql (nao falha)."
        if (Pergunta "    Levar essas mudancas no mesmo commit?") {
            git add -A
            Write-Host "    incluidas" -ForegroundColor Green
        } else {
            Write-Host "    ficam fora deste commit" -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    Write-Host "[3] Vai no commit:" -ForegroundColor Cyan
    git diff --cached --stat
    if (Pergunta "Confirmar commit e push?") {
        $msg = @(
            "032: limite de tentativas no login, Sentry e trilha de leitura de dado pessoal",
            "",
            "- login_tentativas: 5 falhas por e-mail / 20 por IP em 15 min -> 429",
            "- Sentry opcional (SENTRY_DSN), sem PII; /health mostra o estado",
            "- leituras_sensiveis: quem leu contato/socio; GET /telemetria/leituras-sensiveis e /telemetria/logins",
            "",
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
            "Claude-Session: https://claude.ai/code/session_01TJ4m7GYpzfhJ83AvhaKPHd"
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
    Write-Host "    O SENTRY_DSN NAO pode entrar no .env antes do deploy (extra=forbid derruba a API)."
    if (Pergunta "    CI verde e deploy concluido?") {
        Write-Host "[6] instalando sentry-sdk na EC2..." -ForegroundColor Cyan
        scp -i $CHAVE infra/instalar-sentry.sh infra/por-chave-no-env.sh "${EC2}:/tmp/"
        ssh -t -i $CHAVE $EC2 "bash /tmp/instalar-sentry.sh"

        Write-Host ""
        Write-Host "    Agora o DSN (sentry.io > projeto hipo-api > Settings > Client Keys)."
        Write-Host "    O script pergunta o valor sem mostrar e reinicia a API."
        if (Pergunta "    Ja tem o DSN em maos?") {
            ssh -t -i $CHAVE $EC2 "bash /tmp/por-chave-no-env.sh SENTRY_DSN"
            Write-Host ""
            Write-Host "    Conferindo /health (esperado: sentry true):" -ForegroundColor Cyan
            ssh -i $CHAVE $EC2 "curl -s http://localhost:8001/health"
        } else {
            Write-Host "    Depois, rode:" -ForegroundColor Yellow
            Write-Host "    ssh -t -i $CHAVE $EC2 bash /tmp/por-chave-no-env.sh SENTRY_DSN"
        }
    } else {
        Write-Host "    Quando o CI ficar verde, rode de novo so a parte da EC2:" -ForegroundColor Yellow
        Write-Host "    scp -i $CHAVE infra/instalar-sentry.sh infra/por-chave-no-env.sh ${EC2}:/tmp/"
        Write-Host "    ssh -t -i $CHAVE $EC2 bash /tmp/instalar-sentry.sh"
        Write-Host "    ssh -t -i $CHAVE $EC2 bash /tmp/por-chave-no-env.sh SENTRY_DSN"
    }
}

Write-Host ""
Write-Host "Teste rapido do limite (deve dar 429 na 6a):" -ForegroundColor DarkGray
Write-Host "  1..6 | % { curl.exe -s -o NUL -w '%{http_code} ' -d 'username=teste@x.com&password=x' https://hipogestao.com.br/api/auth/login }" -ForegroundColor DarkGray
