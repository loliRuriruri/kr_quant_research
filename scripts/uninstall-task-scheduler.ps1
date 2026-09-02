[CmdletBinding()]
param(
    [string]$TaskName = "KR-Quant-Research-Server"
)

$ErrorActionPreference = 'Stop'

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "[KR Quant Research] Windows ?? ???? ??" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

try {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "??? ??($TaskName)? ????." -ForegroundColor Yellow
        exit 0
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "?? ????($TaskName)? ????? ???????." -ForegroundColor Green
    exit 0
}
catch {
    Write-Error "?? ???? ?? ? ??? ??????: $($_.Exception.Message)"
    exit 1
}
