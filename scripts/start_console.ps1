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
  $gisPython = Join-Path $gisPrefix "python.exe"
  $gdalData = Join-Path $gisPrefix "Library\share\gdal"
  $projLib = Join-Path $gisPrefix "Library\share\proj"
  $gisBin = Join-Path $gisPrefix "Library\bin"
  if (-not (Test-Path -LiteralPath $gisPython)) {
    throw "GIS Python environment was not found: $gisPython"
  }
  if (-not (Test-Path -LiteralPath $gdalData)) {
    throw "GDAL data directory was not found: $gdalData"
  }
  if (-not (Test-Path -LiteralPath $projLib)) {
    throw "PROJ data directory was not found: $projLib"
  }
  $env:GDAL_DATA = Join-Path $gisPrefix "Library\share\gdal"
  $env:PROJ_LIB = Join-Path $gisPrefix "Library\share\proj"
  $env:PATH = "$gisBin;$gisPrefix;$env:PATH"
  # Use the environment's interpreter directly. This preserves the GDAL/PROJ
  # variables in the service process and avoids conda run losing shell state.
  & $gisPython serve_api.py --host $HostName --port $Port
} else {
  & "C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe" serve_api.py --host $HostName --port $Port
}
