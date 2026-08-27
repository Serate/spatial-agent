[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('coordinator', 'backend', 'frontend')]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [string]$TaskFile,

    [ValidateRange(2000, 24000)]
    [int]$MaxChars = 14000
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$rolePath = Join-Path $repoRoot ("docs/agents/roles/{0}.md" -f $Role)
$taskPath = Join-Path $repoRoot $TaskFile
$snapshotPath = Join-Path $repoRoot 'docs/agent-work-state.md'
$protocolPath = Join-Path $repoRoot 'docs/agents/protocol.md'
$resumeScript = Join-Path $PSScriptRoot 'resume_context.ps1'

function Resolve-RepoFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required context file: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $root = (Resolve-Path -LiteralPath $repoRoot).Path
    if (-not $resolved.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Context file is outside repository: $Path"
    }
    return $resolved
}

function Read-Bounded {
    param([string]$Path, [int]$Limit)
    $resolved = Resolve-RepoFile -Path $Path
    $text = Get-Content -LiteralPath $resolved -Raw
    if ($text.Length -gt $Limit) {
        return $text.Substring(0, $Limit) + "`n[section truncated]"
    }
    return $text
}

$rolePath = Resolve-RepoFile -Path $rolePath
$taskPath = Resolve-RepoFile -Path $taskPath
$snapshotPath = Resolve-RepoFile -Path $snapshotPath
$protocolPath = Resolve-RepoFile -Path $protocolPath

$resumeOutput = (& $resumeScript -MaxCurrentChars 3000 -MaxTaskProgressChars 1800) -join "`n"
$sections = @(
    "# Agent 上下文包`n`n角色：$Role`n任务文件：$TaskFile`n`n"
    "## 角色规约`n`n$(Read-Bounded -Path $rolePath -Limit 3000)"
    "## 当前任务卡`n`n$(Read-Bounded -Path $taskPath -Limit 3400)"
    "## 协作协议`n`n$(Read-Bounded -Path $protocolPath -Limit 3400)"
    "## 当前快照`n`n$(Read-Bounded -Path $snapshotPath -Limit 2600)"
    "## 恢复入口摘要`n`n$resumeOutput"
)

$packet = ($sections -join "`n`n").Trim()
if ($packet.Length -gt $MaxChars) {
    $marker = "`n[agent context packet truncated]"
    $keep = [Math]::Max(0, $MaxChars - $marker.Length)
    $packet = $packet.Substring(0, $keep) + $marker
}
Write-Output $packet
