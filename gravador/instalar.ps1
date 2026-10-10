# HIPO Gravador - instalador (Windows 10/11).
#
# Grava as ligacoes do Vivo Voz Negocio e manda para o HIPO, que transcreve
# e coloca cada ligacao na oportunidade.
#
# Uso (PowerShell, na pasta do gravador, SEM precisar de administrador):
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1 -Token hipograv_xxx
#
# O token sai do HIPO: Perfil > Gravador de ligacoes > Gerar token.
#
# O que faz:
#   1. acha (ou instala, com a sua confirmacao) o Python 3.10+;
#   2. copia o programa para %LOCALAPPDATA%\HIPO Gravador\programa;
#   3. cria um ambiente Python so dele e instala as bibliotecas;
#   4. grava o endereco do HIPO e o token;
#   5. testa (HIPO, microfone, saida de audio, softphone);
#   6. agenda para abrir sozinho a cada logon e abre agora.
#
# Arquivo so com ASCII de proposito: o PowerShell 5.1 le .ps1 sem BOM como
# ANSI, e acento vira lixo no meio do script.

param(
  [string]$Token = "",
  [string]$Url = "https://hipogestao.com.br/api",
  [switch]$SemTarefa
)

$ErrorActionPreference = "Stop"
$base = Join-Path $env:LOCALAPPDATA "HIPO Gravador"
$destino = Join-Path $base "programa"
$venv = Join-Path $base "venv"
$nomeTarefa = "HIPO Gravador"

function Passo($texto) { Write-Host ""; Write-Host "== $texto ==" -ForegroundColor Cyan }
function Falha($texto) { Write-Host $texto -ForegroundColor Red; Read-Host "Enter para sair" | Out-Null; exit 1 }

function Achar-Python {
  $candidatos = @(
    @("py", "-3.12"), @("py", "-3.13"), @("py", "-3.11"), @("py", "-3.10"), @("python", $null), @("python3", $null)
  )
  foreach ($c in $candidatos) {
    $exe = $c[0]; $arg = $c[1]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
      if ($arg) { $v = & $exe $arg -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null }
      else { $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null }
    } catch { continue }
    if (-not $v -or $v.Count -lt 2) { continue }
    $partes = $v[0].Split(".")
    $maior = [int]$partes[0]; $menor = [int]$partes[1]
    if ($maior -eq 3 -and $menor -ge 10 -and $menor -le 13) { return $v[1] }
  }
  return $null
}

Write-Host "HIPO Gravador - instalacao" -ForegroundColor Green

# ---------------------------------------------------------------- Python
Passo "Python"
$py = Achar-Python
if (-not $py) {
  Write-Host "  Nao achei Python 3.10 a 3.13 nesta maquina."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    $r = Read-Host "  Instalar o Python 3.12 agora pelo winget (so para este usuario)? [s/N]"
    if ($r.Trim().ToLower() -ne "s") { Falha "Instale o Python 3.12 (python.org) e rode de novo." }
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $py = Achar-Python
  }
  if (-not $py) { Falha "Instale o Python 3.12 (python.org, marque 'Add to PATH') e rode de novo." }
}
Write-Host "  ok: $py"

