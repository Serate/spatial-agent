param(
  [string]$BaseUrl = "http://127.0.0.1:8088",
  [int]$PollLimit = 60
)

$ErrorActionPreference = "Stop"

function Get-Json($url) {
  return Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 5
}

function Assert-RuntimeCapabilitySnapshot($snapshot) {
  if ($null -eq $snapshot) { throw "runtime capability snapshot is empty" }
  if ($snapshot.version -ne "1.0") { throw "runtime capability version mismatch: $($snapshot.version)" }
  if ([string]::IsNullOrWhiteSpace([string]$snapshot.environment)) { throw "runtime capability environment missing" }
  if ($snapshot.health_status -notin @("ready", "degraded", "unavailable", "unknown")) {
    throw "runtime capability health_status invalid: $($snapshot.health_status)"
  }

  $capabilities = @($snapshot.capabilities)
  if ($capabilities.Count -lt 1) { throw "runtime capability list is empty" }
  foreach ($capability in $capabilities) {
    if ([string]::IsNullOrWhiteSpace([string]$capability.id)) {
      throw "runtime capability id missing"
    }
    if ($null -eq $capability.runtime_evidence -or $null -eq $capability.runtime_evidence.datasets) {
      throw "runtime evidence missing for capability: $($capability.id)"
    }
  }

  # An unavailable config is a supported deployment state. Healthy/degraded
  # snapshots must carry the timestamp and per-dataset evidence fields.
  if ($snapshot.health_status -ne "unavailable") {
    if ([string]::IsNullOrWhiteSpace([string]$snapshot.updated_at)) {
      throw "runtime capability updated_at missing"
    }
    if ($null -eq $snapshot.data_evidence) { throw "runtime capability data_evidence missing" }
  }
}

function Get-DatasetEvidence($snapshot, [string]$dataset) {
  if ($null -eq $snapshot.data_evidence) {
    throw "runtime dataset evidence is missing"
  }
  $property = $snapshot.data_evidence.PSObject.Properties[$dataset]
  if ($null -eq $property -or $null -eq $property.Value) {
    throw "runtime dataset evidence missing: $dataset"
  }
  $evidence = $property.Value
  if ([string]::IsNullOrWhiteSpace([string]$evidence.status)) {
    throw "runtime dataset status missing: $dataset"
  }
  if ($null -eq $evidence.file_count -or $null -eq $evidence.checked_files) {
    throw "runtime dataset file metrics missing: $dataset"
  }
  return $evidence
}

function Assert-DataVolumeHealth($snapshot) {
  $coreDatasets = @("admin_areas", "dem", "land_use")
  $optionalDatasets = @("roads", "water")
  $coreMissing = @()
  $optionalMissing = @()
  $evidenceByDataset = @{}

  foreach ($dataset in $coreDatasets) {
    $evidence = Get-DatasetEvidence $snapshot $dataset
    $evidenceByDataset[$dataset] = $evidence
    if ($evidence.status -eq "unavailable" -or [int]$evidence.checked_files -lt 1) {
      $coreMissing += $dataset
    }
  }
  foreach ($dataset in $optionalDatasets) {
    $evidence = Get-DatasetEvidence $snapshot $dataset
    $evidenceByDataset[$dataset] = $evidence
    if ($evidence.status -eq "unavailable" -or [int]$evidence.checked_files -lt 1) {
      $optionalMissing += $dataset
    }
  }

  # Core data is required for a meaningful production GIS acceptance. Roads
  # and water are optional capabilities and remain an explicit reported gap.
  if ($coreMissing.Count -gt 0) {
    throw "core data volume is unavailable: $($coreMissing -join ', ')"
  }

  $coreHealth = [string]$snapshot.core_health_status
  if ($coreHealth -notin @("ready", "degraded")) {
    throw "core data health is not usable: $coreHealth"
  }

  $optionalHealth = [string]$snapshot.optional_health_status
  if ($optionalHealth -notin @("ready", "degraded", "unavailable", "unknown")) {
    throw "optional data health is invalid: $optionalHealth"
  }

  return [pscustomobject]@{
    core_health = $coreHealth
    optional_health = $optionalHealth
    core_missing = @($coreMissing)
    optional_missing = @($optionalMissing)
    status = if ($optionalMissing.Count -gt 0) { "core_ready_optional_partial" } else { "ready" }
  }
}

$live = Get-Json "$BaseUrl/health/live"
$ready = Get-Json "$BaseUrl/health/ready"
$capabilityCatalog = Get-Json "$BaseUrl/capabilities"
$runtimeCapabilities = Get-Json "$BaseUrl/capabilities/runtime?max_files=1"
if ($live.status -ne "ok") { throw "liveness failed" }
if ($ready.status -ne "ready") { throw "readiness failed: $($ready.status)" }
if ($capabilityCatalog.version -ne "1.0" -or @($capabilityCatalog.capabilities).Count -lt 1) { throw "capability catalog failed" }
Assert-RuntimeCapabilitySnapshot $runtimeCapabilities
$dataVolume = Assert-DataVolumeHealth $runtimeCapabilities

$sessionId = "production-acceptance-" + [guid]::NewGuid().ToString("N")
$greeting = ([char]0x4F60) + ([char]0x597D)
$payload = @{ request = $greeting; session_id = $sessionId; planner = "rule"; backend = "memory" } | ConvertTo-Json
$payloadBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
$queued = Invoke-RestMethod -Method Post -Uri "$BaseUrl/runs/async" -ContentType "application/json; charset=utf-8" -Body $payloadBytes -TimeoutSec 5
if (-not $queued.run_id -or $queued.status -ne "QUEUED") { throw "async submission failed" }
$duplicate = Invoke-RestMethod -Method Post -Uri "$BaseUrl/runs/async" -ContentType "application/json; charset=utf-8" -Body $payloadBytes -TimeoutSec 5
if ($duplicate.run_id -ne $queued.run_id -or -not $duplicate.idempotent) { throw "async duplicate submission was not idempotent" }

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
  runtime_health = $runtimeCapabilities.health_status
  data_volume_status = $dataVolume.status
  core_data_health = $dataVolume.core_health
  optional_data_health = $dataVolume.optional_health
  core_missing_datasets = @($dataVolume.core_missing)
  optional_missing_datasets = @($dataVolume.optional_missing)
  runtime_capability_count = @($runtimeCapabilities.capabilities).Count
  runtime_updated_at = $runtimeCapabilities.updated_at
  async_status = $final.status
  async_duplicate_idempotent = $duplicate.idempotent
  run_id = $queued.run_id
} | ConvertTo-Json -Compress
