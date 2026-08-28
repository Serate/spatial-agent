[CmdletBinding()]
param(
    [ValidateRange(800, 4000)]
    [int]$MaxSnapshotChars = 2800,
    [ValidateRange(600, 3200)]
    [int]$MaxStateChars = 2200,
    [ValidateRange(600, 3200)]
    [int]$MaxHandoffChars = 2400,
    [string]$Stage = '',
    [string]$Topic = '',
    [ValidateRange(1, 12)]
    [int]$MaxMatches = 4,
    [ValidateRange(0, 20)]
    [int]$ContextLines = 8,
    [switch]$IncludeHistory,
    [switch]$Diagnostics
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$snapshotPath = Join-Path $repoRoot 'docs/agent-work-state.md'
$indexPath = Join-Path $repoRoot 'docs/document-index.json'
$statePath = Join-Path $repoRoot 'tasks/current-state.md'
$taskProgressPath = Join-Path $repoRoot 'tasks/task-progress.md'

function Require-File {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Label`: $Path"
    }
}

function Read-Bounded {
    param([string]$Path, [int]$MaxChars)
    $value = Get-Content -LiteralPath $Path -Raw
    if ($value.Length -gt $MaxChars) {
        return $value.Substring(0, $MaxChars) + "`n[bounded output truncated]"
    }
    return $value
}

Require-File -Path $snapshotPath -Label 'work state snapshot'
Require-File -Path $indexPath -Label 'document index'
Require-File -Path $statePath -Label 'current task state'

try {
    $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
} catch {
    throw "Invalid document index: $indexPath"
}

$activeStage = if ([string]::IsNullOrWhiteSpace($Stage)) {
    [string]$index.active_stage
} else {
    $Stage.Trim()
}
$stageRecord = @($index.stage_packages | Where-Object { [string]$_.id -eq $activeStage }) | Select-Object -First 1
if ($null -eq $stageRecord) {
    throw "Unknown stage in document index: $activeStage"
}

Write-Output '=== Agent current context ==='
Write-Output (Read-Bounded -Path $snapshotPath -MaxChars $MaxSnapshotChars)

Write-Output '=== Current task state ==='
Write-Output (Read-Bounded -Path $statePath -MaxChars $MaxStateChars)

Write-Output '=== Current stage ==='
Write-Output (ConvertTo-Json $stageRecord -Depth 8)

$handoffPath = Join-Path $repoRoot ([string]$stageRecord.handoff)
if (Test-Path -LiteralPath $handoffPath -PathType Leaf) {
    Write-Output '=== Current stage handoff ==='
    Write-Output (Read-Bounded -Path $handoffPath -MaxChars $MaxHandoffChars)
}

Write-Output '=== Read policy ==='
Write-Output 'Default context loaded: hot snapshot, document index, current task state, and current-stage handoff only.'
Write-Output 'Stage Spec/Plan and source files are listed above but must be read explicitly when implementation needs them.'
Write-Output 'Use -Topic for bounded lookup; use -IncludeHistory only when historical context is required.'

if ($Diagnostics) {
    Write-Output '=== Git status ==='
    git -C $repoRoot status --short --branch
    Write-Output '=== Latest commit ==='
    git -C $repoRoot log -1 --oneline --decorate
}

if (-not [string]::IsNullOrWhiteSpace($Topic)) {
    $targetPaths = @(
        $snapshotPath,
        $indexPath,
        $statePath,
        $taskProgressPath,
        (Join-Path $repoRoot 'tasks/plan.md'),
        (Join-Path $repoRoot 'tasks/todo.md'),
        $handoffPath,
        (Join-Path $repoRoot ([string]$stageRecord.spec)),
        (Join-Path $repoRoot ([string]$stageRecord.plan)),
        (Join-Path $repoRoot ([string]$stageRecord.capability_map))
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }

    if ($IncludeHistory) {
        $targetPaths += @(
            (Join-Path $repoRoot 'docs/agent-development-issues.md'),
            (Join-Path $repoRoot 'docs/agent-context-resume.md'),
            (Join-Path $repoRoot 'docs/archive/'),
            (Join-Path $repoRoot 'docs/milestones.md')
        ) | Where-Object { Test-Path -LiteralPath $_ }
    }

    Write-Output '=== Bounded topic lookup ==='
    Write-Output ("topic={0}; stage={1}; max_matches={2}; context_lines={3}" -f $Topic, $activeStage, $MaxMatches, $ContextLines)

    $rgArgs = @(
        '--no-heading',
        '--line-number',
        '--max-count', [string]$MaxMatches,
        '--context', [string]$ContextLines,
        '--', $Topic
    ) + $targetPaths

    $matches = & rg @rgArgs 2>$null
    if ($LASTEXITCODE -eq 0) {
        $maxOutputLines = $MaxMatches * (1 + (2 * $ContextLines) + 2)
        $matches | Select-Object -First $maxOutputLines
    } else {
        Write-Output '[no bounded topic matches]'
    }
}
