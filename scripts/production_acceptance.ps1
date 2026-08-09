param(
  [string]$BaseUrl = "http://127.0.0.1:8088",
  [int]$PollLimit = 60
)

$ErrorActionPreference = "Stop"

function Get-Json($url) {
  return Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 5
}

$live = Get-Json "$BaseUrl/health/live"
$ready = Get-Json "$BaseUrl/health/ready"
$capabilityCatalog = Get-Json "$BaseUrl/capabilities"
if ($live.status -ne "ok") { throw "liveness failed" }
if ($ready.status -ne "ready") { throw "readiness failed: $($ready.status)" }
if ($capabilityCatalog.version -ne "1.0" -or @($capabilityCatalog.capabilities).Count -lt 1) { throw "capability catalog failed" }

$sessionId = "production-acceptance-" + [guid]::NewGuid().ToString("N")
$greeting = ([char]0x4F60) + ([char]0x597D)
$payload = @{ request = $greeting; session_id = $sessionId; planner = "rule"; backend = "memory" } | ConvertTo-Json
$payloadBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
$queued = Invoke-RestMethod -Method Post -Uri "$BaseUrl/runs/async" -ContentType "application/json; charset=utf-8" -Body $payloadBytes -TimeoutSec 5
if (-not $queued.run_id -or $queued.status -ne "QUEUED") { throw "async submission failed" }

$final = $null
for ($index = 0; $index -lt $PollLimit; $index++) {
  Start-Sleep -Milliseconds 200
  $candidate = Get-Json "$BaseUrl/runs/$($queued.run_id)?planner=rule&backend=memory"
  if ($candidate.status -notin @("PLANNING", "EXECUTING", "CREATED", "QUEUED")) {
    $final = $candidate
    break
  }
}
if ($null -eq $final) { throw "async run did not reach a terminal state" }
if ($final.status -ne "COMPLETED") { throw "async run failed: $($final.error)" }

[pscustomobject]@{
  status = "ok"
  liveness = $live.status
  readiness = $ready.status
  capability_count = @($capabilityCatalog.capabilities).Count
  async_status = $final.status
  run_id = $queued.run_id
} | ConvertTo-Json -Compress
