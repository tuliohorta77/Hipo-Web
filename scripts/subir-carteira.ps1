<#
    HIPO - Sobe a carteira da Oraculus e o bloqueio da MedSeg, de uma vez.

    E o script unico: aplica a migration 010, marca os clientes da MedSeg,
    cria as contas e as oportunidades da Oraculus e confere o resultado no
    banco no fim. Na ordem certa, que e a unica que funciona.

    POR QUE UM SO
    Os tres passos tem dependencia real entre si. A migration precisa vir
    antes das duas cargas (sem a coluna nao_prospectar as duas morrem), e o
    bloqueio da MedSeg precisa vir antes da Oraculus -- um CNPJ que esteja
    nas duas listas tem que ja estar bloqueado quando a carteira passar,
    senao entra no funil e so seria barrado na rodada seguinte. Hoje as duas
    listas nao se cruzam; a ordem existe para a proxima versao da planilha.

    Rodar os tres a mao funciona igual. Isto so tira a chance de trocar a
    ordem ou esquecer a migration -- que e passo manual e, por isso, o que
    mais se esquece.

    DUAS PASSADAS, SEMPRE
    Sem -Commit, os importadores rodam em dry-run e desfazem tudo no fim.
    Leia os numeros, e so entao rode de novo com -Commit. O script NAO faz
    as duas passadas sozinho de proposito: quem le os numeros e voce.

    A MIGRATION E A EXCECAO
    Ela e aditiva e idempotente, mas e DDL de verdade e nao volta atras.
    Por isso ela nao entra no dry-run: o script CONFERE se a coluna existe e,
    se nao existir, para e manda voce rodar com -AplicarMigration. Uma vez
    aplicada, as rodadas seguintes so passam por ela.

    NAO PRECISA TER FEITO O PUSH AINDA
    As cargas escrevem direto no banco, nao passam pela API. O codigo novo
    (KPI, badge, bloqueio na criacao de oportunidade) so muda o que voce VE
    na tela. Da para subir os dados antes e o codigo depois -- a base fica
    correta nos dois momentos.

    USO (da raiz do projeto)

        # 1a vez: aplica a migration e mostra o que as cargas fariam
        .\scripts\subir-carteira.ps1 -FinderCnpj "12.345.678/0001-99" `
            -FinderRazao "CONTROLLER ORACULUS ..." -AplicarMigration

        # conferiu os numeros? entao grava
        .\scripts\subir-carteira.ps1 -FinderCnpj "12.345.678/0001-99" -Commit

    ESPERADO no dry-run: 326 contas da MedSeg marcadas, 946 contas da
    Oraculus, 463 contatos, 946 oportunidades em suspect, 473 para o Gabriel
    e 473 para a Kethlleen. Se aparecer outra coisa, pare e investigue.

    Outras opcoes:
        -Limite 100            sobe a Oraculus em lote (roda de novo p/ continuar)
        -Responsaveis "a@x,b@x"  troca a dupla padrao
        -SemResponsavel        carrega sem envolvido nenhum
        -PularMedseg           so a Oraculus (se a MedSeg ja subiu)
        -PularOraculus         so a MedSeg
        -PularComNegocio       nao cria suspect em conta que ja tem negocio
                               aberto (a carga sempre AVISA quais sao; esta
                               flag e para nao criar mesmo)
        -AdotarFinder          nas que ficaram de fora e estao paradas em
                               suspect SEM finder, grava a Oraculus como
                               finder da oportunidade que ja existe. Nao toca
                               em lead, negociacao, fechada nem em quem ja
                               tem outro finder. Feito para andar junto com
                               -PularComNegocio.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FinderCnpj,
    [string]$FinderRazao = "",
    [string]$Responsaveis = "",
    [switch]$SemResponsavel,
    [int]$Limite = 0,
    [switch]$Commit,
    [switch]$AplicarMigration,
    [switch]$PularMedseg,
    [switch]$PularOraculus,
    [switch]$PularComNegocio,
    [switch]$AdotarFinder,
    [string]$Chave    = "$HOME\Downloads\chave-hipo.pem",
    [string]$Servidor = "ec2-user@63.179.88.212"
)

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot

$arquivos = @{
    migration   = Join-Path $raiz "api\migrations\010_nao_prospectar.sql"
    impMedseg   = Join-Path $raiz "api\scripts\importar_medseg_bloqueio.py"
    payMedseg   = Join-Path $raiz "api\scripts\dados\medseg_nao_prospectar_2026-09-09.json"
    impOraculus = Join-Path $raiz "api\scripts\importar_oraculus.py"
    payOraculus = Join-Path $raiz "api\scripts\dados\oraculus_2026-09-09.json"
    shMigration = Join-Path $raiz "scripts\aplicar_migration_remoto.sh"
    shColuna    = Join-Path $raiz "scripts\conferir_coluna_remoto.sh"
    shMedseg    = Join-Path $raiz "scripts\carga_medseg_bloqueio_remoto.sh"
    shOraculus  = Join-Path $raiz "scripts\carga_oraculus_remoto.sh"
    shConferir  = Join-Path $raiz "scripts\conferir_carga_remoto.sh"
}

# Confere TUDO antes de mandar qualquer coisa: descobrir na metade que falta
# um arquivo deixa a EC2 com meio pacote em /tmp e a carga pela metade.
foreach ($par in $arquivos.GetEnumerator()) {
    if (-not (Test-Path $par.Value)) { throw "Nao encontrei: $($par.Value)" }
}
if (-not (Test-Path $Chave)) { throw "Nao encontrei a chave SSH: $Chave" }

$digitos = ($FinderCnpj -replace '\D', '')
if ($digitos.Length -ne 14) { throw "FinderCnpj precisa ter 14 digitos. Recebi: $FinderCnpj" }
if ($PularMedseg -and $PularOraculus) { throw "Pular as duas cargas nao faz nada." }

function Enviar($local, $nomeRemoto) {
    scp -i $Chave $local "${Servidor}:/tmp/$nomeRemoto"
    if ($LASTEXITCODE -ne 0) { throw "scp de $nomeRemoto falhou." }
}

# tr -d '\r': o .sh sai do Windows podendo levar CRLF, e o bash quebra no
# primeiro \r com um erro que nao diz o que aconteceu.
function RodarNaEc2($shRemoto, $destino, $argumentos) {
    ssh -i $Chave $Servidor "tr -d '\r' < /tmp/$shRemoto > /tmp/$destino && bash /tmp/$destino $argumentos"
    if ($LASTEXITCODE -ne 0) {
        throw "Passo falhou na EC2 ($shRemoto). As cargas rodam em transacao unica - nada foi gravado por ela."
    }
}

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 66) -ForegroundColor DarkGray
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 66) -ForegroundColor DarkGray
}

$flagCommit = if ($Commit) { "--commit" } else { "" }

Write-Host "servidor : $Servidor"
Write-Host "finder   : $digitos"
Write-Host "modo     : $(if ($Commit) { 'COMMIT - grava de verdade' } else { 'DRY-RUN - desfaz tudo no fim' })"
Write-Host "resp.    : $(if ($SemResponsavel) { 'NENHUM' } elseif ($Responsaveis -ne '') { $Responsaveis } else { 'Gabriel + Kethlleen (padrao, meio a meio)' })"
if ($Limite -gt 0) { Write-Host "limite   : $Limite (so a Oraculus)" }

# -- Passo 0: migration -----------------------------------------------
Titulo "0/3  Migration 010 - coluna nao_prospectar"

if ($AplicarMigration) {
    Enviar $arquivos.migration   "010_nao_prospectar.sql"
    Enviar $arquivos.shMigration "aplicar_migration_remoto.sh"
    RodarNaEc2 "aplicar_migration_remoto.sh" "aplicar-migration.sh" "010_nao_prospectar.sql"
} else {
    # A coluna existe? Perguntar e barato; descobrir que nao existe no meio
    # da carga custa uma transacao inteira desfeita e um susto.
    Write-Host "Conferindo se a coluna ja existe..."
    Enviar $arquivos.shColuna "conferir_coluna_remoto.sh"
    # tail -1 porque o .sh pode imprimir aviso antes; a resposta e a ultima
    # linha. Uma chamada so: rodar duas vezes imprimiria SIM/NAO solto na tela.
    $existe = ssh -i $Chave $Servidor "tr -d '\r' < /tmp/conferir_coluna_remoto.sh > /tmp/conferir-coluna.sh && bash /tmp/conferir-coluna.sh contas nao_prospectar | tail -1"
    if ($LASTEXITCODE -ne 0) { throw "Nao consegui conferir o banco na EC2." }
    if ("$existe".Trim() -ne "SIM") {
        throw @"
A coluna nao_prospectar ainda nao existe em producao.

As duas cargas dependem dela. Rode de novo com -AplicarMigration:

  .\scripts\subir-carteira.ps1 -FinderCnpj "$FinderCnpj" -AplicarMigration

(A migration 010 e aditiva e idempotente: so acrescenta quatro colunas, um
CHECK e um indice. Nao apaga nada e pode ser rodada de novo sem efeito.)
"@
    }
    Write-Host "Coluna presente. Migration ja aplicada." -ForegroundColor Green
}

# -- Passo 1: bloqueio da MedSeg --------------------------------------
if (-not $PularMedseg) {
    Titulo "1/3  Clientes MedSeg -> nao prospectar  (326 CNPJ)"
    Enviar $arquivos.impMedseg "importar_medseg_bloqueio.py"
    Enviar $arquivos.payMedseg "medseg_nao_prospectar_2026-09-09.json"
    Enviar $arquivos.shMedseg  "carga_medseg_bloqueio_remoto.sh"
    RodarNaEc2 "carga_medseg_bloqueio_remoto.sh" "carga-medseg.sh" $flagCommit
} else {
    Titulo "1/3  MedSeg - PULADO (-PularMedseg)"
}

# -- Passo 2: carteira da Oraculus ------------------------------------
if (-not $PularOraculus) {
    Titulo "2/3  Carteira Oraculus -> suspects  (946 contas)"
    Enviar $arquivos.impOraculus "importar_oraculus.py"
    Enviar $arquivos.payOraculus "oraculus_2026-09-09.json"
    Enviar $arquivos.shOraculus  "carga_oraculus_remoto.sh"

    # Lista, e nao string concatenada: um if inline no meio da string deixa
    # espaco duplicado e o bash entrega um argumento vazio ao Python.
    $extraArgs = @()
    if ($Commit)                  { $extraArgs += "--commit" }
    if ($Limite -gt 0)            { $extraArgs += "--limite"; $extraArgs += "$Limite" }
    # base64, e nao aspas. O PowerShell 5.1 REMOVE aspas duplas ao montar a
    # linha de comando de um programa externo (aqui, o ssh), entao
    #     --finder-razao "RAZAO COM ESPACO"
    # chega do outro lado como tres palavras soltas e o argparse recusa.
    # Aspas simples resolveriam o espaco mas nao a apostrofe, e uma das
    # razoes sociais reais desta base e "ORACULU'S CONTABIL LTDA".
    # Base64 nao tem metacaractere nenhum: atravessa inteiro.
    if ($FinderRazao -ne "") {
        $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($FinderRazao))
        $extraArgs += "--finder-razao-b64"; $extraArgs += $b64
    }
    if ($PularComNegocio)         { $extraArgs += "--pular-com-negocio" }
    if ($AdotarFinder)            { $extraArgs += "--adotar-finder-no-suspect" }
    if ($SemResponsavel)          { $extraArgs += "--sem-responsavel" }
    elseif ($Responsaveis -ne "") { $extraArgs += "--responsaveis"; $extraArgs += "$Responsaveis" }

    RodarNaEc2 "carga_oraculus_remoto.sh" "carga-oraculus.sh" "$digitos $($extraArgs -join ' ')"
} else {
    Titulo "2/3  Oraculus - PULADO (-PularOraculus)"
}

# -- Passo 3: conferencia ---------------------------------------------
# So depois do commit. Num dry-run a transacao ja voltou, e conferir aqui
# mostraria a base como estava antes -- numero certo respondendo a pergunta
# errada, que e o pior tipo de relatorio.
if ($Commit) {
    Titulo "3/3  Conferencia no banco"
    Enviar $arquivos.shConferir "conferir_carga_remoto.sh"
    RodarNaEc2 "conferir_carga_remoto.sh" "conferir-carga.sh" ""
} else {
    Titulo "3/3  Conferencia - so depois do -Commit"
    Write-Host "O dry-run ja desfez tudo; conferir agora leria a base de antes." -ForegroundColor DarkGray
}

Write-Host ""
if ($Commit) {
    Write-Host "Carga concluida." -ForegroundColor Green
    Write-Host "  Contas       https://hipogestao.com.br/crm/contas" -ForegroundColor Green
    Write-Host "  Oportunidades https://hipogestao.com.br/crm/oportunidades" -ForegroundColor Green
    Write-Host ""
    Write-Host "Se o codigo novo ainda nao subiu, o KPI 'Nao prospectar' e o bloqueio" -ForegroundColor Yellow
    Write-Host "na criacao de oportunidade so aparecem depois do push. Os dados ja estao la." -ForegroundColor Yellow
} else {
    Write-Host "Dry-run terminado - NADA foi gravado." -ForegroundColor Yellow
    Write-Host "Se os numeros baterem, rode de novo com -Commit." -ForegroundColor Yellow
}
