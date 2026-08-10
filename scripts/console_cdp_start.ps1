param(
  [int]$Port = 9222,
  [string]$ConsoleUrl = "http://127.0.0.1:8088/",
  [int]$WaitSeconds = 15
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
  Write-Output ("Chrome CDP 已存在，复用端口 {0}：{1}" -f $Port, $existing.Browser)
  Write-Output ("Console：{0}" -f $ConsoleUrl)
  exit 0
}

$chromeCandidates = @(
  (Join-Path ${env:ProgramFiles} "Google\Chrome\Application\chrome.exe"),
  (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
  (Join-Path ${env:LocalAppData} "Google\Chrome\Application\chrome.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if (-not $chromeCandidates) {
  throw "未找到 Chrome。请安装 Google Chrome，或手动以 --remote-debugging-port=$Port 启动。"
}
$chromePath = [string]($chromeCandidates | Select-Object -First 1)

# 独立临时 profile，避免接管或修改用户正在使用的 Chrome profile。
$profile = Join-Path ([IO.Path]::GetTempPath()) ("spatial-agent-cdp-{0}" -f ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Path $profile -Force | Out-Null
$arguments = @(
  "--remote-debugging-port=$Port",
  "--remote-allow-origins=*",
  "--user-data-dir=$profile",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-popup-blocking",
  $ConsoleUrl
)
$process = Start-Process -FilePath $chromePath -ArgumentList $arguments -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$version = $null
while ((Get-Date) -lt $deadline) {
  $version = Get-CdpVersion
  if ($version) { break }
  if ($process.HasExited) {
    throw "Chrome CDP 进程已退出，PID=$($process.Id)。"
  }
  Start-Sleep -Milliseconds 250
}
if (-not $version) {
  throw "Chrome CDP 在 $WaitSeconds 秒内未监听 127.0.0.1:$Port。请检查端口占用或 Chrome 启动日志。"
}

Write-Output ("Chrome CDP 已启动：PID={0}，端口={1}" -f $process.Id, $Port)
Write-Output ("独立 profile：{0}" -f $profile)
Write-Output ("Console：{0}" -f $ConsoleUrl)
