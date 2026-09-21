<#
    HIPO - deploy 017: enriquecimento cadastral por CNPJ (migration 014)
    ====================================================================

    Orquestra a subida inteira, na ORDEM OBRIGATORIA, que existe porque esta
    entrega tem migration:

        1. copia os arquivos para o repo (com backup do que for sobrescrito)
        2. testes locais
        3. MIGRATION no RDS de producao
        4. .env da EC2 (as variaveis novas)
        5. git push  ->  o CI faz rsync e reinicia
        6. conferencia no ar

    Invertendo 3 e 5, o codigo novo sobe pedindo coluna que nao existe e a
    API responde 500 em /crm/contas ate a migration rodar.

    A migration e ADITIVA e IDEMPOTENTE: nenhum DROP, nenhum DELETE, e rodar
    duas vezes nao faz nada na segunda. Por isso ela NAO exige export previo
    em CSV -- essa regra vale para migration destrutiva, e esta nao e.

    COMO RODAR

    Da RAIZ do repo (a pasta que tem api\ e web\). Primeiro sem tocar em
    nada, so para ver o plano:

        .\deploy-017-enriquecimento.ps1 -DryRun

    Depois, para valer:

        .\deploy-017-enriquecimento.ps1

    UMA LINHA POR VEZ. Colar as duas juntas no PowerShell executa as duas
    em sequencia -- o comentario depois do comando nao impede nada.

    Se os arquivos da 014 JA ESTAO no repo, o script confere e segue; nao
    e preciso ter a pasta de entrega. Se voce preferir subir a partir do
    zip extraido, aponte para ele:

        .\deploy-017-enriquecimento.ps1 -Entrega ..\hipo-014-enriquecimento

    Flags uteis:
        -PularTestes     pula pytest/vitest/build (nao recomendado)
        -PularMigration  quando a 014 ja foi aplicada
        -PularEnv        quando o .env ja tem as variaveis
        -PularPush       faz tudo menos o push (voce commita a mao)

    SOBRE A CHAVE DA LEADCNPJ

    Passe em -LeadCnpjApiKey, ou deixe em branco e o script pergunta (com a
    digitacao oculta). Ela viaja para a EC2 em base64 -- PowerShell 5.1
    REMOVE aspas duplas ao montar a linha de comando de um programa externo,
    e uma chave com caractere especial chegaria picada do outro lado. Foi
    exatamente o que aconteceu com --finder-razao na carga da Oraculus.

    Sem chave, a BrasilAPI responde sozinha: tudo funciona, menos o numero
    de funcionarios (a Receita nao publica isso).

    Sem acentos de proposito: comentario acentuado embaralha ao ser colado
    no terminal, e este arquivo vai ser lido no meio de um deploy.
#>

