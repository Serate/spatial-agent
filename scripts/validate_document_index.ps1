[CmdletBinding()]
param(
    [string]$Stage = ''
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$indexPath = Join-Path $repoRoot 'docs/document-index.json'
$snapshotPath = Join-Path $repoRoot 'docs/agent-work-state.md'
$statePath = Join-Path $repoRoot 'tasks/current-state.md'

$errors = New-Object System.Collections.Generic.List[string]

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
}

function Resolve-RepoPath {
    param([string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { return $null }
    return Join-Path $repoRoot $RelativePath
}

if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { Add-Error 'document index is missing' }
if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) { Add-Error 'work state snapshot is missing' }
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { Add-Error 'current task state is missing' }

$index = $null
if ($errors.Count -eq 0) {
    try {
        $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
    } catch {
        Add-Error 'document index is not valid JSON'
    }
}

if ($null -ne $index) {
    if ([string]$index.schema_version -ne 'spatial-agent.document-index.v1') {
        Add-Error 'unsupported document index schema'
    }
    $activeStage = if ([string]::IsNullOrWhiteSpace($Stage)) { [string]$index.active_stage } else { $Stage.Trim() }
    $stageEntry = @($index.stage_packages | Where-Object { [string]$_.id -eq $activeStage }) | Select-Object -First 1
    if ($null -eq $stageEntry) {
        Add-Error ("active stage is not indexed: {0}" -f $activeStage)
    } else {
        foreach ($field in @('capability_map', 'spec', 'plan', 'handoff')) {
            $value = [string]$stageEntry.$field
            if ([string]::IsNullOrWhiteSpace($value) -or -not (Test-Path -LiteralPath (Resolve-RepoPath $value) -PathType Leaf)) {
                Add-Error ("stage {0} has missing {1}" -f $activeStage, $field)
            }
        }
        foreach ($path in @($stageEntry.read_on_resume)) {
            if ([string]$path -ne [string]$stageEntry.handoff) {
                Add-Error ("stage {0} read_on_resume contains a non-handoff file" -f $activeStage)
            }
        }
    }
    foreach ($path in @($index.resume.default_files)) {
        if ([string]$path -match '(^|/|\\)archive($|/|\\)' -or [string]$path -match 'task-progress\.md$') {
            Add-Error ("default resume path is historical: {0}" -f $path)
        }
        if (-not (Test-Path -LiteralPath (Resolve-RepoPath ([string]$path)) -PathType Leaf)) {
            Add-Error ("default resume path is missing: {0}" -f $path)
        }
    }
}

foreach ($entry in @(
    @{ name = 'agent-work-state.md'; path = $snapshotPath; max = 6000 },
    @{ name = 'current-state.md'; path = $statePath; max = 6000 }
)) {
    if (Test-Path -LiteralPath $entry.path -PathType Leaf) {
        $length = (Get-Content -LiteralPath $entry.path -Raw).Length
        if ($length -gt $entry.max) { Add-Error ("{0} exceeds hot-state limit: {1}" -f $entry.name, $length) }
    }
}

$result = [ordered]@{
    schema_version = 'spatial-agent.document-index-check.v1'
    status = if ($errors.Count -eq 0) { 'ok' } else { 'failed' }
    stage = if ($null -ne $index) { if ([string]::IsNullOrWhiteSpace($Stage)) { [string]$index.active_stage } else { $Stage.Trim() } } else { $null }
    errors = @($errors)
    metrics = [ordered]@{
        default_file_count = if ($null -ne $index) { @($index.resume.default_files).Count } else { 0 }
        hot_state_limits = @{ snapshot_chars = 6000; current_state_chars = 6000 }
    }
}
Write-Output ($result | ConvertTo-Json -Depth 8)
if ($errors.Count -gt 0) { exit 1 }
