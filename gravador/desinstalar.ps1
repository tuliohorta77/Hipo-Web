# HIPO Gravador - desinstalador.
#
# Uso: powershell -ExecutionPolicy Bypass -File .\desinstalar.ps1
#
# Para o gravador, tira do logon e apaga o programa e o ambiente Python.
# Gravacoes que ainda estao na fila (nao chegaram ao HIPO) sao mostradas
# antes, e so sao apagadas com confirmacao.
# Arquivo so com ASCII (ver instalar.ps1).

$ErrorActionPreference = "Continue"
$base = Join-Path $env:LOCALAPPDATA "HIPO Gravador"
$nomeTarefa = "HIPO Gravador"

Stop-ScheduledTask -TaskName $nomeTarefa -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $nomeTarefa -Confirm:$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*hipo_gravador.pyw*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "HIPO Gravador.lnk"
if (Test-Path $lnk) { Remove-Item -Force $lnk }

$fila = Join-Path $base "fila"
$pendentes = @(Get-ChildItem -Path $fila -Filter "*.flac" -ErrorAction SilentlyContinue)
if ($pendentes.Count -gt 0) {
  Write-Host "Ha $($pendentes.Count) gravacao(oes) que ainda nao chegaram ao HIPO em $fila" -ForegroundColor Yellow
  $r = Read-Host "Apagar essas gravacoes tambem? [s/N]"
  if ($r.Trim().ToLower() -ne "s") {
    Remove-Item -Recurse -Force (Join-Path $base "programa"), (Join-Path $base "venv") -ErrorAction SilentlyContinue
    Write-Host "Programa removido. A fila ficou em $fila."
    exit 0
  }
}
Remove-Item -Recurse -Force $base -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $env:APPDATA "HIPO Gravador") -ErrorAction SilentlyContinue
Write-Host "HIPO Gravador removido. Revogue o token no HIPO (Perfil > Gravador de ligacoes)."