[CmdletBinding()]
param(
    [string] $Entrega = "..\hipo-014-enriquecimento",
    [string] $Servidor = "63.179.88.212",
    [string] $Usuario = "ec2-user",
    [string] $ChaveSsh = "$HOME\Downloads\chave-hipo.pem",
    [string] $LeadCnpjApiKey = "",
    [string] $Branch = "main",
    [switch] $PularTestes,
    [switch] $PularMigration,
    [switch] $PularEnv,
    [switch] $PularPush,
    [switch] $DryRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$inicio = Get-Date
$carimbo = $inicio.ToString("yyyyMMdd-HHmmss")
$passo = 0

function Titulo([string] $texto) {
    $script:passo++
    Write-Host ""
    Write-Host ("=" * 64) -ForegroundColor DarkCyan
    Write-Host (" PASSO {0} - {1}" -f $script:passo, $texto) -ForegroundColor Cyan
    Write-Host ("=" * 64) -ForegroundColor DarkCyan
}

function Ok([string] $t)    { Write-Host "  [ok]   $t" -ForegroundColor Green }
function Aviso([string] $t) { Write-Host "  [!]    $t" -ForegroundColor Yellow }
function Erro([string] $t)  { Write-Host "  [ERRO] $t" -ForegroundColor Red }
function Nota([string] $t)  { Write-Host "         $t" -ForegroundColor DarkGray }

function Abortar([string] $motivo) {
    Erro $motivo
    Write-Host ""
    Write-Host "Deploy interrompido. Nada foi enviado para producao a partir deste ponto." -ForegroundColor Red
    exit 1
}

# Roda um executavel externo e aborta se o codigo de saida nao for 0.
# Existe porque $ErrorActionPreference NAO pega exit code de .exe -- so de
# cmdlet. Sem isto, um pytest vermelho passaria batido e o push aconteceria.
function Executar([string] $programa, [string[]] $argumentos, [string] $oque) {
    Nota "$programa $($argumentos -join ' ')"
    if ($DryRun) { Aviso "(dry-run) nao executado"; return }
    & $programa @argumentos
    if ($LASTEXITCODE -ne 0) {
        Abortar "$oque falhou (codigo $LASTEXITCODE)."
    }
}

# Comando remoto via ssh. O script inteiro vai em base64 pelo mesmo motivo
# da chave: nada de quoting atravessando PowerShell -> ssh -> bash.
function RemotoBash([string] $script, [string] $oque, [switch] $Interativo) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($script)
    $b64 = [Convert]::ToBase64String($bytes)
    $cmd = "echo $b64 | base64 -d | bash"
    if ($DryRun) { Aviso "(dry-run) remoto: $oque"; return "" }

    if ($Interativo) {
        & ssh -t -i $ChaveSsh "$Usuario@$Servidor" $cmd
    } else {
        $saida = & ssh -i $ChaveSsh "$Usuario@$Servidor" $cmd
        if ($LASTEXITCODE -ne 0) { Abortar "$oque falhou no servidor (codigo $LASTEXITCODE)." }
        return $saida
    }
    if ($LASTEXITCODE -ne 0) { Abortar "$oque falhou no servidor (codigo $LASTEXITCODE)." }
    return ""
}

