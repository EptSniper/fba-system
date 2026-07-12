[CmdletBinding()]
param(
    [ValidateRange(5, 180)]
    [int]$MinimumGapMinutes = 40,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Repository = "EptSniper/fba-system"
$Workflow = "keepa-collect.yml"

function Write-DispatchStatus {
    param([string]$Message)
    Write-Output "[$([DateTimeOffset]::UtcNow.ToString('u'))] $Message"
}

$gh = Get-Command gh.exe -ErrorAction SilentlyContinue
if (-not $gh) {
    throw "GitHub CLI (gh.exe) is not available on PATH. The dispatcher cannot authenticate or start the workflow."
}

$raw = & $gh.Source run list `
    --repo $Repository `
    --workflow $Workflow `
    --limit 10 `
    --json createdAt,status,conclusion,databaseId 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not read recent $Workflow runs. gh exited $LASTEXITCODE. $($raw -join ' ')"
}

$parsedRuns = ConvertFrom-Json -InputObject ($raw -join [Environment]::NewLine)
$runs = @()
foreach ($run in $parsedRuns) {
    $runs += $run
}
$active = $runs | Where-Object { $_.status -in @("queued", "in_progress", "waiting", "pending") } | Select-Object -First 1
if ($active) {
    Write-DispatchStatus "Skip: workflow run $($active.databaseId) is already $($active.status)."
    exit 0
}

$latest = $runs | Sort-Object { [DateTimeOffset]::Parse($_.createdAt) } -Descending | Select-Object -First 1
if ($latest) {
    $age = [DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($latest.createdAt)
    if ($age.TotalMinutes -lt $MinimumGapMinutes) {
        Write-DispatchStatus ("Skip: latest run {0} started {1:N1} minutes ago; minimum gap is {2} minutes." -f `
            $latest.databaseId, $age.TotalMinutes, $MinimumGapMinutes)
        exit 0
    }
}

if ($DryRun) {
    Write-DispatchStatus "Dry run: would dispatch $Workflow for $Repository."
    exit 0
}

$dispatchOutput = & $gh.Source workflow run $Workflow --repo $Repository --ref master 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Workflow dispatch failed. gh exited $LASTEXITCODE. $($dispatchOutput -join ' ')"
}

Write-DispatchStatus "Dispatched $Workflow on master. GitHub concurrency will serialize it with any cron run."
