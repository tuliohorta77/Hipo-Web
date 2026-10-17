# =====================================================================
#  HIPO -- deploy 060: modulo Contratos (repasse Controller -> Spectre)
#          + conta da administracao + carga da planilha de contratos
# =====================================================================
#
#  Modulo novo 'contratos' (/contratos na tela, /repasses na API):
#    - um contrato por CNPJ cobrado (por vida ou valor fixo);
#    - lancamento do mes: vidas, valor por vida ou de tabela ->
#      K (contrato), L (repasse: 100% no 1o mes, 30% depois),
#      N (imposto 14,33%) e O (liquido); nota do mes = soma dos O
#      menos os descontos; NF e recebimento.
#  Quem ve: Franqueado, ADM e o cargo novo Financeiro (a conta
#  administracao@controllermedseg.com, que so ve este modulo).
#  EC, SDR, EV e EP nao veem.
#  Migration 043 (aditiva), aplicada sozinha pelo deploy do CI.
#  Gestao precisa SAIR e ENTRAR de novo para ver o item "Contratos".
#
#    1. pre-voo      -- arquivos no lugar, base do git, SSH
#    2. testes       -- vitest da tela + pytest das regras (o CI roda tudo)
#    3. push         -- SO os arquivos da entrega
#    4. espera       -- ate o codigo novo chegar no servidor
#    5. usuario      -- administracao@controllermedseg.com, senha 123456
#    6. carga        -- oportunidades conquistadas + contratos (dry-run,
#                       pergunta, so entao grava)
#
#  USO
#     .\deploy-060-contratos.ps1 -Simular
#     .\deploy-060-contratos.ps1 -Responsavel seu-login@controllermedseg.com
#     .\deploy-060-contratos.ps1 -SoUsuario            (push ja foi; etapas 5 e 6)
#     .\deploy-060-contratos.ps1 -SoCarga -Responsavel x@y.com
#
#  ESTE ARQUIVO E ASCII PURO (PowerShell 5.1 + copiar-e-colar).
# =====================================================================

