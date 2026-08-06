param(
  [ValidateSet("memory", "gis")]
  [string]$Mode = "memory",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8088
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Stop-Process -Id $existing.OwningProcess -Force
}

if ($Mode -eq "gis") {
  $gisPrefix = "C:\Users\torch\.conda\envs\spatial-agent-gis"
  $env:GDAL_DATA = Join-Path $gisPrefix "Library\share\gdal"
  $env:PROJ_LIB = Join-Path $gisPrefix "Library\share\proj"
  & "D:\code\conda\Scripts\conda.exe" run --no-capture-output -n spatial-agent-gis python serve_api.py --host $HostName --port $Port
} else {
  & "C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe" serve_api.py --host $HostName --port $Port
}
