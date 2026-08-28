[CmdletBinding()]
param(
    [string[]]$Path = @('tasks/task-progress.md'),
    [string]$ArchiveId = '',
    [switch]$DryRun
)

$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')

function Resolve-SafePath {
    param([string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { throw 'path must not be empty' }
    $fullPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $RelativePath))
    $rootPrefix = $repoRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ("path escapes repository root: {0}" -f $RelativePath)
    }
    return $fullPath
}

function Read-Control {
    param([string]$Text, [string]$Source)
    $match = [regex]::Match($Text, '<!--\s*document-control:\s*(\{.*?\})\s*-->')
    if (-not $match.Success) { throw ("missing document-control in {0}" -f $Source) }
    try {
        return $match.Groups[1].Value | ConvertFrom-Json
    } catch {
        throw ("invalid document-control in {0}" -f $Source)
    }
}

$results = New-Object System.Collections.Generic.List[object]
foreach ($relativePath in $Path) {
    $sourcePath = Resolve-SafePath $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw ("source document not found: {0}" -f $relativePath)
    }
    $sourceText = Get-Content -LiteralPath $sourcePath -Raw
    $control = Read-Control -Text $sourceText -Source $relativePath
    if ([string]$control.schema_version -ne 'spatial-agent.document-control.v1') {
        throw ("unsupported document-control schema in {0}" -f $relativePath)
    }
    $archiveRelativePath = [string]$control.archive_target
    $archivePath = Resolve-SafePath $archiveRelativePath
    $prefix = [string]$control.archive_block_prefix
    if ([string]::IsNullOrWhiteSpace($prefix)) { throw ("archive_block_prefix is missing in {0}" -f $relativePath) }

    $escapedPrefix = [regex]::Escape($prefix)
    $pattern = '(?ms)<!--\s*' + $escapedPrefix + ':([A-Za-z0-9._-]+):start\s*-->\s*(.*?)\s*<!--\s*' + $escapedPrefix + ':\1:end\s*-->'
    $blocks = @([regex]::Matches($sourceText, $pattern))
    $selected = @($blocks | Where-Object {
        [string]::IsNullOrWhiteSpace($ArchiveId) -or $_.Groups[1].Value -eq $ArchiveId
    })
    $archiveText = if (Test-Path -LiteralPath $archivePath -PathType Leaf) { Get-Content -LiteralPath $archivePath -Raw } else { '' }
    $archiveEntries = New-Object System.Collections.Generic.List[object]
    $replacements = New-Object System.Collections.Generic.List[object]
    $seenIds = New-Object 'System.Collections.Generic.HashSet[string]'

    foreach ($block in $selected) {
        $id = $block.Groups[1].Value
        if (-not $seenIds.Add($id)) {
            throw ("duplicate archive block id in {0}: {1}" -f $relativePath, $id)
        }
        $marker = '<!-- archived-block:' + $id + ' -->'
        if ($archiveText.Contains($marker)) {
            $results.Add([ordered]@{ source = $relativePath; id = $id; status = 'already_archived' })
            continue
        }
        $entry = @(
            ''
            $marker
            ("来源：{0}" -f $relativePath)
            ("归档时间（UTC）：{0}" -f [DateTime]::UtcNow.ToString('o'))
            ''
            $block.Groups[2].Value.Trim()
            '<!-- archived-block-end:' + $id + ' -->'
            ''
        ) -join "`n"
        $archiveEntries.Add($entry)
        $archiveText += "`n" + $marker
        $replacements.Add([ordered]@{
            index = $block.Index
            length = $block.Length
            text = '<!-- archived-block-ref:' + $id + ' -->' + "`n" + '### ' + $id + ' — 已归档' + "`n" + ("- 详情：`{0}`（归档块 `{1}`）" -f $archiveRelativePath, $id)
        })
        $results.Add([ordered]@{ source = $relativePath; id = $id; status = if ($DryRun) { 'would_archive' } else { 'archived' } })
    }

    if (-not $DryRun -and $archiveEntries.Count -gt 0) {
        $archiveDirectory = Split-Path -Parent $archivePath
        if (-not (Test-Path -LiteralPath $archiveDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $archiveDirectory -Force | Out-Null
        }
        Add-Content -LiteralPath $archivePath -Value (($archiveEntries -join "`n") + "`n") -Encoding utf8
        foreach ($replacement in @($replacements | Sort-Object -Property index -Descending)) {
            $sourceText = $sourceText.Remove([int]$replacement.index, [int]$replacement.length)
            $sourceText = $sourceText.Insert([int]$replacement.index, [string]$replacement.text)
        }
        Set-Content -LiteralPath $sourcePath -Value $sourceText -Encoding utf8 -NoNewline
    }
}

$output = [ordered]@{
    schema_version = 'spatial-agent.document-archive.v1'
    status = 'ok'
    dry_run = [bool]$DryRun
    results = $results.ToArray()
}
Write-Output ($output | ConvertTo-Json -Depth 8)