[CmdletBinding()]
param(
    [switch]$Simular,
    [switch]$PularTestes,
    [switch]$SoUsuario,
    [switch]$SoCarga,
    [switch]$Forcar,

    [string]$Responsavel = "",
    [string]$Pasta    = (Get-Location).Path,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "hipogestao.com.br",
    [string]$Usuario  = "ec2-user",
    [int]$EsperaMax   = 900
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
if ($SoCarga) { $SoUsuario = $true }

# Arquivos EXISTENTES que a entrega altera, com o blob de cada um no HEAD
# sobre o qual a 060 foi feita (16/10/2026).
$base = [ordered]@{
    "api/main.py"                        = "4ee1c8d285823ae51c98ae14d352ef64925c2467"
    "api/routers/permissions.py"         = "49ea9ae1546310cb5687c1f4e64faa8300491409"
    "api/services/telemetria.py"         = "4e27cdbdc805204c6f3809ba94da40d7c15038cc"
    "api/services/atividade.py"          = "c8933fe34b0a6b802b2fe432a951f46835314cf7"
    "api/schema.sql"                     = "c1549612f9e0e8a95ae24a9cb7afe47845cff6ed"
    "api/tests/test_permissions_auth.py" = "ef36331abf6e11ee38ac918b4a716006d051ff26"
    "web/src/App.jsx"                    = "3a1ac6a308c8dc7a24ac5947b3ea0b7c7a86a143"
    "web/src/api.js"                     = "7df300e74139a26447451271dba79adedf3ab2ac"
    "web/src/components/Layout.jsx"      = "d37345fedefdd54a5ad160ddac33793d4b6ca7a9"
    "web/src/tests/Layout.test.jsx"      = "1b7618efdb6122939b3011c5d34c6da9344bf89c"
    "web/src/tests/primeiraRota.test.js" = "3189db515315444c93c84b4cabca0462c47e85ab"
}

$novos = @(
    "api/migrations/043_repasses_contratos.sql",
    "api/routers/repasses.py",
    "api/services/repasse.py",
    "api/scripts/criar_usuario_financeiro.py",
    "api/tests/test_repasses.py",
    "api/tests/test_repasse_regras.py",
    "web/src/pages/contratos/Contratos.jsx",
    "web/src/components/contratos/repasseCalculo.js",
    "web/src/tests/Contratos.test.jsx",
    "infra/criar-usuario-financeiro.sh",
    "deploy-060-contratos.ps1"
)

# Entrega 042 (gravacao duplicada de ligacao + gravador 1.0.7): estava na
# pasta SEM commit. Vai num commit proprio ANTES da 060, no mesmo push --
# a 043 nao pode subir antes da 042 (o aplicar_migrations recusa migration
# pendente com numero menor que a ultima aplicada). telemetria.py e
# schema.sql tem mudanca das duas: o commit da 042 leva a versao so com a
# 042 (Claude outputs\*_042.*), e o da 060 leva a versao completa.
$entrega042 = @(
    "api/migrations/042_ligacao_duplicada.sql",
    "api/routers/crm_ligacoes.py",
    "api/services/coleta_ligacao.py",
    "api/services/ligacao.py",
    "api/tests/test_crm_ligacoes.py",
    "api/tests/test_ligacao_regras.py",
    "gravador/LEIA-ME.md",
    "gravador/app/__init__.py",
    "gravador/app/config.py",
    "gravador/app/principal.py",
    "gravador/tests/test_gravador.py"
)
$versoes042 = [ordered]@{
    "api/services/telemetria.py" = "Claude outputs\telemetria_042.py"
    "api/schema.sql"             = "Claude outputs\schema_042.sql"
}

# Carga de uso unico: vai por scp, nao entra no git.
$carga = @("carga_contratos_spectre.py", "carga-contratos-spectre.sh")

$entrega = $novos + @($base.Keys)

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

$faltando = @(($entrega + $carga) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
if ($faltando.Count -gt 0) {
    foreach ($f in $faltando) { Write-Host "     falta: $f" -ForegroundColor Red }
    Abortar "$($faltando.Count) arquivo(s) da entrega nao estao na pasta."
}
Bom "arquivos da entrega conferidos"

if (-not $SoUsuario) {
    $migs = @(Get-ChildItem "api/migrations" -Filter "043_*.sql" | Select-Object -ExpandProperty Name)
    if ($migs.Count -ne 1) { Abortar "numero 043 em uso por outra migration: $($migs -join ', ')" }

    # Via cmd: no PowerShell 5.1 com ErrorAction Stop, stderr de exe vira excecao.
    & cmd /c "git ls-files --error-unmatch api/migrations/042_ligacao_duplicada.sql >nul 2>nul"
    $pendente042 = ($LASTEXITCODE -ne 0)
    if ($pendente042) {
        $falta042 = @(($entrega042 + @($versoes042.Values)) | Where-Object { -not (Test-Path (Join-Path $Pasta $_)) })
        if ($falta042.Count -gt 0) {
            foreach ($f in $falta042) { Write-Host "     falta: $f" -ForegroundColor Red }
            Abortar "a 042 esta pendente mas faltam arquivos dela."
        }
        Aviso "a 042 (ligacao duplicada + gravador 1.0.7) ainda nao tem commit: vai antes da 060, no mesmo push"
    } else {
        Bom "a 042 ja esta commitada"
    }

    $divergentes = @()
    foreach ($f in $base.Keys) {
        $head = (& git rev-parse "HEAD:$f" 2>$null)
        if ($head -ne $base[$f]) { $divergentes += $f }
    }
    if ($divergentes.Count -gt 0) {
        foreach ($f in $divergentes) { Write-Host "     $f no HEAD difere da base da 060" -ForegroundColor Yellow }
        if ($Forcar) {
            Aviso "seguindo por -Forcar (confira o diff antes do push)"
        } else {
            Abortar "outra entrega mexeu nesses arquivos depois da base. Me mande os atuais (ou -Forcar)."
        }
    } else {
        Bom "base do git confere"
    }
}

if (-not (Test-Path $Chave)) { Abortar "nao achei a chave SSH: $Chave" }
Passo "porta 22 em $Servidor..."
$aberta = $false
try {
    $aberta = Test-NetConnection -ComputerName $Servidor -Port 22 `
        -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { $aberta = $false }
if (-not $aberta) {
    Write-Host "  Se for o seu IP residencial: .\ops\utilitarios\liberar-meu-ip-ssh.ps1" -ForegroundColor Gray
    Abortar "sem SSH nao da para criar o usuario nem rodar a carga."
}
Bom "porta 22 responde"

if (-not $SoUsuario) {

# =====================================================================
# 2. Testes
# =====================================================================

Titulo "2. Testes"
if ($PularTestes) {
    Aviso "pulado por -PularTestes (o CI ainda vai rodar tudo)"
} else {
    Push-Location (Join-Path $Pasta "web")
    try {
        Passo "vitest (Contratos, Layout, primeira rota)..."
        & npx vitest run src/tests/Contratos.test.jsx src/tests/Layout.test.jsx src/tests/primeiraRota.test.js
        if ($LASTEXITCODE -ne 0) { Abortar "vitest falhou. Nada foi commitado." }
        Passo "build..."
        & npx vite build
        if ($LASTEXITCODE -ne 0) { Abortar "build falhou. Nada foi commitado." }
        Bom "front verde"
    } finally { Pop-Location }

    $py = Join-Path $Pasta "api\venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $py = $cmd.Source } else { $py = $null }
    }
    if ($py) {
        Push-Location (Join-Path $Pasta "api")
        try {
            $env:PYTHONPATH = (Get-Location).Path
            Passo "pytest (regras puras do repasse e permissoes)..."
            & $py -m pytest -q -p no:cacheprovider --no-cov tests\test_repasse_regras.py `
                "tests\test_permissions_auth.py::TestModulosDoCargo"
            if ($LASTEXITCODE -ne 0) { Abortar "pytest falhou. Nada foi commitado." }
            Bom "regras verdes (os testes de banco rodam no CI)"
        } finally { Pop-Location }
    } else {
        Aviso "python nao encontrado -- os testes do backend ficam so com o CI"
    }
}

