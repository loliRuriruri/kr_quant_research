[CmdletBinding()]
param(
    [string]$TaskName = "KR-Quant-Research-Server",
    [int]$Port = 8790
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$LaunchScript = Join-Path $PSScriptRoot 'launch.ps1'

if (-not (Test-Path $LaunchScript)) {
    throw "?? ????? ????: $LaunchScript"
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "[KR Quant Research] Windows ?? ???? ??" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "?? ??: $TaskName"
Write-Host "?? ??: $ProjectRoot"
Write-Host "?? ??: $env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$LaunchScript`" -Port $Port -NoBrowser" `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

try {
    # ?? ?? ??? ??? ???? ??
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "??? ??? ??($TaskName)? ???????..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "KR Quant Research Local Server - PC ??? ? ?? ?? ? ? ?? ? ??? ??? ??" | Out-Null

    Write-Host ""
    Write-Host "?? ????? ????? ???????!" -ForegroundColor Green
    Write-Host "  - ???: Windows ???($env:USERNAME) ??? ?"
    Write-Host "  - ??: ????? ?? ?? ?? (???? ? ?? ??)"
    Write-Host "  - ??: ?? ?? ? ?? ??? ??? ?? ?? ??"
    Write-Host ""
    Write-Host "?? ??? ?? ???:"
    Write-Host "  Start-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Gray
    Write-Host "?? ???:"
    Write-Host "  .\scripts\uninstall-task-scheduler.ps1" -ForegroundColor Gray
}
catch {
    Write-Error "?? ???? ?? ? ??? ??????: $($_.Exception.Message)"
    exit 1
}