# ---------------------------------------------------------------- Parar o que estiver rodando
$tarefa = Get-ScheduledTask -TaskName $nomeTarefa -ErrorAction SilentlyContinue
if ($tarefa) {
  Stop-ScheduledTask -TaskName $nomeTarefa -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*hipo_gravador.pyw*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------- Copiar
Passo "Copiando o programa"
$origem = $PSScriptRoot
if (-not (Test-Path (Join-Path $origem "hipo_gravador.pyw"))) { Falha "Rode este script de dentro da pasta do gravador." }
New-Item -ItemType Directory -Force -Path $destino | Out-Null
if (Test-Path (Join-Path $destino "app")) { Remove-Item -Recurse -Force (Join-Path $destino "app") }
Copy-Item -Recurse -Force (Join-Path $origem "app") (Join-Path $destino "app")
Copy-Item -Force (Join-Path $origem "hipo_gravador.pyw") $destino
Copy-Item -Force (Join-Path $origem "requirements.txt") $destino
Copy-Item -Force (Join-Path $origem "desinstalar.ps1") $destino
Write-Host "  ok: $destino"

# ---------------------------------------------------------------- Ambiente
Passo "Bibliotecas (pode levar 1 a 2 minutos)"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  & $py -m venv $venv
  if ($LASTEXITCODE -ne 0) { Falha "Nao foi possivel criar o ambiente Python em $venv." }
}
$vpy = Join-Path $venv "Scripts\python.exe"
$vpyw = Join-Path $venv "Scripts\pythonw.exe"
& $vpy -m pip install --quiet --disable-pip-version-check --upgrade pip
& $vpy -m pip install --quiet --disable-pip-version-check -r (Join-Path $destino "requirements.txt")
if ($LASTEXITCODE -ne 0) { Falha "A instalacao das bibliotecas falhou (veja a mensagem acima)." }
Write-Host "  ok"

# ---------------------------------------------------------------- Token
Passo "Ligacao com o HIPO"
$script = Join-Path $destino "hipo_gravador.pyw"
$cfg = Join-Path $env:APPDATA "HIPO Gravador\config.json"
if (-not $Token -and (Test-Path $cfg)) {
  $r = Read-Host "  Ja existe configuracao. Manter o token atual? [S/n]"
  if ($r.Trim().ToLower() -eq "n") { $Token = Read-Host "  Cole o token do gravador (Perfil > Gravador de ligacoes)" }
} elseif (-not $Token) {
  $Token = Read-Host "  Cole o token do gravador (Perfil > Gravador de ligacoes)"
}
if ($Token) {
  & $vpy $script --configurar $Url $Token.Trim()
  if ($LASTEXITCODE -ne 0) { Falha "Token invalido." }
}

# ---------------------------------------------------------------- Teste
Passo "Teste"
& $vpy $script --testar
if ($LASTEXITCODE -ne 0) {
  Write-Host "  O teste apontou problema (acima). O gravador sera instalado mesmo assim." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- Abrir no logon
if (-not $SemTarefa) {
  Passo "Abrir sozinho a cada logon"
  $acao = New-ScheduledTaskAction -Execute $vpyw -Argument ('"' + $script + '"') -WorkingDirectory $destino
  $gatilho = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
  $quem = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  try {
    Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho -Settings $ajustes `
      -Principal $quem -Description "Grava as ligacoes do Vivo Voz Negocio para o HIPO" -Force | Out-Null
    Start-ScheduledTask -TaskName $nomeTarefa
    Write-Host "  ok: tarefa '$nomeTarefa' criada e iniciada"
  } catch {
    # Sem permissao para tarefa agendada: atalho na pasta Inicializar.
    $startup = [Environment]::GetFolderPath("Startup")
    $lnk = Join-Path $startup "HIPO Gravador.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $atalho = $ws.CreateShortcut($lnk)
    $atalho.TargetPath = $vpyw
    $atalho.Arguments = '"' + $script + '"'
    $atalho.WorkingDirectory = $destino
    $atalho.Save()
    Start-Process -FilePath $vpyw -ArgumentList ('"' + $script + '"') -WorkingDirectory $destino
    Write-Host "  ok: atalho em Inicializar (sem tarefa agendada: $($_.Exception.Message))"
  }
}

Write-Host ""
Write-Host "Pronto. Procure o icone verde do HIPO Gravador perto do relogio." -ForegroundColor Green
Write-Host "Vermelho = gravando. Clique com o botao direito para pausar (ligacao pessoal)."
Write-Host "Diario: $base\gravador.log"
Read-Host "Enter para fechar" | Out-Null
