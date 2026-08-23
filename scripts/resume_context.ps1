[CmdletBinding()]
param(
    [ValidateRange(800, 4000)]
    [int]$MaxCurrentChars = 1800,
    [string]$Topic = '',
    [ValidateRange(1, 12)]
    [int]$MaxMatches = 4,
    [ValidateRange(0, 20)]
    [int]$ContextLines = 8,
    [switch]$Diagnostics
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$snapshotPath = Join-Path $repoRoot 'docs/agent-context-resume.md'

if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
    throw "Missing context snapshot: $snapshotPath"
}

$current = Get-Content -LiteralPath $snapshotPath -Raw
if ($current.Length -gt $MaxCurrentChars) {
    $current = $current.Substring(0, $MaxCurrentChars) + "`n[context snapshot truncated]"
}

Write-Output '=== Agent current context ==='
Write-Output $current

if ($Diagnostics) {
    Write-Output '=== Git status ==='
    git -C $repoRoot status --short --branch
    Write-Output '=== Latest commit ==='
    git -C $repoRoot log -1 --oneline --decorate
}

if ([string]::IsNullOrWhiteSpace($Topic)) {
    Write-Output '=== Read policy ==='
    Write-Output 'Only the current snapshot was loaded. Use -Diagnostics or -Topic explicitly for more context.'
}

if (-not [string]::IsNullOrWhiteSpace($Topic)) {
    $historyPaths = @(
        (Join-Path $repoRoot 'docs/agent-development-issues.md'),
        (Join-Path $repoRoot 'docs/archive/context-history/agent-context-resume-history.md'),
        (Join-Path $repoRoot 'docs/archive/context-history/task-resume-history.md'),
        (Join-Path $repoRoot 'docs/archive/context-history/agent-development-issues-history.md'),
        (Join-Path $repoRoot 'docs/milestones.md')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }

    Write-Output '=== Targeted history ==='
    Write-Output ("topic={0}; max_matches={1}; context_lines={2}" -f $Topic, $MaxMatches, $ContextLines)

    $rgArgs = @(
        '--no-heading',
        '--line-number',
        '--max-count', [string]$MaxMatches,
        '--context', [string]$ContextLines,
        '--', $Topic
    ) + $historyPaths

    $matches = & rg @rgArgs 2>$null
    if ($LASTEXITCODE -eq 0) {
        $maxOutputLines = $MaxMatches * (1 + (2 * $ContextLines) + 2)
        $matches | Select-Object -First $maxOutputLines
    }
    else {
        Write-Output '[no bounded history matches]'
    }
}