# =====================================================================
# 3. Push
# =====================================================================

Titulo "3. Push"

$mensagem = @"
feat(contratos): modulo Contratos -- repasse Controller -> Spectre (migration 043)

- repasse_contratos / repasse_lancamentos / repasse_competencias /
  repasse_descontos: contrato por CNPJ, lancamento mensal (K, L, N, O),
  nota do mes e descontos.
- Regra: 100% no primeiro mes (premio de venda), 30% da recorrencia
  depois; imposto 14,33%; nota = soma dos liquidos - descontos.
- Tela /contratos: mes (KPIs, proxima acao, lancar/confirmar sugestoes,
  nota e recebimento) e cadastro (contratos, gerar da oportunidade).
- Permissao: modulo 'contratos' para Franqueado, ADM e o cargo novo
  Financeiro (conta da administracao, so este modulo).
- scripts/criar_usuario_financeiro.py + infra/criar-usuario-financeiro.sh.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ArDdJvuL2mBbim4F1qc7xQ
"@

if ($Simular) {
    Aviso "simulacao: nao vou commitar nem dar push"
    & git status --short -- $entrega
} else {
    if ($pendente042) {
        Confirmar "Commitar a 042 (ligacao duplicada + gravador 1.0.7), depois a 060, e dar push na main?"
        $msg042 = @"
feat(ligacoes): gravacao duplicada marcada e fora das contas (migration 042) + gravador 1.0.7

- ligacoes.duplicada_de: o coletor compara a transcricao com as ligacoes
  da mesma pessoa em +-15 min e marca a copia sem vinculo; ela sai da faixa
  "sem vinculo" e das contas de atividade.
- gravador 1.0.7: fim da chamada com 15 s de silencio (antes 4 s), corte
  do rabo e instancia unica.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ArDdJvuL2mBbim4F1qc7xQ
"@
        # Troca temporaria: telemetria.py e schema.sql so com a 042.
        $guarda = @{}
        foreach ($f in $versoes042.Keys) {
            $tmp = Join-Path $env:TEMP ("hipo-060-" + [IO.Path]::GetFileName($f))
            Copy-Item -LiteralPath $f -Destination $tmp -Force
            $guarda[$f] = $tmp
            Copy-Item -LiteralPath $versoes042[$f] -Destination $f -Force
        }
        try {
            $arq042 = $entrega042 + @($versoes042.Keys)
            & git add -- $arq042
            if ($LASTEXITCODE -ne 0) { throw "git add da 042 falhou." }
            $tmpMsg = Join-Path $env:TEMP "hipo-commit-042.txt"
            [System.IO.File]::WriteAllText($tmpMsg, $msg042, (New-Object System.Text.UTF8Encoding($false)))
            & git commit -F $tmpMsg -- $arq042
            if ($LASTEXITCODE -ne 0) { throw "git commit da 042 falhou." }
            Remove-Item $tmpMsg -ErrorAction SilentlyContinue
        } finally {
            # Volta a versao completa (042 + 060) na pasta, aconteca o que for.
            foreach ($f in $guarda.Keys) { Copy-Item -LiteralPath $guarda[$f] -Destination $f -Force }
        }
        Bom "commit da 042 criado"
    } else {
        Confirmar "Commitar a entrega 060 e dar push na main?"
    }
    & git add -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git add falhou." }
    $tmpMsg = Join-Path $env:TEMP "hipo-commit-060.txt"
    [System.IO.File]::WriteAllText($tmpMsg, $mensagem, (New-Object System.Text.UTF8Encoding($false)))
    & git commit -F $tmpMsg -- $entrega
    if ($LASTEXITCODE -ne 0) { Abortar "git commit falhou (nada mudou?). Se o push ja foi, rode com -SoUsuario." }
    Remove-Item $tmpMsg -ErrorAction SilentlyContinue
    Bom "commit criado"
    & git push
    if ($LASTEXITCODE -ne 0) { Abortar "git push falhou." }
    Bom "push feito -- o CI assumiu daqui (aplica as migrations pendentes no deploy)"
}

