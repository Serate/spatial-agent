param(
  [string]$BaseUrl = "http://127.0.0.1:8088",
  [int]$PollLimit = 60,
  [string]$ContractPayloadPath = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

function Get-Json($url) {
  # The first GIS capability snapshot may initialize GDAL/PROJ and inspect
  # real mounted datasets.  Keep the acceptance bounded, but allow a cold
  # production container enough time to complete that one-time work.
  return Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 30
}

function Post-Json($url, $body) {
  $payload = $body | ConvertTo-Json -Depth 12
  $payloadBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
  return Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json; charset=utf-8" -Body $payloadBytes -TimeoutSec 10
}

function Post-JsonExpectError($url, $body) {
  $payload = $body | ConvertTo-Json -Depth 12
  $client = New-Object System.Net.Http.HttpClient
  try {
    $contentObject = New-Object System.Net.Http.StringContent($payload, [System.Text.Encoding]::UTF8, "application/json")
    $response = $client.PostAsync($url, $contentObject).GetAwaiter().GetResult()
    $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if ([int]$response.StatusCode -lt 400) {
      throw "request unexpectedly succeeded"
    }
    return [pscustomobject]@{
      status_code = [int]$response.StatusCode
      payload = $content | ConvertFrom-Json
    }
  } finally {
    $client.Dispose()
  }
}

function Resolve-ContractHarnessPython {
  $configured = [string]$env:SPATIAL_AGENT_PYTHON
  $candidates = @()
  if (-not [string]::IsNullOrWhiteSpace($configured)) {
    $candidates += [Environment]::ExpandEnvironmentVariables($configured.Trim())
  }

  # ``python`` may resolve to the WindowsApps Store alias.  It exits without
  # a useful diagnostic on some hosts, so enumerate real python.exe entries
  # and probe them before running the contract checker.
  $commands = @(Get-Command python.exe -All -ErrorAction SilentlyContinue)
  foreach ($command in $commands) {
    if (-not [string]::IsNullOrWhiteSpace([string]$command.Source)) {
      $candidates += [string]$command.Source
    }
  }

  $seen = @{}
  foreach ($candidate in $candidates) {
    $path = [string]$candidate
    if ([string]::IsNullOrWhiteSpace($path)) { continue }
    $key = $path.ToLowerInvariant()
    if ($seen.ContainsKey($key)) { continue }
    $seen[$key] = $true
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    if ($path -match '(?i)[\\/]WindowsApps[\\/]') { continue }
    $probe = @(& $path -c "import sys; print(sys.executable)" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $probe.Count -gt 0) {
      return $path
    }
  }

  if (-not [string]::IsNullOrWhiteSpace($configured)) {
    throw "no runnable Python found for SPATIAL_AGENT_PYTHON=$configured"
  }
  throw "no runnable Python found; set SPATIAL_AGENT_PYTHON to a Python executable"
}

function Invoke-ContractHarness($payloads, [string]$surface) {
  if ($null -eq $payloads -or @($payloads).Count -lt 2) {
    throw "$surface contract comparison requires at least two payloads"
  }
  $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("spatial-agent-contract-" + [guid]::NewGuid().ToString("N") + ".json")
  try {
    $json = ConvertTo-Json -InputObject @($payloads) -Depth 50 -Compress
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempPath, $json, $utf8)
    $python = Resolve-ContractHarnessPython
    $checker = Join-Path $PSScriptRoot "contract_harness_check.py"
    $output = @(& $python $checker --input $tempPath 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
      $details = ($output | Out-String).Trim()
      if ([string]::IsNullOrWhiteSpace($details)) {
        $details = "checker exited without output"
      }
      throw "$surface contract harness failed (python=$python, exit_code=$exitCode): $details"
    }
    $report = ($output -join "`n") | ConvertFrom-Json
    if ($null -eq $report -or $report.status -ne "ok") {
      throw "$surface contract harness returned an invalid report"
    }
    return $report
  } finally {
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
  }
}

