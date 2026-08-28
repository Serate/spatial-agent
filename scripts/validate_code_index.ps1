[CmdletBinding()]
param(
    [string]$IndexPath = 'docs/code-index.json',
    [string]$OverridesPath = 'docs/code-index-overrides.json'
)

$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$errors = New-Object System.Collections.Generic.List[string]

function Resolve-RepoPath {
    param([string]$RelativePath)
    return Join-Path $repoRoot $RelativePath
}

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
}

$indexFile = Resolve-RepoPath $IndexPath
$overridesFile = Resolve-RepoPath $OverridesPath
$index = $null
$overrides = $null
try { $index = Get-Content -LiteralPath $indexFile -Raw | ConvertFrom-Json } catch { Add-Error 'code index is not valid JSON' }
try { $overrides = Get-Content -LiteralPath $overridesFile -Raw | ConvertFrom-Json } catch { Add-Error 'code index overrides are not valid JSON' }

if ($null -ne $index) {
    if ([string]$index.schema_version -ne 'spatial-agent.code-index.v1') { Add-Error 'unsupported code index schema' }
    $entries = @($index.files)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($entry in $entries) {
        $path = [string]$entry.path
        if (-not $seen.Add($path)) { Add-Error ("duplicate code index path: {0}" -f $path) }
        if (-not (Test-Path -LiteralPath (Resolve-RepoPath $path) -PathType Leaf)) { Add-Error ("indexed source is missing: {0}" -f $path) }
        $lineCount = 0
        try { $lineCount = [int]$entry.line_count } catch { Add-Error ("invalid line_count: {0}" -f $path) }
        foreach ($symbol in @($entry.public_symbols)) {
            $line = 0
            try { $line = [int]$symbol.line } catch { Add-Error ("invalid symbol line: {0}" -f $path) }
            if ($line -lt 1 -or $line -gt [Math]::Max(1, $lineCount)) { Add-Error ("symbol line outside file: {0}" -f $path) }
        }
    }
    if ([int]$index.file_count -ne $entries.Count) { Add-Error 'file_count does not match files array' }
}

if ($null -ne $overrides) {
    if ([string]$overrides.schema_version -ne 'spatial-agent.code-index-overrides.v1') { Add-Error 'unsupported overrides schema' }
    foreach ($property in $overrides.files.psobject.Properties) {
        $path = [string]$property.Name
        if ($null -ne $index -and -not (@($index.files | Where-Object { [string]$_.path -eq $path }).Count -eq 1)) {
            Add-Error ("override is not generated: {0}" -f $path)
        }
        if ($null -ne $property.Value.tests) {
            foreach ($testPath in @($property.Value.tests)) {
                $testPathText = [string]$testPath
                if ([string]::IsNullOrWhiteSpace($testPathText)) { Add-Error ("override test is empty: {0}" -f $path); continue }
                if (-not (Test-Path -LiteralPath (Resolve-RepoPath $testPathText) -PathType Leaf)) { Add-Error ("override test is missing: {0}" -f $testPathText) }
            }
        }
    }
}

$result = [ordered]@{
    schema_version = 'spatial-agent.code-index-check.v1'
    status = if ($errors.Count -eq 0) { 'ok' } else { 'failed' }
    errors = @($errors)
    metrics = [ordered]@{ indexed_files = if ($null -ne $index) { @($index.files).Count } else { 0 } }
}
Write-Output ($result | ConvertTo-Json -Depth 8)
if ($errors.Count -gt 0) { exit 1 }
