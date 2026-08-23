[CmdletBinding()]
param(
    [int]$MaxCurrentChars = 4500,
    [string]$Topic = '',
    [ValidateRange(1, 12)]
    [int]$MaxMatches = 4,
    [ValidateRange(0, 20)]
    [int]$ContextLines = 8
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$currentPath = Join-Path $repoRoot 'docs/agent-context-current.md'

if (-not (Test-Path -LiteralPath $currentPath -PathType Leaf)) {
    throw "Missing context snapshot: $currentPath"
}

$current = Get-Content -LiteralPath $currentPath -Raw
if ($current.Length -gt $MaxCurrentChars) {
    $current = $current.Substring(0, $MaxCurrentChars) + "`n[context snapshot truncated]"
}

Write-Output '=== Agent current context ==='
Write-Output $current
Write-Output '=== Git status ==='
git -C $repoRoot status --short --branch
Write-Output '=== Latest commit ==='
git -C $repoRoot log -1 --oneline --decorate
Write-Output '=== History policy ==='
Write-Output 'Historical files are not loaded by default. With -Topic, only bounded matches from the current issue index and archives are returned.'

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
