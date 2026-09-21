<#
    HIPO - Descoberta do contrato da API da LeadCNPJ (v2)
    =====================================================

    A v1 voltou com status 0 nas 25 tentativas, inclusive nas cinco que nem
    usam chave. Status 0 nao e "caminho errado" nem "header errado": e a
    conexao que nao saiu da maquina. E a v1 tinha um defeito meu -- ela
    capturava a mensagem da excecao e nao imprimia, entao o motivo real
    ficou invisivel.

    Esta versao arruma isso e passa a fazer, nesta ordem:

      PASSO 0  diagnostico de rede, com um alvo de CONTROLE (a BrasilAPI).
               E o que separa "sua internet/proxy esta bloqueando" de "a
               LeadCNPJ especificamente nao responde".
      PASSO 1  a especificacao OpenAPI (nao gasta credito).
      PASSO 2  uma consulta real, so se o passo 0 disser que da.

    Toda falha agora mostra a MENSAGEM, e cada tentativa e feita por dois
    caminhos diferentes quando o primeiro falha: Invoke-WebRequest (stack do
    .NET) e curl.exe (stack propria do Windows, que ignora proxy do .NET e
    tem TLS proprio). Se um funciona e o outro nao, a resposta esta ai.

    COMO RODAR

      .\descobrir-leadcnpj.ps1

    Ele pergunta a chave (digitacao oculta). Me mande o resumo.txt.
    A chave NAO entra em nenhum arquivo gerado.

    Sem acentos de proposito.
#>

[CmdletBinding()]
param(
    [string] $Chave = "",
    [string] $Cnpj = "33000167000101",
    [string] $BaseUrl = "https://leadcnpj.com.br/api",
    [string] $Saida = "leadcnpj-descoberta"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11
} catch { }

New-Item -ItemType Directory -Force -Path $Saida | Out-Null
$linhas = New-Object System.Collections.Generic.List[string]

function Anotar([string] $texto) {
    $script:linhas.Add($texto) | Out-Null
    Write-Host $texto
}

function Mascarar([string] $texto) {
    if (-not $texto) { return $texto }
    if ($script:Chave) { return $texto.Replace($script:Chave, "<CHAVE-OMITIDA>") }
    return $texto
}

