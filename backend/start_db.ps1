# Starts the local Postgres (pgvector) on its own, outside the API process.
# Run once after a reboot, BEFORE starting the API:
#   powershell -File law-chatbot-reel\backend\start_db.ps1
# (When Postgres is started from inside the API's server process, Windows
#  refuses to start its worker processes: error 0xC0000142.)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$bin  = Join-Path $root ".venv\Lib\site-packages\pgserver\pginstall\bin"
$data = Join-Path $root "pgdata"
$port = 54041

& "$bin\pg_isready.exe" -h 127.0.0.1 -p $port | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "Postgres already running on $port"; exit 0 }

Start-Process -FilePath "$bin\pg_ctl.exe" -WindowStyle Hidden -ArgumentList @(
  '-D', "`"$data`"", '-o', "`"-h 127.0.0.1 -p $port`"", '-l', "`"$data\log`"", 'start')

for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  & "$bin\pg_isready.exe" -h 127.0.0.1 -p $port | Out-Null
  if ($LASTEXITCODE -eq 0) { Write-Host "Postgres ready on $port"; exit 0 }
}
Write-Error "Postgres did not start; see $data\log"