Write-Host ""
Write-Host "HIPO - deploy 017: enriquecimento cadastral por CNPJ" -ForegroundColor White
Write-Host "$($inicio.ToString('dd/MM/yyyy HH:mm:ss'))" -ForegroundColor DarkGray
if ($DryRun) {
    Write-Host ""
    Write-Host " MODO DRY-RUN: mostra o plano e nao altera nada." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
Titulo "Pre-requisitos"
# ---------------------------------------------------------------------------

if (-not (Test-Path (Join-Path "api" "main.py")) -or
    -not (Test-Path (Join-Path "web" "package.json"))) {
    Abortar "Rode da RAIZ do repo (a pasta que tem api\ e web\). Estou em: $(Get-Location)"
}
Ok "raiz do repo"

# Os arquivos que esta entrega precisa ter no repo. A lista existe para o
# script poder trabalhar nos dois casos: com a pasta de entrega ao lado (ele
# copia) ou sem ela (os arquivos ja foram colocados no lugar, e aqui ele so
# confere). Exigir a origem quando o destino ja esta certo seria burocracia.
$ARQUIVOS_ESPERADOS = @(
    "api\migrations\014_enriquecimento.sql",
    "api\services\enriquecimento\__init__.py",
    "api\services\enriquecimento\modelo.py",
    "api\services\enriquecimento\fontes.py",
    "api\services\enriquecimento\persistencia.py",
    "api\routers\crm_enriquecimento.py",
    "api\routers\crm_contas.py",
    "api\services\atividade.py",
    "api\main.py",
    "api\config.py",
    "api\schema.sql",
    "api\.env.template",
    "api\scripts\amostrar_enriquecimento.py",
    "api\tests\test_enriquecimento_modelo.py",
    "api\tests\test_crm_enriquecimento.py",
    "infra\aplicar-014-enriquecimento.sh",
    "web\src\components\crm\AbaDadosPublicos.jsx",
    "web\src\components\crm\ContaDetalhe.jsx",
    "web\src\pages\crm\Contas.jsx",
    "web\src\tests\AbaDadosPublicos.test.jsx",
    "web\src\tests\Contas.test.jsx"
)

$TemEntrega = Test-Path $Entrega
if ($TemEntrega) {
    $Entrega = (Resolve-Path $Entrega).Path
    Ok "entrega: $Entrega"
} else {
    # Sem a pasta de origem, os arquivos precisam ja estar no repo.
    $faltando = @()
    foreach ($rel in $ARQUIVOS_ESPERADOS) {
        if (-not (Test-Path (Join-Path (Get-Location) $rel))) { $faltando += $rel }
    }
    if ($faltando.Count -gt 0) {
        Erro "A pasta da entrega nao existe ($Entrega) e faltam arquivos no repo:"
        $faltando | ForEach-Object { Nota "  $_" }
        Abortar "Extraia o hipo-014-enriquecimento.zip e aponte -Entrega para a pasta."
    }
    Ok "arquivos da 014 ja estao no repo ($($ARQUIVOS_ESPERADOS.Count) conferidos)"
    Nota "sem pasta de entrega -- o passo de copia vai ser pulado"
}

if (-not (Test-Path $ChaveSsh)) {
    Abortar "Chave SSH nao encontrada: $ChaveSsh"
}
Ok "chave ssh"

foreach ($p in @("git", "ssh", "scp")) {
    if (-not (Get-Command $p -ErrorAction SilentlyContinue)) {
        Abortar "'$p' nao esta no PATH."
    }
}
Ok "git, ssh e scp no PATH"

# Branch e arvore limpa: commit no meio de uma arvore suja mistura esta
# entrega com o que ja estava mexido.
$branchAtual = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($branchAtual -ne $Branch) {
    Aviso "voce esta em '$branchAtual', nao em '$Branch'"
    $r = Read-Host "  Continuar mesmo assim? [s/N]"
    if ($r -ne "s" -and $r -ne "S") { Abortar "Cancelado." }
}
Ok "branch: $branchAtual"

$sujo = & git status --porcelain
if ($sujo -and -not $DryRun) {
    Aviso "a arvore tem alteracoes nao commitadas:"
    $sujo | Select-Object -First 10 | ForEach-Object { Nota $_ }
    $r = Read-Host "  O commit desta entrega vai levar isso junto. Continuar? [s/N]"
    if ($r -ne "s" -and $r -ne "S") { Abortar "Cancelado." }
}

# Janela de SSH: o security group costuma liberar so um IP por vez.
if (Test-Path ".\liberar-meu-ip-ssh.ps1") {
    Nota "dica: se o ssh travar, rode .\liberar-meu-ip-ssh.ps1 antes"
}

# ---------------------------------------------------------------------------
Titulo "Copiando os arquivos (com backup)"
# ---------------------------------------------------------------------------

$backup = "_backup-014-$carimbo"
$copiados = 0
$sobrescritos = 0

# -Force: sem ele o .env.template (e qualquer outro arquivo que comece com
# ponto) ficaria de fora da copia em silencio.
$arquivos = if ($TemEntrega) {
    Get-ChildItem -Path $Entrega -Recurse -File -Force
} else {
    @()
}

if (-not $TemEntrega) {
    Aviso "pulado: os arquivos ja estao no repo e foram conferidos no passo 1"
    Nota "nada a copiar, nada a fazer backup"
}

foreach ($arq in $arquivos) {
    $relativo = $arq.FullName.Substring($Entrega.Length).TrimStart("\", "/")
    $destino = Join-Path (Get-Location) $relativo

    if (Test-Path $destino) {
        $destBackup = Join-Path $backup $relativo
        $pastaBackup = Split-Path $destBackup -Parent
        if (-not $DryRun) {
            New-Item -ItemType Directory -Force -Path $pastaBackup | Out-Null
            Copy-Item $destino $destBackup -Force
        }
        $sobrescritos++
        Write-Host "  ~ $relativo" -ForegroundColor Yellow
    } else {
        Write-Host "  + $relativo" -ForegroundColor Green
    }

    if (-not $DryRun) {
        $pastaDestino = Split-Path $destino -Parent
        New-Item -ItemType Directory -Force -Path $pastaDestino | Out-Null
        Copy-Item $arq.FullName $destino -Force
    }
    $copiados++
}

if ($TemEntrega) {
    Ok "$copiados arquivo(s): $sobrescritos sobrescrito(s), $($copiados - $sobrescritos) novo(s)"
    if ($sobrescritos -gt 0 -and -not $DryRun) {
        Nota "backup do que foi sobrescrito em .\$backup"
    }
}

# ---------------------------------------------------------------------------
Titulo "Testes"
# ---------------------------------------------------------------------------

if ($PularTestes) {
    Aviso "pulados por -PularTestes"
} else {
    # PYTEST LOCAL SO RODA O QUE NAO PRECISA DE POSTGRES. A armadilha esta
    # documentada: sem banco local, os testes com db_conn falham e nao
    # significam nada. O resto valida no CI, que sobe um postgres:15.
    Push-Location api
    try {
        $env:PYTHONPATH = (Get-Location).Path
        Nota "pytest (so os de logica pura -- o resto exige Postgres e valida no CI)"
        Executar "python" @(
            "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider",
            "tests/test_enriquecimento_modelo.py",
            "tests/test_cnpj.py",
            "tests/test_texto.py"
        ) "pytest local"
    } finally {
        Pop-Location
    }

    Push-Location web
    try {
        if (-not (Test-Path "node_modules")) {
            Nota "node_modules ausente -- rodando npm install"
            Executar "npm" @("install") "npm install"
        }
        Executar "npm" @("run", "test") "vitest"
        Executar "npm" @("run", "build") "vite build"
    } finally {
        Pop-Location
    }
    Ok "testes locais verdes"
    Nota "a suite completa do backend (1546 testes) roda no CI, com Postgres"
}

# ---------------------------------------------------------------------------
Titulo "Migration 014 no RDS"
# ---------------------------------------------------------------------------

if ($PularMigration) {
    Aviso "pulada por -PularMigration"
} else {
    $sqlLocal = Join-Path "api" (Join-Path "migrations" "014_enriquecimento.sql")
    $shLocal = Join-Path "infra" "aplicar-014-enriquecimento.sh"
    # Em dry-run a copia nao aconteceu, entao a ausencia aqui e esperada.
    foreach ($f in @($sqlLocal, $shLocal)) {
        if (-not (Test-Path $f) -and -not $DryRun) {
            Abortar "Nao achei $f apos a copia."
        }
    }

    Nota "enviando a migration para /tmp na EC2"
    if (-not $DryRun) {
        & scp -i $ChaveSsh $sqlLocal $shLocal "${Usuario}@${Servidor}:/tmp/"
        if ($LASTEXITCODE -ne 0) { Abortar "scp da migration falhou." }
    }
    Ok "arquivos no servidor"

    Write-Host ""
    Aviso "o script no servidor mostra o banco (com a senha mascarada) e pede confirmacao"
    Nota "confira o HOST antes de responder 's' -- e a unica barreira contra o banco errado"
    Write-Host ""

    # SEM o pipe base64 aqui, de proposito. As outras chamadas mandam o
    # script pelo stdin (`base64 -d | bash`), e nesse arranjo o stdin ja
    # esta consumido quando o script pede a confirmacao -- o `read` falha
    # na hora e o `set -e` mata tudo logo depois de imprimir o banco.
    #
    # Este comando nao tem caractere especial nenhum, entao vai direto, e o
    # `-t` aloca o terminal de que a confirmacao precisa. (O proprio .sh
    # tambem passou a ler de /dev/tty, entao os dois lados estao cobertos.)
    Nota "ssh -t ... bash /tmp/aplicar-014-enriquecimento.sh"
    if (-not $DryRun) {
        & ssh -t -i $ChaveSsh "$Usuario@$Servidor" `
            "bash /tmp/aplicar-014-enriquecimento.sh /tmp/014_enriquecimento.sql"
        if ($LASTEXITCODE -ne 0) {
            Abortar "migration 014 falhou no servidor (codigo $LASTEXITCODE)."
        }
    } else {
        Aviso "(dry-run) migration nao executada"
    }

    # Conferencia independente do que o script disse: 4 tabelas e 9 colunas.
    $verificacao = RemotoBash @'
set -euo pipefail
ENV_PATH=/home/hipo/app/.env
# O .env e 600 e o dono pode ser root OU hipo -- ver o cabecalho de
# infra/aplicar-014-enriquecimento.sh. Tenta as tres formas.
ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}
CONTEUDO=$(ler_env) || { echo "sem acesso ao .env"; exit 1; }
DATABASE_URL=$(printf '%s\n' "$CONTEUDO" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
psql "$DATABASE_URL" -At <<'SQL'
SELECT count(*) FROM information_schema.tables
 WHERE table_name IN ('cnaes','conta_socios','conta_enriquecimentos','conta_cnaes_secundarios');
SELECT count(*) FROM information_schema.columns
 WHERE table_name='contas' AND column_name IN
   ('cnae_codigo','porte','situacao_cadastral','data_abertura','capital_social',
    'num_funcionarios_origem','num_funcionarios_em','enriquecida_em','enriquecida_fonte');
SQL
'@ "conferencia da migration"

    if (-not $DryRun) {
        $linhas = @($verificacao | Where-Object { $_ -match '^\d+$' })
        if ($linhas.Count -ge 2) {
            $tabelas = [int] $linhas[0]
            $colunas = [int] $linhas[1]
            Write-Host "  tabelas novas: $tabelas / 4    colunas novas em contas: $colunas / 9"
            if ($tabelas -ne 4 -or $colunas -ne 9) {
                Abortar "A migration nao ficou completa. NAO faca o push."
            }
            Ok "estrutura conferida no banco"
        } else {
            Aviso "nao consegui ler a conferencia; confira a mao antes do push"
        }
    }
}

# ---------------------------------------------------------------------------
Titulo ".env da EC2"
# ---------------------------------------------------------------------------

if ($PularEnv) {
    Aviso "pulado por -PularEnv"
} else {
    if (-not $LeadCnpjApiKey) {
        Write-Host "  Chave da API da LeadCNPJ (Enter para deixar em branco e usar so a BrasilAPI):"
        $segura = Read-Host -AsSecureString "  chave"
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
        try {
            $LeadCnpjApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
    $LeadCnpjApiKey = $LeadCnpjApiKey.Trim()

    if (-not $LeadCnpjApiKey) {
        Aviso "sem chave: ENRIQUECIMENTO_FONTES vai so com brasilapi"
        Nota "tudo funciona, menos o numero de funcionarios"
        $fontes = "brasilapi"
    } else {
        $fontes = "leadcnpj,brasilapi"
    }

    # A chave vai em base64 e e decodificada do outro lado: nenhum caractere
    # especial dela atravessa o quoting do PowerShell nem o do bash.
    $chaveB64 = if ($LeadCnpjApiKey) {
        [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($LeadCnpjApiKey))
    } else { "" }

    $scriptEnv = @"
set -euo pipefail
ENV=/home/hipo/app/.env
CHAVE=''
if [ -n '$chaveB64' ]; then CHAVE=`$(echo '$chaveB64' | base64 -d); fi

# O .env e 600 e o dono pode ser root OU hipo. `sudo -u hipo` falha quando
# o arquivo e de root -- foi o que parou a primeira tentativa da 014. Como
# append por sudo NAO muda dono nem modo, ler e escrever como root e seguro
# nos dois casos.
ler_env() {
    sudo cat "`$ENV" 2>/dev/null && return 0
    sudo -iu hipo cat "`$ENV" 2>/dev/null && return 0
    cat "`$ENV" 2>/dev/null && return 0
    return 1
}

if ! CONTEUDO=`$(ler_env); then
    echo "ERRO: nao consegui ler `$ENV"
    sudo ls -l "`$ENV" 2>/dev/null || ls -l "`$ENV" 2>/dev/null || true
    exit 1
fi

# Acrescenta so o que ainda nao existe. Nunca reescreve o arquivo inteiro:
# o .env de producao tem segredo que nao esta em lugar nenhum.
adicionar() {
    local chave="`$1"
    local valor="`$2"
    if printf '%s\n' "`$CONTEUDO" | grep -qE "^`${chave}="; then
        echo "  ja existe: `$chave"
    else
        echo "`${chave}=`${valor}" | sudo tee -a "`$ENV" > /dev/null
        echo "  adicionado: `$chave"
        CONTEUDO="`$CONTEUDO
`${chave}=`${valor}"
    fi
}

adicionar ENRIQUECIMENTO_FONTES '$fontes'
adicionar ENRIQUECIMENTO_TTL_DIAS '90'
if [ -n "`$CHAVE" ]; then
    adicionar LEADCNPJ_API_KEY "`$CHAVE"
fi

echo
echo '-- variaveis de enriquecimento no .env (valores mascarados) --'
printf '%s\n' "`$CONTEUDO" | grep -E '^(ENRIQUECIMENTO_|LEADCNPJ_)' | sed -E 's/(KEY=).*/\1****/'
echo
echo '-- dono e modo do .env (nao devem ter mudado) --'
sudo ls -l "`$ENV" 2>/dev/null || ls -l "`$ENV"
"@

    RemotoBash $scriptEnv "atualizacao do .env"
    Ok ".env atualizado"
    Nota "o servico so le o .env novo depois do restart, que o CI faz no deploy"
}

# ---------------------------------------------------------------------------
Titulo "Commit e push"
# ---------------------------------------------------------------------------

if ($PularPush) {
    Aviso "pulado por -PularPush"
    Nota "a migration JA foi aplicada; suba o codigo assim que puder"
} else {
    # O backup nao entra no commit.
    if (Test-Path ".gitignore") {
        $ignore = Get-Content ".gitignore" -Raw
        if ($ignore -notmatch "_backup-014") {
            if (-not $DryRun) { Add-Content ".gitignore" "`n_backup-014-*/" }
            Nota "_backup-014-*/ adicionado ao .gitignore"
        }
    }

    $mensagem = @"
feat(crm): enriquecimento cadastral por CNPJ (014)

Consulta por CNPJ preenche cadastro, CNAE, porte, situacao cadastral e
quadro societario; CNAE ganha vertical e grau de risco (NR-4) mapeaveis,
valendo para todas as contas com aquele codigo.

Duas fontes atras da mesma interface (BrasilAPI e LeadCNPJ), com cache por
(cnpj, fonte) e TTL de 90 dias -- em fonte paga, consulta repetida e
dinheiro. Sem LEADCNPJ_API_KEY a fonte paga nao entra na lista e a API sobe
igual, como o S3, o SES e a chave da IA.

Regras que o codigo garante:
- enriquecimento nao sobrescreve campo preenchido por gente; a divergencia
  volta para a tela decidir
- numero de funcionarios estimado nunca sobrescreve o declarado pelo
  cliente, nem com sobrescrever=true
- CPF de socio e mascarado antes do banco, com CHECK como segunda barreira
- consulta nao grava: gravar e POST separado, com autoria

Migration 014 aditiva e idempotente, ja aplicada em producao.
"@

    Nota "git add ."
    if (-not $DryRun) {
        & git add .
        if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }

        # -F -: a mensagem vai por stdin. Passada por -m, o PowerShell 5.1
        # come as aspas e a mensagem chega picada em varias palavras.
        $mensagem | & git commit -F -
        if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada para commitar?)." }
        Ok "commit criado"

        & git push origin $branchAtual
        if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
        Ok "push enviado -- o CI assume daqui"
    }
}

# ---------------------------------------------------------------------------
Titulo "Conferencia no ar"
# ---------------------------------------------------------------------------

if ($DryRun) {
    Aviso "(dry-run) nada a conferir"
} elseif ($PularPush) {
    Aviso "sem push, nao ha o que conferir ainda"
} else {
    Write-Host "  Aguardando o CI (rsync + restart). Isso leva alguns minutos." -ForegroundColor DarkGray
    Write-Host "  Acompanhe em: https://github.com/tuliohorta77/Hipo-Web/actions" -ForegroundColor DarkGray
    Write-Host ""
    $r = Read-Host "  Quando os 3 jobs ficarem verdes, tecle Enter para conferir (ou 'n' para sair)"
    if ($r -ne "n" -and $r -ne "N") {
        try {
            $openapi = Invoke-RestMethod -Uri "https://hipogestao.com.br/api/openapi.json" -TimeoutSec 30
            $rotas = $openapi.paths.PSObject.Properties.Name
            $esperadas = @(
                "/crm/enriquecimento/cnpj/{cnpj}",
                "/crm/enriquecimento/contas/{conta_id}/aplicar",
                "/crm/enriquecimento/cnaes",
                "/crm/enriquecimento/socios/empresas"
            )
            $faltando = @()
            foreach ($rota in $esperadas) {
                if ($rotas -contains $rota) {
                    Ok "no ar: $rota"
                } else {
                    $faltando += $rota
                    Erro "ausente: $rota"
                }
            }
            if ($faltando.Count -gt 0) {
                Aviso "o deploy ainda nao chegou, ou o job falhou -- confira o Actions"
            }
        } catch {
            Aviso "nao consegui ler o openapi.json: $($_.Exception.Message)"
        }
    }
}

# ---------------------------------------------------------------------------

$duracao = (Get-Date) - $inicio
Write-Host ""
Write-Host ("=" * 64) -ForegroundColor DarkCyan
Write-Host " FIM  ($([int]$duracao.TotalMinutes)min $($duracao.Seconds)s)" -ForegroundColor Cyan
Write-Host ("=" * 64) -ForegroundColor DarkCyan
Write-Host ""
Write-Host " O QUE FAZER AGORA, NA TELA:" -ForegroundColor White
Write-Host ""
Write-Host "  1. LOGOUT e LOGIN." -ForegroundColor Yellow
Write-Host "     Ctrl+Shift+R recarrega os assets mas nao zera o localStorage."
Write-Host ""
Write-Host "  2. Contas -> Nova conta -> digite um CNPJ -> 'Buscar na Receita'."
Write-Host "     A conta nasce com endereco, CNAE, porte e socios."
Write-Host ""
Write-Host "  3. Abra a conta -> aba 'Dados publicos'."
Write-Host "     O CNAE aparece sem classificacao: mapeie a vertical e o grau"
Write-Host "     de risco ali. Vale para todas as contas com aquele codigo."
Write-Host ""
Write-Host "  4. Antes de deixar o plano da LeadCNPJ renovar, meca a cobertura"
Write-Host "     na sua propria carteira:" -ForegroundColor Yellow
Write-Host ""
Write-Host "       ssh -i `"$ChaveSsh`" $Usuario@$Servidor" -ForegroundColor DarkGray
Write-Host "       sudo -iu hipo" -ForegroundColor DarkGray
Write-Host "       cd /home/hipo/app/api" -ForegroundColor DarkGray
Write-Host "       python -m scripts.amostrar_enriquecimento --quantidade 100" -ForegroundColor DarkGray
Write-Host ""
Write-Host "     O numero que decide e um so: em quantas empresas o quadro de"
Write-Host "     pessoal vem preenchido."
Write-Host ""
if (-not $PularMigration -and -not $DryRun) {
    Write-Host " Para voltar atras: a migration e aditiva, entao o codigo antigo" -ForegroundColor DarkGray
    Write-Host " roda sem problema com as tabelas novas paradas. Basta o revert" -ForegroundColor DarkGray
    Write-Host " do commit -- nenhum DROP e necessario." -ForegroundColor DarkGray
    Write-Host ""
}
