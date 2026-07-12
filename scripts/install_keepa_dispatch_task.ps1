[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$IntervalMinutes = 0,

    [int]$MinimumGapMinutes = 0,

    [string]$TaskName = "FBA Keepa Collector Dispatch",

    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$dispatcher = Join-Path $PSScriptRoot "dispatch_keepa_collect.ps1"
$repoRoot = Split-Path -Parent $PSScriptRoot
$brainPath = Join-Path $repoRoot "learning-hub\data\ai-brain.json"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        if ($PSCmdlet.ShouldProcess($TaskName, "Unregister scheduled task")) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Output "Removed scheduled task: $TaskName"
        }
    } else {
        Write-Output "Scheduled task does not exist: $TaskName"
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $dispatcher -PathType Leaf)) {
    throw "Dispatcher script is missing: $dispatcher"
}
if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh.exe) is required before installing the dispatcher task."
}

try {
    $brain = Get-Content -LiteralPath $brainPath -Raw | ConvertFrom-Json
    $acceleration = $brain.learning.sampling.corpusAcceleration
} catch {
    throw "Could not read dispatcher cadence from ai-brain.json: $($_.Exception.Message)"
}
if ($IntervalMinutes -eq 0) {
    $IntervalMinutes = [int]$acceleration.targetDispatchMinutes
}
if ($MinimumGapMinutes -eq 0) {
    $MinimumGapMinutes = [int]$acceleration.minimumDispatchGapMinutes
}
if ($IntervalMinutes -lt 15 -or $IntervalMinutes -gt 180) {
    throw "IntervalMinutes must resolve to 15-180; got $IntervalMinutes."
}
if ($MinimumGapMinutes -lt 5 -or $MinimumGapMinutes -gt 180) {
    throw "MinimumGapMinutes must resolve to 5-180; got $MinimumGapMinutes."
}

$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$dispatcher`" -MinimumGapMinutes $MinimumGapMinutes"
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Dispatches the Keepa collector only after a quiet gap; GitHub cron remains the fallback. No credentials are embedded."

if ($PSCmdlet.ShouldProcess($TaskName, "Register or replace scheduled task")) {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    $registered = Get-ScheduledTask -TaskName $TaskName
    Write-Output "Installed scheduled task: $TaskName"
    Write-Output "Interval: $IntervalMinutes minutes; dispatch gap: $MinimumGapMinutes minutes; starts: $($registered.Triggers[0].StartBoundary)"
}
