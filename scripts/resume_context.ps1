[CmdletBinding()]
param(
    [int]$MaxCurrentChars = 6000
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
Write-Output 'Historical resume/task/issues files are not loaded. Use rg to locate a specific stage or keyword first.'
