[CmdletBinding()]
param(
    [ValidateRange(800, 4000)]
    [int]$MaxCurrentChars = 3600,
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
$taskProgressPath = Join-Path $repoRoot 'tasks/task-progress.md'

if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
    throw "Missing work state snapshot: $snapshotPath"
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

function Get-TaskProgressExcerpt {
    param(
        [string]$Path,
        [int]$MaxChars
    )

    $lines = @(Get-Content -LiteralPath $Path)
    $currentIndex = [Array]::IndexOf($lines, '## 当前进行中')
    $recentIndex = [Array]::IndexOf($lines, '## 最近完成')
    function Find-NextTopLevelSection {
        param(
            [string[]]$SectionLines,
            [int]$Start
        )
        for ($i = $Start; $i -lt $SectionLines.Count; $i++) {
            if ([string]$SectionLines[$i] -match '^## [^#]') { return $i }
        }
        return $SectionLines.Count
    }
    $currentLines = @()
    if ($currentIndex -ge 0) {
        $currentEnd = Find-NextTopLevelSection -SectionLines $lines -Start ($currentIndex + 1)
        $currentLines = @($lines[$currentIndex..($currentEnd - 1)])
    }

    $currentText = ($currentLines -join "`n").Trim()
    $remaining = [Math]::Max(0, $MaxChars - $currentText.Length - 2)
    $selectedRecent = New-Object System.Collections.Generic.List[string]
    $used = 0
    if ($recentIndex -ge 0) {
        $recentEnd = Find-NextTopLevelSection -SectionLines $lines -Start ($recentIndex + 1)
        $headers = @(
            for ($i = $recentIndex + 1; $i -lt $recentEnd; $i++) {
                if ([string]$lines[$i] -like '### *') { $i }
            }
        )
        # The ledger keeps only the newest completed task blocks in this
        # bounded section; old entries are below the next top-level section.
        for ($headerOffset = 0; $headerOffset -lt $headers.Count; $headerOffset++) {
            $start = [int]$headers[$headerOffset]
            $end = if ($headerOffset -lt ($headers.Count - 1)) {
                [int]$headers[$headerOffset + 1]
            } else {
                $recentEnd
            }
            $block = (($lines[$start..($end - 1)]) -join "`n").Trim()
            $cost = $block.Length + 2
            if ($selectedRecent.Count -gt 0 -and ($used + $cost) -gt $remaining) {
                break
            }
            $selectedRecent.Add($block)
            $used += $cost
        }
    }

    $parts = @()
    if ($currentText) { $parts += $currentText }
    if ($selectedRecent.Count -gt 0) {
        $parts += ((@('## 最近完成') + @($selectedRecent)) -join "`n`n").Trim()
    }
    $result = ($parts -join "`n`n").Trim()
    if ($result.Length -gt $MaxChars) {
        $result = $result.Substring(0, $MaxChars) + "`n[task progress excerpt truncated at line boundary]"
    }
    return $result
}

$taskProgress = Get-TaskProgressExcerpt -Path $taskProgressPath -MaxChars $MaxTaskProgressChars
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
    Write-Output 'Only the current handoff snapshot and bounded current/recent task-progress sections were loaded. Use -Diagnostics or -Topic explicitly for more context.'
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