# =====================================================================
# 4. Espera o codigo novo
# =====================================================================

Titulo "4. Esperando o CI"

$marcador = "/home/hipo/app/api/scripts/criar_usuario_financeiro.py"
if ($Simular) {
    Aviso "simulacao: nao vou esperar"
} else {
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $chegou = $false
    while ($relogio.Elapsed.TotalSeconds -lt $EsperaMax) {
        & ssh -i $Chave -o ConnectTimeout=10 $alvo "test -f $marcador" 2>$null
        if ($LASTEXITCODE -eq 0) { $chegou = $true; break }
        Write-Host "     ainda nao ($([int]$relogio.Elapsed.TotalSeconds) s)..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 20
    }
    if (-not $chegou) {
        Aviso "o codigo nao chegou em $EsperaMax s. Olhe o Actions; depois rode com -SoUsuario."
        exit 1
    }
    Bom "codigo novo no servidor"
    Passo "aguardando 60 s para o restart da API e a migration..."
    Start-Sleep -Seconds 60
}

}  # fim do if (-not $SoUsuario)

# =====================================================================
# 5. Usuario da administracao
# =====================================================================

if (-not $SoCarga) {
    Titulo "5. Usuario administracao@controllermedseg.com (cargo Financeiro)"
    if ($Simular) {
        Aviso "simulacao: nao vou criar nada"
    } else {
        & scp -i $Chave (Join-Path $Pasta "infra\criar-usuario-financeiro.sh") "${alvo}:/tmp/criar-usuario-financeiro.sh"
        if ($LASTEXITCODE -ne 0) { Abortar "o scp do script falhou." }
        & ssh -i $Chave $alvo "bash /tmp/criar-usuario-financeiro.sh"
        if ($LASTEXITCODE -ne 0) { Abortar "a criacao falhou (codigo $LASTEXITCODE)." }
        Bom "usuario pronto (senha 123456)"
    }
}

# =====================================================================
# 6. Carga da planilha de contratos
# =====================================================================

Titulo "6. Carga: oportunidades conquistadas + contratos"
if ($Simular) {
    Aviso "simulacao: nao vou rodar a carga"
} else {
    & scp -i $Chave (Join-Path $Pasta "carga-contratos-spectre.sh") (Join-Path $Pasta "carga_contratos_spectre.py") "${alvo}:/tmp/"
    if ($LASTEXITCODE -ne 0) { Abortar "o scp da carga falhou." }
    if (-not $Responsavel) {
        & ssh -t -i $Chave $alvo "bash /tmp/carga-contratos-spectre.sh"
        $Responsavel = Read-Host "  E-mail do responsavel pela carga (o seu login no HIPO)"
        if (-not $Responsavel) { Abortar "sem responsavel a carga nao roda. Depois: -SoCarga -Responsavel x@y.com" }
    }
    # Dry-run, relatorio, pergunta [s/N] e so entao grava.
    & ssh -t -i $Chave $alvo "bash /tmp/carga-contratos-spectre.sh '$Responsavel'"
    $saida = $LASTEXITCODE
    if ($saida -eq 3) {
        Aviso "carga cancelada. Nada gravado. Rode de novo com -SoCarga."
    } elseif ($saida -ne 0) {
        Abortar "a carga falhou (codigo $saida). Mande a saida acima."
    } else {
        Bom "carga concluida"
    }
}

Titulo "Pronto"
Write-Host @"
  1. Gestao: SAIR e ENTRAR de novo -> item "Contratos" na barra.
  2. administracao@controllermedseg.com / 123456 (aba anonima): cai direto
     em Contratos e a barra mostra so esse item. Trocar a senha em Perfil.
  3. Contratos > Mes: out/2026 com os 26 contratos pendentes e a sugestao
     copiada do cadastro. "Confirmar sugestoes" lanca todos de uma vez.
  4. Oportunidades: as conquistadas da planilha, com a data da coluna B
     (02/02 com 12 CNPJs, 24/04, 20/05, 20/06 e uma por venda depois).
"@ -ForegroundColor White
