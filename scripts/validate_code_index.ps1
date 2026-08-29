[CmdletBinding()]
param(
    [string]$IndexPath = 'docs/code-index.json',
    [string]$OverridesPath = 'docs/code-index-overrides.json'
)

$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$errors = New-Object System.Collections.Generic.List[string]
$allowedLayers = @('unclassified', 'application', 'runtime', 'planner', 'tooling', 'integration', 'analysis', 'domain', 'frontend', 'acceptance', 'data', 'verification', 'persistence', 'evidence', 'result', 'adapter', 'observability')
$allowedSemanticSources = @('file-override', 'path-rule', 'default')
$allowedResponsibilitySources = @('module-doc', 'semantic-role')

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
        if ([string]::IsNullOrWhiteSpace([string]$entry.layer)) { Add-Error ("semantic layer is empty: {0}" -f $path) }
        elseif ($allowedLayers -notcontains [string]$entry.layer) { Add-Error ("unsupported semantic layer: {0}" -f $path) }
        if ([string]::IsNullOrWhiteSpace([string]$entry.role)) { Add-Error ("semantic role is empty: {0}" -f $path) }
        if ([string]$entry.semantic_source -notin $allowedSemanticSources) { Add-Error ("invalid semantic source: {0}" -f $path) }
        if ([string]$entry.semantic_source -eq 'default') { Add-Error ("file has no semantic classification rule: {0}" -f $path) }
        if ([string]::IsNullOrWhiteSpace([string]$entry.responsibility)) { Add-Error ("responsibility is empty: {0}" -f $path) }
        if ([string]$entry.responsibility_source -notin $allowedResponsibilitySources) { Add-Error ("invalid responsibility source: {0}" -f $path) }
        $lineCount = 0
        try { $lineCount = [int]$entry.line_count } catch { Add-Error ("invalid line_count: {0}" -f $path) }
        foreach ($symbol in @($entry.public_symbols)) {
            $line = 0
            try { $line = [int]$symbol.line } catch { Add-Error ("invalid symbol line: {0}" -f $path) }
            if ($line -lt 1 -or $line -gt [Math]::Max(1, $lineCount)) { Add-Error ("symbol line outside file: {0}" -f $path) }
        }
    }
    if ([int]$index.file_count -ne $entries.Count) { Add-Error 'file_count does not match files array' }
    if ($null -eq $index.semantic_index) { Add-Error 'semantic_index metrics are missing' }
    else {
        $classifiedCount = @($entries | Where-Object { [string]$_.semantic_source -ne 'default' }).Count
        if ([int]$index.semantic_index.classified_files -ne $classifiedCount) { Add-Error 'semantic classified_files does not match files' }
        $defaultCount = @($entries | Where-Object { [string]$_.semantic_source -eq 'default' }).Count
        if ([int]$index.semantic_index.default_files -ne $defaultCount) { Add-Error 'semantic default_files does not match files' }
        $expectedCoverage = if ($entries.Count -eq 0) { 100.0 } else { [Math]::Round(100.0 * $classifiedCount / $entries.Count, 2) }
        if ([double]$index.semantic_index.coverage_percent -ne $expectedCoverage) { Add-Error 'semantic coverage_percent does not match files' }
        $agentEntries = @($entries | Where-Object { [string]$_.path -like 'agent/*' })
        if ([int]$index.semantic_index.agent_files -ne $agentEntries.Count) { Add-Error 'semantic agent_files does not match files' }
        $agentResponsibilityCount = @($agentEntries | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.responsibility) }).Count
        if ([int]$index.semantic_index.agent_files_with_responsibility -ne $agentResponsibilityCount) { Add-Error 'semantic agent responsibility count does not match files' }
        $agentModuleDocCount = @($agentEntries | Where-Object { [string]$_.responsibility_source -eq 'module-doc' }).Count
        if ([int]$index.semantic_index.agent_files_with_module_doc -ne $agentModuleDocCount) { Add-Error 'semantic agent module doc count does not match files' }
    }
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
    metrics = [ordered]@{
        indexed_files = if ($null -ne $index) { @($index.files).Count } else { 0 }
        semantic_coverage_percent = if ($null -ne $index -and $null -ne $index.semantic_index) { [double]$index.semantic_index.coverage_percent } else { 0 }
    }
}
Write-Output ($result | ConvertTo-Json -Depth 8)
if ($errors.Count -gt 0) { exit 1 }
