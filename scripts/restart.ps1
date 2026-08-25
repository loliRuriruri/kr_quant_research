$ErrorActionPreference = 'SilentlyContinue'
$connections = Get-NetTCPConnection -LocalPort 8790 -ErrorAction SilentlyContinue
foreach ($conn in $connections) {
    if ($conn.OwningProcess -gt 0) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500
$launchScript = Join-Path $PSScriptRoot 'launch.ps1'
& $launchScript -NoBrowser
Write-Host "서버가 성공적으로 재시작되었습니다." -ForegroundColor Green
