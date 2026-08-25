[CmdletBinding()]
param(
    [ValidateRange(800, 4000)]
    [int]$MaxCurrentChars = 3600,
    [ValidateRange(600, 3000)]
[int]$MaxTaskStateChars = 2200,
    [ValidateRange(600, 2600)]
    [int]$MaxTaskProgressChars = 1800,
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
$taskStatePath = Join-Path $repoRoot 'tasks/task-state.md'
$taskProgressPath = Join-Path $repoRoot 'tasks/task-progress.md'

if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
    throw "Missing work state snapshot: $snapshotPath"
}
if (-not (Test-Path -LiteralPath $taskStatePath -PathType Leaf)) {
    throw "Missing task state ledger: $taskStatePath"
}
if (-not (Test-Path -LiteralPath $taskProgressPath -PathType Leaf)) {
    throw "Missing task progress ledger: $taskProgressPath"
}

$current = Get-Content -LiteralPath $snapshotPath -Raw
if ($current.Length -gt $MaxCurrentChars) {
    $current = $current.Substring(0, $MaxCurrentChars) + "`n[context snapshot truncated]"
}

Write-Output '=== Agent current context ==='
Write-Output $current

$taskProgress = Get-Content -LiteralPath $taskProgressPath -Raw
if ($taskProgress.Length -gt $MaxTaskProgressChars) {
    $taskProgress = (Get-Content -LiteralPath $taskProgressPath | Select-Object -Last 40) -join "`n"
    if ($taskProgress.Length -gt $MaxTaskProgressChars) {
        $taskProgress = $taskProgress.Substring([Math]::Max(0, $taskProgress.Length - $MaxTaskProgressChars))
    }
}
Write-Output '=== Current task state ==='
Write-Output $taskProgress

if ($Diagnostics) {
    Write-Output '=== Git status ==='
    git -C $repoRoot status --short --branch
    Write-Output '=== Latest commit ==='
    git -C $repoRoot log -1 --oneline --decorate
}

if ([string]::IsNullOrWhiteSpace($Topic)) {
    Write-Output '=== Read policy ==='
    Write-Output 'Only the current snapshot and recent task-progress tail were loaded. Use -Diagnostics or -Topic explicitly for more context.'
}

if (-not [string]::IsNullOrWhiteSpace($Topic)) {
    $targetPaths = @(
        $snapshotPath,
        $taskProgressPath,
        (Join-Path $repoRoot 'tasks/plan.md'),
        (Join-Path $repoRoot 'tasks/todo.md')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }

    if ($IncludeHistory) {
        $targetPaths += @(
            (Join-Path $repoRoot 'docs/agent-development-issues.md'),
            (Join-Path $repoRoot 'docs/archive/context-history/agent-context-resume-history.md'),
            (Join-Path $repoRoot 'docs/archive/context-history/task-resume-history.md'),
            (Join-Path $repoRoot 'docs/archive/context-history/agent-development-issues-history.md'),
            (Join-Path $repoRoot 'docs/milestones.md')
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    }

    Write-Output '=== Targeted history ==='
    Write-Output ("topic={0}; max_matches={1}; context_lines={2}" -f $Topic, $MaxMatches, $ContextLines)

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
    }
    else {
        Write-Output '[no bounded history matches]'
    }
}