function Assert-RuntimeCapabilitySnapshot($snapshot) {
  if ($null -eq $snapshot) { throw "runtime capability snapshot is empty" }
  if ($snapshot.version -ne "1.0") { throw "runtime capability version mismatch: $($snapshot.version)" }
  if ([string]::IsNullOrWhiteSpace([string]$snapshot.environment)) { throw "runtime capability environment missing" }
  if ($snapshot.health_status -notin @("ready", "degraded", "unavailable", "unknown")) {
    throw "runtime capability health_status invalid: $($snapshot.health_status)"
  }
  if ($null -eq $snapshot.tool_provider) {
    throw "runtime tool provider evidence missing"
  }
  if ([string]::IsNullOrWhiteSpace([string]$snapshot.tool_provider.id)) {
    throw "runtime tool provider id missing"
  }
  if ($null -eq $snapshot.tool_provider_health) {
    throw "runtime tool provider health missing"
  }
  if ($snapshot.tool_provider_health.schema_version -ne "spatial-agent.tool-provider-health.v1") {
    throw "runtime tool provider health schema mismatch"
  }
  if ($snapshot.tool_provider_health.status -notin @("ready", "degraded", "unavailable", "unknown")) {
    throw "runtime tool provider health status invalid"
  }
  if ($null -eq $snapshot.tool_provider_health.definition_contract) {
    throw "runtime tool provider definition contract missing"
  }
  if ($snapshot.tool_provider_health.definition_contract.schema_version -ne "spatial-agent.tool-provider-contract.v1") {
    throw "runtime tool provider definition contract schema mismatch"
  }
  if ($snapshot.tool_provider_health.definition_contract.status -ne "valid") {
    throw "runtime tool provider definition contract is not valid"
  }
  if ($null -eq $snapshot.tool_governance) {
    throw "runtime tool governance evidence missing"
  }
  if ($snapshot.tool_governance.schema_version -ne "spatial-agent.tool-governance.v1") {
    throw "runtime tool governance schema mismatch"
  }
  if ([int]$snapshot.tool_provider.tool_count -lt 1) {
    throw "runtime tool provider has no registered tools"
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

function Assert-FailureEvidence($payload, [string]$surface) {
  if ($null -eq $payload -or $payload.status -eq "COMPLETED") { return }
  if ($null -eq $payload.failure) { throw "$surface failure evidence missing" }
  if ($payload.failure.schema_version -ne "spatial-agent.failure.v1") {
    throw "$surface failure schema mismatch"
  }
  if ($payload.failure.status -ne $payload.status) {
    throw "$surface failure status mismatch"
  }
  if ([string]::IsNullOrWhiteSpace([string]$payload.failure.category)) {
    throw "$surface failure category missing"
  }
  if ([string]::IsNullOrWhiteSpace([string]$payload.failure.code)) {
    throw "$surface failure code missing"
  }
  if ($payload.failure.phase -notin @("planning", "execution", "control", "persistence", "unknown")) {
    throw "$surface failure phase invalid"
  }
  if ($null -eq $payload.result -or $null -eq $payload.result.failure) {
    throw "$surface result failure evidence missing"
  }
  if ($payload.result.failure.schema_version -ne "spatial-agent.failure.v1") {
    throw "$surface result failure schema mismatch"
  }
}

function Assert-ReplanningEvidence($payload, [string]$surface) {
  if ($null -eq $payload -or $null -eq $payload.result -or $null -eq $payload.result.replanning) {
    throw "$surface result replanning envelope missing"
  }
  $replanning = $payload.result.replanning
  if ($replanning.schema_version -ne "spatial-agent.replanning.v1") {
    throw "$surface replanning schema mismatch"
  }
  $events = @($replanning.events)
  if ([int]$replanning.count -ne $events.Count) {
    throw "$surface replanning count mismatch"
  }
  if (($replanning.available -eq $true) -ne ($events.Count -gt 0)) {
    throw "$surface replanning availability mismatch"
  }
  foreach ($event in $events) {
    if ([string]::IsNullOrWhiteSpace([string]$event.failed_step_id)) {
      throw "$surface replanning failed step missing"
    }
    if ([string]::IsNullOrWhiteSpace([string]$event.failed_tool)) {
      throw "$surface replanning failed tool missing"
    }
    if ($null -eq $event.replanned_step_ids -or @($event.replanned_step_ids).Count -gt 24) {
      throw "$surface replanning replacement steps invalid"
    }
  }
  if ($null -eq $payload.result.lineage -or $null -eq $payload.result.lineage.replanning) {
    throw "$surface replanning lineage missing"
  }
  if ([int]$payload.result.lineage.replanning.count -ne [int]$replanning.count) {
    throw "$surface replanning lineage count mismatch"
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

function Assert-PlanningEvidence($payload, [string]$surface) {
  if ($null -eq $payload.plan_evidence) { throw "$surface plan_evidence missing" }
  if ($null -eq $payload.result -or $null -eq $payload.result.planning) {
    throw "$surface result planning envelope missing"
  }
  $planning = $payload.result.planning
  if ($payload.plan_evidence.capability_discovery_available -ne $true) {
    throw "$surface capability discovery evidence missing"
  }
  if ($payload.plan_evidence.capability_catalog_available -ne $true) {
    throw "$surface capability catalog evidence missing"
  }
  if ([string]::IsNullOrWhiteSpace([string]$payload.plan_evidence.selected_capability_id)) {
    throw "$surface selected capability missing"
  }
  if (@($payload.plan_evidence.capability_candidate_ids).Count -lt 1) {
    throw "$surface capability candidates missing"
  }
  if (@($payload.plan_evidence.capability_catalog_ids).Count -lt 1) {
    throw "$surface capability catalog ids missing"
  }
  if ($planning.selected_capability_id -ne $payload.plan_evidence.selected_capability_id) {
    throw "$surface result planning selected capability mismatch"
  }
  if ($planning.capability_catalog_environment -ne $payload.plan_evidence.capability_catalog_environment) {
    throw "$surface capability catalog environment mismatch"
  }
  if ($planning.plan_identity.fingerprint -ne $payload.plan_evidence.plan_identity.fingerprint) {
    throw "$surface plan identity mismatch"
  }
  if ($null -eq $payload.plan_evidence.request_facts) {
    throw "$surface request facts evidence missing"
  }
  if ($payload.plan_evidence.request_facts.schema_version -ne "spatial-agent.request-facts.v1") {
    throw "$surface request facts schema mismatch"
  }
  if ($null -eq $payload.result.request_facts -or $payload.result.request_facts.schema_version -ne "spatial-agent.request-facts.v1") {
    throw "$surface result request facts mismatch"
  }
  if ($null -eq $payload.plan_evidence.execution_policy) {
    throw "$surface execution policy evidence missing"
  }
  if ($payload.plan_evidence.execution_policy.schema_version -ne "spatial-agent.execution-policy.v1") {
    throw "$surface execution policy schema mismatch"
  }
  if (@($payload.plan_evidence.execution_policy.tools).Count -lt 1) {
    throw "$surface execution policy tools missing"
  }
}

function Assert-DegradationEvidence($payload, [string]$surface) {
  if ($null -eq $payload.result -or $null -eq $payload.result.degradation) {
    throw "$surface result degradation envelope missing"
  }
  $degradation = $payload.result.degradation
  if ($degradation.schema_version -ne "spatial-agent.degradation.v1") {
    throw "$surface degradation schema mismatch: $($degradation.schema_version)"
  }
  if ($degradation.status -notin @("none", "warning", "degraded", "unavailable")) {
    throw "$surface degradation status invalid: $($degradation.status)"
  }
  $items = @($degradation.items)
  if ([int]$degradation.item_count -ne $items.Count) {
    throw "$surface degradation item_count mismatch"
  }
  if ($degradation.status -ne "none" -and $items.Count -lt 1) {
    throw "$surface degradation items missing"
  }
  foreach ($item in $items) {
    if ([string]::IsNullOrWhiteSpace([string]$item.code)) {
      throw "$surface degradation item code missing"
    }
    if ($item.severity -notin @("warning", "degraded", "unavailable")) {
      throw "$surface degradation item severity invalid: $($item.severity)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$item.message)) {
      throw "$surface degradation item message missing"
    }
    if ([string]::IsNullOrWhiteSpace([string]$item.source)) {
      throw "$surface degradation item source missing"
    }
  }
}

function Assert-WorkspaceEvidence($payload, [string]$surface) {
  if ($null -eq $payload.result -or $null -eq $payload.result.workspace) {
    throw "$surface result workspace envelope missing"
  }
  $workspace = $payload.result.workspace
  if ($workspace.schema_version -ne "spatial-agent.workspace.v1") {
    throw "$surface workspace schema mismatch: $($workspace.schema_version)"
  }
  if ([string]::IsNullOrWhiteSpace([string]$workspace.result_type)) {
    throw "$surface workspace result_type missing"
  }
  if ($null -eq $workspace.common_panels -or @($workspace.common_panels).Count -lt 1) {
    throw "$surface workspace common panels missing"
  }
  if ($null -eq $workspace.panels) {
    throw "$surface workspace panels missing"
  }
  if ($null -eq $workspace.map -or [string]::IsNullOrWhiteSpace([string]$workspace.map.mode)) {
    throw "$surface workspace map evidence missing"
  }
}

function Assert-ViewEvidence($payload, [string]$surface) {
  if ($null -eq $payload.result -or $null -eq $payload.result.views) {
    throw "$surface result views envelope missing"
  }
  $views = $payload.result.views
  if ($views.schema_version -ne "spatial-agent.views.v1") {
    throw "$surface views schema mismatch: $($views.schema_version)"
  }
  if ($null -eq $views.panels) {
    throw "$surface views panels missing"
  }
  $workspacePanels = @($payload.result.workspace.panels)
  $viewPanelNames = @($views.panels.PSObject.Properties.Name | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
  foreach ($panel in $viewPanelNames) {
    if ($panel -notin $workspacePanels) {
      throw "$surface view panel not declared by workspace: $panel"
    }
  }
}

function Assert-NestedViewTree($workspace, $views, [string]$surface, [bool]$RequireWorkspaceIdentity = $true) {
  if ($null -eq $workspace) { throw "$surface workspace envelope missing" }
  if ($workspace.schema_version -ne "spatial-agent.workspace.v1") {
    throw "$surface workspace schema mismatch: $($workspace.schema_version)"
  }
  if ($RequireWorkspaceIdentity) {
    if ([string]::IsNullOrWhiteSpace([string]$workspace.result_type)) {
      throw "$surface workspace result_type missing"
    }
    if ($null -eq $workspace.common_panels) {
      throw "$surface workspace common_panels missing"
    }
  }
  if ($null -eq $workspace.panels) { throw "$surface workspace panels missing" }
  if ($null -eq $workspace.view_specs) { throw "$surface workspace view_specs missing" }

  foreach ($view in @($workspace.view_specs)) {
    if ($null -eq $view) { throw "$surface view spec is null" }
    if ($view.schema_version -ne "spatial-agent.view.v1") {
      throw "$surface view schema mismatch: $($view.schema_version)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$view.id)) {
      throw "$surface view id missing"
    }
    if ([string]::IsNullOrWhiteSpace([string]$view.renderer)) {
      throw "$surface view renderer missing"
    }
  }

  if ($null -eq $views) { throw "$surface views envelope missing" }
  if ($views.schema_version -ne "spatial-agent.views.v1") {
    throw "$surface views schema mismatch: $($views.schema_version)"
  }
  if ($null -eq $views.panels) { throw "$surface views panels missing" }
  $workspacePanels = @($workspace.panels)
  $panelProperties = @($views.panels.PSObject.Properties | Where-Object {
    -not [string]::IsNullOrWhiteSpace([string]$_.Name)
  })
  foreach ($property in $panelProperties) {
    $panel = $property.Value
    if ($null -eq $panel -or $panel -is [string]) {
      throw "$surface panel payload invalid: $($property.Name)"
    }
    if ($property.Name -notin $workspacePanels) {
      throw "$surface view panel not declared by workspace: $($property.Name)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$panel.kind)) {
      throw "$surface panel kind missing: $($property.Name)"
    }
    # Panel models use the shared view schema version. If a producer supplies
    # one, it must be the supported version instead of being silently accepted.
    $panelVersionProperty = $panel.PSObject.Properties["schema_version"]
    if ($null -ne $panelVersionProperty -and $panelVersionProperty.Value -ne "spatial-agent.view.v1") {
      throw "$surface panel schema mismatch: $($panelVersionProperty.Value)"
    }
  }
}

function Assert-NestedSchemaContract($payload, [string]$surface) {
  if ($null -eq $payload) { throw "$surface payload is empty" }
  $result = $payload.result
  if ($null -eq $result) {
    throw "$surface result envelope missing"
  }
  if ($result.schema_version -ne "spatial-agent.result-envelope.v1") {
    throw "$surface result schema mismatch: $($result.schema_version)"
  }
  if ([string]::IsNullOrWhiteSpace([string]$result.type)) {
    throw "$surface result type missing"
  }
  Assert-NestedViewTree $result.workspace $result.views "$surface result" $true

  # Async polling intentionally exposes a smaller evidence projection. It
  # still has to use the same workspace/view versions and panel linkage.
  $evidence = $payload.result_evidence
  if ($null -ne $evidence) {
    if ($evidence.schema_version -ne "spatial-agent.async-result-evidence.v1") {
      throw "$surface async result evidence schema mismatch"
    }
    Assert-NestedViewTree $evidence.workspace $evidence.views "$surface async evidence" $false
    foreach ($property in @($evidence.views.panels.PSObject.Properties | Where-Object {
      -not [string]::IsNullOrWhiteSpace([string]$_.Name)
    })) {
      if ([string]::IsNullOrWhiteSpace([string]$property.Value.kind)) {
        throw "$surface async panel kind missing: $($property.Name)"
      }
    }
  }
}

function Assert-AsyncResultEvidence($payload, [string]$surface) {
  $evidence = $payload.result_evidence
  if ($null -eq $evidence) { throw "$surface async result evidence missing" }
  if ($evidence.schema_version -ne "spatial-agent.async-result-evidence.v1") {
    throw "$surface async result evidence schema mismatch"
  }
  if ($evidence.state -notin @("pending", "success", "degraded", "unavailable")) {
    throw "$surface async result evidence state invalid: $($evidence.state)"
  }
  if ($null -eq $evidence.workspace -or $null -eq $evidence.views) {
    throw "$surface async result evidence workspace/views missing"
  }
  if ($evidence.views.schema_version -ne "spatial-agent.views.v1") {
    throw "$surface async result evidence views schema mismatch"
  }
  if ($null -eq $evidence.artifact -or $null -eq $evidence.artifact.available) {
    throw "$surface async result evidence artifact state missing"
  }
  Assert-NestedViewTree $evidence.workspace $evidence.views "$surface async evidence" $false
  $serialized = $evidence | ConvertTo-Json -Depth 20 -Compress
  if ($serialized -match '(?i)(?:[A-Za-z]:\\|/app/|/data/)') {
    throw "$surface async result evidence contains a filesystem path"
  }
}

function Assert-DeploymentEvidence($payload, [string]$surface) {
  if ($null -eq $payload) { throw "$surface deployment payload is empty" }
  $deployment = $payload.deployment_evidence
  if ($null -eq $deployment -and $null -ne $payload.result) {
    $deployment = $payload.result.deployment_evidence
  }
  if ($null -eq $deployment) { throw "$surface deployment evidence missing" }
  if ($deployment.schema_version -ne "spatial-agent.deployment-evidence.v1") {
    throw "$surface deployment evidence schema mismatch"
  }
  if ($deployment.status -notin @("ready", "degraded", "unavailable", "context_only", "unknown")) {
    throw "$surface deployment evidence status invalid: $($deployment.status)"
  }
  if ([string]::IsNullOrWhiteSpace([string]$deployment.context_fingerprint)) {
    throw "$surface deployment context fingerprint missing"
  }
  if ($null -eq $deployment.data -or $null -eq $deployment.model -or $null -eq $deployment.degradation) {
    throw "$surface deployment evidence sections missing"
  }
  if ($deployment.model.execution_mode -notin @("rule", "offline_replay", "live_model", "unknown")) {
    throw "$surface deployment model execution mode invalid"
  }

  $context = $payload.runtime_context
  if ($null -eq $context -and $null -ne $payload.result) {
    $context = $payload.result.runtime_context
  }
  if ($null -ne $context -and -not [string]::IsNullOrWhiteSpace([string]$context.fingerprint)) {
    if ([string]$context.fingerprint -ne [string]$deployment.context_fingerprint) {
      throw "$surface deployment context fingerprint mismatch"
    }
  }

  $serialized = $payload | ConvertTo-Json -Depth 50 -Compress
  if ($serialized -match '(?i)"(?:api_key|authorization|password|secret|raw_response)"\s*:') {
    throw "$surface deployment payload contains a forbidden sensitive field"
  }
}

if (-not [string]::IsNullOrWhiteSpace($ContractPayloadPath)) {
  if (-not (Test-Path -LiteralPath $ContractPayloadPath -PathType Leaf)) {
    throw "contract payload not found: $ContractPayloadPath"
  }
  $contractPayload = Get-Content -LiteralPath $ContractPayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
  Assert-NestedSchemaContract $contractPayload "offline nested contract"
  [pscustomobject]@{
    status = "ok"
    surface = "nested-schema"
  } | ConvertTo-Json -Compress
  exit 0
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
Assert-DeploymentEvidence $runtimeCapabilities "runtime capabilities"
$releaseEvidence = Get-Json "$BaseUrl/release-evidence?max_files=1"
Assert-DeploymentEvidence $releaseEvidence "release evidence"
if ($releaseEvidence.deployment_evidence.context_fingerprint -ne $runtimeCapabilities.deployment_evidence.context_fingerprint) {
  throw "runtime and release deployment context fingerprints differ"
}

$sessionId = "production-acceptance-" + [guid]::NewGuid().ToString("N")
$adminRequest = ([char]0x67E5) + ([char]0x8BE2) + ([char]0x6D2A) + ([char]0x5C71) + ([char]0x533A) + ([char]0x884C) + ([char]0x653F) + ([char]0x533A) + ([char]0x8FB9) + ([char]0x754C)
$preview = Post-Json "$BaseUrl/runs/preview" @{
  request = $adminRequest
  session_id = $sessionId
  planner = "rule"
  backend = "memory"
}
if ($preview.status -ne "PLANNED") { throw "preview failed: $($preview.status)" }
if ($preview.execution.planned_only -ne $true -or $preview.execution.tool_execution -ne $false) {
  throw "preview execution flags invalid"
}
if ($preview.PSObject.Properties.Name -contains "run_id") { throw "preview must not allocate run_id" }
if ($null -eq $preview.plan_identity -or [string]::IsNullOrWhiteSpace([string]$preview.plan_identity.fingerprint)) {
  throw "preview plan identity missing"
}
if (-not ([string]$preview.plan_identity.fingerprint).StartsWith("sha256:")) {
  throw "preview fingerprint must be sha256"
}

$syncRun = Post-Json "$BaseUrl/runs" @{
  request = $adminRequest
  session_id = $sessionId
  planner = "rule"
  backend = "memory"
  preview_fingerprint = $preview.plan_identity.fingerprint
  export_artifact = $true
}
if ($syncRun.status -ne "COMPLETED") { throw "sync run failed: $($syncRun.error)" }
if ($syncRun.plan_evidence.plan_fingerprint_match -ne $true) {
  throw "sync run did not match preview fingerprint"
}
Assert-PlanningEvidence $syncRun "sync run"
Assert-DegradationEvidence $syncRun "sync run"
Assert-WorkspaceEvidence $syncRun "sync run"
Assert-ViewEvidence $syncRun "sync run"
Assert-NestedSchemaContract $syncRun "sync run"
Assert-ReplanningEvidence $syncRun "sync run"
Assert-DeploymentEvidence $syncRun "sync run"
if ([string]::IsNullOrWhiteSpace([string]$syncRun.artifact_ref)) {
  throw "sync run artifact_ref missing"
}
$artifactName = Split-Path -Leaf ([string]$syncRun.artifact_ref)
$artifact = Get-Json "$BaseUrl/artifacts/runs/$artifactName"
if ($artifact.plan_evidence.selected_capability_id -ne $syncRun.plan_evidence.selected_capability_id) {
  throw "artifact selected capability mismatch"
}
if ($artifact.plan_evidence.capability_catalog_available -ne $true) {
  throw "artifact capability catalog evidence missing"
}
if ($artifact.request_facts.schema_version -ne "spatial-agent.request-facts.v1") {
  throw "artifact request facts evidence missing"
}
if ($artifact.result.request_facts.schema_version -ne "spatial-agent.request-facts.v1") {
  throw "artifact result request facts evidence missing"
}
if ($artifact.plan_evidence.execution_policy.schema_version -ne "spatial-agent.execution-policy.v1") {
  throw "artifact execution policy evidence missing"
}
if ($null -eq $artifact.degradation -or $null -eq $artifact.result -or $null -eq $artifact.result.degradation) {
  throw "artifact degradation evidence missing"
}
if ($artifact.degradation.status -ne $syncRun.result.degradation.status) {
  throw "artifact degradation status mismatch"
}
if ($null -eq $artifact.result -or $null -eq $artifact.result.workspace) {
  throw "artifact workspace evidence missing"
}
if ($artifact.result.workspace.schema_version -ne $syncRun.result.workspace.schema_version) {
  throw "artifact workspace schema mismatch"
}
if ($null -eq $artifact.result.views) {
  throw "artifact views evidence missing"
}
if ($artifact.result.views.schema_version -ne $syncRun.result.views.schema_version) {
  throw "artifact views schema mismatch"
}
Assert-ReplanningEvidence $artifact "artifact"
Assert-DeploymentEvidence $artifact "artifact"
Assert-NestedSchemaContract $artifact "artifact"
$syncArtifactContract = Invoke-ContractHarness -payloads @($syncRun, $artifact) -surface "sync/artifact"

$failureRun = Post-Json "$BaseUrl/runs" @{
  request = $adminRequest
  session_id = "acceptance-failure-contract"
  planner = "rule"
  backend = "memory"
  preview_fingerprint = "sha256:acceptance-mismatch"
  export_artifact = $true
}
if ($failureRun.status -ne "FAILED") { throw "failure contract run unexpectedly succeeded" }
Assert-FailureEvidence $failureRun "sync failure run"
Assert-DeploymentEvidence $failureRun "sync failure run"
$failureArtifactName = Split-Path -Leaf ([string]$failureRun.artifact_ref)
$failureArtifact = Get-Json "$BaseUrl/artifacts/runs/$failureArtifactName"
Assert-FailureEvidence $failureArtifact "failure artifact"
Assert-DeploymentEvidence $failureArtifact "failure artifact"

$invalid = Post-JsonExpectError "$BaseUrl/runs" @{
  request = $adminRequest
  planner = "rule"
  backend = "invalid-backend"
}
if ($invalid.status_code -ne 400) { throw "invalid backend status mismatch: $($invalid.status_code)" }
if ($invalid.payload.error_code -ne "invalid_request" -or $invalid.payload.error_category -ne "tool") {
  throw "invalid backend error envelope mismatch"
}

$greeting = ([char]0x4F60) + ([char]0x597D)
$asyncPayload = @{ request = $greeting; session_id = $sessionId; planner = "rule"; backend = "memory" }
$queued = Post-Json "$BaseUrl/runs/async" $asyncPayload
if (-not $queued.run_id -or $queued.status -ne "QUEUED") { throw "async submission failed" }
$duplicate = Post-Json "$BaseUrl/runs/async" $asyncPayload
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
Assert-DeploymentEvidence $final "async run"
$asyncObservation = Get-Json "$BaseUrl/runs/$($queued.run_id)/async"
Assert-AsyncResultEvidence $asyncObservation "async polling"

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
  runtime_tool_provider = $runtimeCapabilities.tool_provider.id
  runtime_deployment_status = $runtimeCapabilities.deployment_evidence.status
  release_deployment_status = $releaseEvidence.deployment_evidence.status
  sync_deployment_status = $syncRun.result.deployment_evidence.status
  runtime_tool_provider_health = $runtimeCapabilities.tool_provider_health.status
  runtime_tool_count = $runtimeCapabilities.tool_provider.tool_count
  preview_status = $preview.status
  preview_fingerprint_version = $preview.plan_identity.version
  sync_status = $syncRun.status
  sync_preview_fingerprint_match = $syncRun.plan_evidence.plan_fingerprint_match
  sync_selected_capability = $syncRun.plan_evidence.selected_capability_id
  sync_capability_catalog_environment = $syncRun.plan_evidence.capability_catalog_environment
  sync_artifact_available = -not [string]::IsNullOrWhiteSpace([string]$syncRun.artifact_ref)
  sync_degradation_status = $syncRun.result.degradation.status
  sync_workspace_panels = @($syncRun.result.workspace.panels)
  sync_view_panels = @($syncRun.result.views.panels.PSObject.Properties.Name | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
  sync_artifact_contract = $syncArtifactContract.status
  failure_contract_status = $failureRun.failure.status
  failure_contract_phase = $failureRun.failure.phase
  invalid_request_status = $invalid.status_code
  invalid_request_error_code = $invalid.payload.error_code
  async_status = $final.status
  async_view_state = $asyncObservation.result_evidence.state
  async_duplicate_idempotent = $duplicate.idempotent
  run_id = $queued.run_id
} | ConvertTo-Json -Compress