# Devolve sempre (status, corpo, erro). Status 0 = nem conectou, e nesse
# caso `erro` traz a mensagem -- que era justamente o que faltava na v1.
function ViaDotNet([string] $url, [hashtable] $headers) {
    $r = [ordered]@{ via = ".NET"; status = 0; corpo = ""; erro = "" }
    try {
        $resp = Invoke-WebRequest -Uri $url -Headers $headers -Method Get `
                                  -UseBasicParsing -TimeoutSec 25
        $r.status = [int] $resp.StatusCode
        $r.corpo = $resp.Content
    } catch {
        $resp = $null
        if ($_.Exception.PSObject.Properties.Name -contains "Response") {
            $resp = $_.Exception.Response
        }
        if ($resp -and $resp.PSObject.Properties.Name -contains "StatusCode") {
            try { $r.status = [int] $resp.StatusCode } catch { }
            try {
                $sr = New-Object IO.StreamReader($resp.GetResponseStream())
                $r.corpo = $sr.ReadToEnd(); $sr.Close()
            } catch { }
        }
        if ($r.status -eq 0) {
            $r.erro = $_.Exception.Message
            $interna = $_.Exception.InnerException
            while ($interna) {
                $r.erro += " | " + $interna.Message
                $interna = $interna.InnerException
            }
        }
    }
    return $r
}

# curl.exe e outra pilha: TLS proprio, proxy proprio, sem o .NET no meio.
# `curl` sozinho seria o alias de Invoke-WebRequest no PowerShell 5.1 --
# tem que ser curl.exe.
function ViaCurl([string] $url, [hashtable] $headers) {
    $r = [ordered]@{ via = "curl.exe"; status = 0; corpo = ""; erro = "" }
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { $r.erro = "curl.exe nao encontrado"; return $r }

    $args = @("-s", "-S", "--max-time", "25", "-w", "`n%{http_code}", $url)
    foreach ($k in $headers.Keys) { $args += @("-H", "${k}: $($headers[$k])") }

    $saidaErro = [IO.Path]::GetTempFileName()
    try {
        $texto = & curl.exe @args 2> $saidaErro
        $stderr = (Get-Content $saidaErro -Raw -ErrorAction SilentlyContinue)
        if ($texto) {
            $partes = ($texto -join "`n") -split "`n"
            $ultima = $partes[-1]
            if ($ultima -match '^\d{3}$') {
                $r.status = [int] $ultima
                $r.corpo = ($partes[0..($partes.Count - 2)] -join "`n")
            } else {
                $r.corpo = ($partes -join "`n")
            }
        }
        if ($r.status -eq 0 -and $stderr) { $r.erro = $stderr.Trim() }
    } finally {
        Remove-Item $saidaErro -Force -ErrorAction SilentlyContinue
    }
    return $r
}

# Tenta pelo .NET; se nem conectar, tenta por curl.exe.
function Chamar([string] $url, [hashtable] $headers) {
    $r = ViaDotNet $url $headers
    if ($r.status -eq 0) {
        $c = ViaCurl $url $headers
        if ($c.status -ne 0) {
            Anotar "         (.NET falhou: $($r.erro))"
            Anotar "         (curl.exe conseguiu -- o bloqueio e na pilha do .NET/proxy)"
            return $c
        }
        if ($c.erro) { $r.erro = "$($r.erro) || curl: $($c.erro)" }
    }
    return $r
}

Anotar "============================================================"
Anotar " HIPO - descoberta da API LeadCNPJ (v2)"
Anotar " $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
Anotar " PowerShell $($PSVersionTable.PSVersion)"
Anotar " Base: $BaseUrl"
Anotar "============================================================"
Anotar ""

# ---------------------------------------------------------------------------
Anotar "PASSO 0 - diagnostico de rede"
Anotar ""

$host_ = ([Uri] $BaseUrl).Host

# DNS
try {
    $ips = [Net.Dns]::GetHostAddresses($host_) | ForEach-Object { $_.IPAddressToString }
    Anotar "  DNS  $host_ -> $($ips -join ', ')"
} catch {
    Anotar "  DNS  $host_ -> FALHOU: $($_.Exception.Message)"
    Anotar "       Sem DNS, nada mais vai funcionar. Costuma ser VPN, DNS"
    Anotar "       corporativo ou filtro de rede."
}

# Porta 443
try {
    $tcp = New-Object Net.Sockets.TcpClient
    $async = $tcp.BeginConnect($host_, 443, $null, $null)
    $abriu = $async.AsyncWaitHandle.WaitOne(8000, $false)
    if ($abriu -and $tcp.Connected) {
        Anotar "  TCP  ${host_}:443 -> conectou"
        $tcp.EndConnect($async)
    } else {
        Anotar "  TCP  ${host_}:443 -> NAO conectou (timeout de 8s)"
    }
    $tcp.Close()
} catch {
    Anotar "  TCP  ${host_}:443 -> FALHOU: $($_.Exception.Message)"
}

# Proxy configurado no sistema (a causa mais comum de status 0 com DNS ok).
try {
    $proxy = [Net.WebRequest]::GetSystemWebProxy().GetProxy([Uri] $BaseUrl)
    if ($proxy.AbsoluteUri -ne "$BaseUrl/" -and $proxy.Host -ne $host_) {
        Anotar "  PROXY o sistema manda este trafego por: $($proxy.AbsoluteUri)"
        Anotar "        (e um proxy que pode estar recusando ou exigindo auth)"
    } else {
        Anotar "  PROXY nenhum configurado para este destino"
    }
} catch {
    Anotar "  PROXY nao consegui verificar: $($_.Exception.Message)"
}

# CONTROLE: se a BrasilAPI responde e a LeadCNPJ nao, o problema e do
# destino. Se nenhuma das duas responde, o problema e da sua saida.
Anotar ""
Anotar "  Controle (BrasilAPI, publica e sem chave):"
$controle = Chamar "https://brasilapi.com.br/api/cnpj/v1/$Cnpj" @{ "Accept" = "application/json" }
Anotar "    status $($controle.status) via $($controle.via)"
if ($controle.erro) { Anotar "    erro: $(Mascarar $controle.erro)" }

Anotar ""
Anotar "  Alvo (LeadCNPJ, so a home, sem chave):"
$alvo = Chamar "https://$host_/" @{}
Anotar "    status $($alvo.status) via $($alvo.via)"
if ($alvo.erro) { Anotar "    erro: $(Mascarar $alvo.erro)" }

Anotar ""
if ($controle.status -eq 200 -and $alvo.status -eq 0) {
    Anotar "  LEITURA: a internet esta ok (a BrasilAPI respondeu) e o dominio"
    Anotar "  leadcnpj.com.br especificamente nao responde desta maquina."
    Anotar "  Suspeitos: antivirus com inspecao de HTTPS, firewall corporativo"
    Anotar "  ou instabilidade do lado deles."
} elseif ($controle.status -eq 0 -and $alvo.status -eq 0) {
    Anotar "  LEITURA: nenhum dos dois respondeu. O bloqueio e na saida desta"
    Anotar "  maquina (proxy, antivirus, VPN), nao na LeadCNPJ."
} elseif ($alvo.status -ne 0) {
    Anotar "  LEITURA: o dominio responde. Se as consultas abaixo derem 401 ou"
    Anotar "  404, ai sim e questao de header ou de caminho."
}

if ($alvo.status -eq 0 -and $controle.status -eq 0) {
    Anotar ""
    Anotar "  Parando aqui: sem conectividade, testar caminho e header nao"
    Anotar "  diz nada. Resolva a saida de rede e rode de novo."
    Mascarar ($linhas -join [Environment]::NewLine) |
        Set-Content -Path "$Saida\resumo.txt" -Encoding UTF8
    Write-Host ""
    Write-Host "Resumo em $Saida\resumo.txt" -ForegroundColor Cyan
    exit 0
}

# ---------------------------------------------------------------------------
if (-not $Chave) {
    Write-Host ""
    $segura = Read-Host -AsSecureString "Cole a chave da API da LeadCNPJ (Enter pula o passo 2)"
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try { $Chave = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
$Chave = $Chave.Trim()

Anotar ""
Anotar "PASSO 1 - especificacao OpenAPI (nao gasta credito)"
Anotar ""

$spec = $null
$caminhosDaSpec = @()
foreach ($url in @(
    "$BaseUrl/openapi.json", "$BaseUrl/docs/openapi.json",
    "$BaseUrl/swagger.json", "$BaseUrl/v1/openapi.json",
    "https://$host_/openapi.json", "$BaseUrl/docs"
)) {
    $h = @{ "Accept" = "application/json" }
    if ($Chave) { $h["Authorization"] = "Bearer $Chave" }
    $r = Chamar $url $h
    $marca = if ($r.status -eq 200) { "OK " } else { "-- " }
    Anotar "  $marca $($r.status.ToString().PadLeft(3))  $url"
    if ($r.erro) { Anotar "        $(Mascarar $r.erro)" }

    if ($r.status -eq 200 -and $r.corpo -match '"(openapi|swagger)"') {
        $spec = $r.corpo
        Mascarar $r.corpo | Set-Content -Path "$Saida\openapi.json" -Encoding UTF8
        Anotar "        spec salva em $Saida\openapi.json"
        break
    }
}

if ($spec) {
    try {
        $obj = $spec | ConvertFrom-Json
        $caminhosDaSpec = @($obj.paths.PSObject.Properties.Name)
        Anotar ""
        Anotar "  Endpoints declarados:"
        foreach ($p in $caminhosDaSpec) { Anotar "    $p" }
        if ($obj.components -and $obj.components.securitySchemes) {
            Anotar ""
            Anotar "  Autenticacao declarada:"
            foreach ($nome in $obj.components.securitySchemes.PSObject.Properties.Name) {
                $s = $obj.components.securitySchemes.$nome
                Anotar "    $nome -> type=$($s.type) in=$($s.in) name=$($s.name) scheme=$($s.scheme)"
            }
        }
    } catch {
        Anotar "  (spec baixada mas ilegivel: $($_.Exception.Message))"
    }
}

# ---------------------------------------------------------------------------
if (-not $Chave) {
    Anotar ""
    Anotar "PASSO 2 - pulado (sem chave)"
} else {
    Anotar ""
    Anotar "PASSO 2 - consulta de CNPJ (a primeira que responder 200 gasta credito)"
    Anotar ""

    $caminhos = New-Object System.Collections.Generic.List[string]
    foreach ($p in $caminhosDaSpec) {
        if ($p -match "\{[^}]*(cnpj|document|id)[^}]*\}") {
            $caminhos.Add(($p -replace "\{[^}]+\}", $Cnpj)) | Out-Null
        }
    }
    foreach ($p in @("/empresas/$Cnpj", "/empresa/$Cnpj", "/cnpj/$Cnpj",
                     "/v1/empresas/$Cnpj", "/consulta/$Cnpj")) {
        if (-not $caminhos.Contains($p)) { $caminhos.Add($p) | Out-Null }
    }

    $headersCandidatos = @(
        @{ rotulo = "Authorization: Bearer <chave>"; h = @{ "Authorization" = "Bearer $Chave" } },
        @{ rotulo = "X-API-Key: <chave>";            h = @{ "X-API-Key"     = $Chave } },
        @{ rotulo = "api-key: <chave>";              h = @{ "api-key"       = $Chave } },
        @{ rotulo = "Authorization: <chave>";        h = @{ "Authorization" = $Chave } }
    )

    $acertou = $false
    foreach ($caminho in $caminhos) {
        if ($acertou) { break }
        $url = "$BaseUrl/$($caminho.TrimStart('/'))"
        foreach ($cand in $headersCandidatos) {
            $h = $cand.h.Clone()
            $h["Accept"] = "application/json"
            $r = Chamar $url $h
            Anotar "  $($r.status.ToString().PadLeft(3))  $url   [$($cand.rotulo)]"
            if ($r.erro) { Anotar "        $(Mascarar $r.erro)" }
            if ($r.status -ge 400 -and $r.corpo) {
                $trecho = ($r.corpo -replace '\s+', ' ')
                if ($trecho.Length -gt 200) { $trecho = $trecho.Substring(0, 200) + "..." }
                Anotar "        corpo: $(Mascarar $trecho)"
            }

            if ($r.status -eq 200) {
                Anotar ""
                Anotar "  ACERTOU."
                Anotar "    URL    : $url"
                Anotar "    Header : $($cand.rotulo)"
                Mascarar $r.corpo | Set-Content -Path "$Saida\resposta.json" -Encoding UTF8
                Anotar "    JSON salvo em $Saida\resposta.json"
                try {
                    $dados = $r.corpo | ConvertFrom-Json
                    Anotar ""
                    Anotar "  Campos do primeiro nivel:"
                    foreach ($prop in $dados.PSObject.Properties) {
                        $v = $prop.Value
                        $tipo = if ($null -eq $v) { "null" }
                                elseif ($v -is [Array]) { "array[$($v.Count)]" }
                                elseif ($v -is [PSCustomObject]) { "objeto" }
                                else { $v.GetType().Name }
                        $amostra = ""
                        if ($tipo -ne "objeto" -and $tipo -notlike "array*" -and $null -ne $v) {
                            $amostra = " = " + ([string] $v)
                            if ($amostra.Length -gt 70) { $amostra = $amostra.Substring(0, 70) + "..." }
                        }
                        Anotar ("    {0,-34} {1}{2}" -f $prop.Name, $tipo, $amostra)
                    }
                    Anotar ""
                    $achou = $false
                    foreach ($prop in $dados.PSObject.Properties) {
                        if ($prop.Name -match "funcion|employee|colaborad|porte|size") {
                            Anotar "  >> NUMERO DE PESSOAS: $($prop.Name) = $($prop.Value)"
                            $achou = $true
                        }
                    }
                    if (-not $achou) {
                        Anotar "  >> Nenhum campo de funcionarios no primeiro nivel."
                        Anotar "     Pode estar aninhado - o resposta.json mostra."
                    }
                } catch {
                    Anotar "  (resposta salva, mas nao era JSON interpretavel)"
                }
                $acertou = $true
                break
            }

            if ($r.status -eq 429) {
                Anotar "        limite de requisicoes - esperando 20s"
                Start-Sleep -Seconds 20
            }
            Start-Sleep -Milliseconds 2000
        }
    }

    if (-not $acertou) {
        Anotar ""
        Anotar "  Nenhuma combinacao respondeu 200. Com os status acima:"
        Anotar "    401/403 -> o caminho existe, o header e outro"
        Anotar "    404     -> o caminho e outro (veja o painel deles)"
        Anotar "    0       -> ainda e rede, nao e a API"
    }
}

Anotar ""
Anotar "============================================================"
Anotar " Arquivos em: $((Resolve-Path $Saida).Path)"
Anotar " A chave NAO esta em nenhum deles."
Anotar "============================================================"

Mascarar ($linhas -join [Environment]::NewLine) |
    Set-Content -Path "$Saida\resumo.txt" -Encoding UTF8
