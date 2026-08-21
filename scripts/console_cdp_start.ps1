param(
  [int]$Port = 9222,
  [string]$ConsoleUrl = "http://127.0.0.1:8088/",
  [int]$WaitSeconds = 15,
  [switch]$Headless
)

$ErrorActionPreference = "Stop"

function Get-CdpVersion {
  try {
    return Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json/version" -f $Port) -TimeoutSec 2
  } catch {
    return $null
  }
}

$existing = Get-CdpVersion
if ($existing) {
  Write-Output ("Chrome CDP already running on port {0}: {1}" -f $Port, $existing.Browser)
  Write-Output ("Console: {0}" -f $ConsoleUrl)
  exit 0
}

$chromeCandidates = @(
  (Join-Path ${env:ProgramFiles} "Google\Chrome\Application\chrome.exe"),
  (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
  (Join-Path ${env:LocalAppData} "Google\Chrome\Application\chrome.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if (-not $chromeCandidates) {
  throw "Chrome was not found. Install Google Chrome or start it with --remote-debugging-port=$Port."
}
$chromePath = [string]($chromeCandidates | Select-Object -First 1)

# 独立临时 profile，避免接管或修改用户正在使用的 Chrome profile。
$tempRoot = [IO.Path]::GetTempPath()
$cdpProfile = [IO.Path]::Combine($tempRoot, "spatial-agent-cdp-" + ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Path $cdpProfile -Force | Out-Null
$arguments = @(
  "--remote-debugging-port=$Port",
  "--remote-allow-origins=*",
  "--user-data-dir=$cdpProfile",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-popup-blocking",
  $ConsoleUrl
)
if ($Headless) {
  $arguments = @("--headless=new", "--disable-gpu", "--no-sandbox") + $arguments
}
$process = Start-Process -FilePath $chromePath -ArgumentList $arguments -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$version = $null
while ((Get-Date) -lt $deadline) {
  $version = Get-CdpVersion
  if ($version) { break }
  if ($process.HasExited) {
    throw "Chrome CDP process exited, PID=$($process.Id)."
  }
  Start-Sleep -Milliseconds 250
}
if (-not $version) {
  throw "Chrome CDP did not listen on 127.0.0.1:$Port within $WaitSeconds seconds."
}

Write-Output ("Chrome CDP started: PID={0}, port={1}" -f $process.Id, $Port)
Write-Output ("Isolated profile: {0}" -f $cdpProfile)
Write-Output ("Console: {0}" -f $ConsoleUrl)
