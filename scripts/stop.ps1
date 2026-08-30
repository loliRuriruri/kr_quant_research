[CmdletBinding()]
param(
    [int]$Port = 8790
)

$ErrorActionPreference = 'SilentlyContinue'
$connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
$stopped = 0
foreach ($processId in @($connections | Where-Object { $_.OwningProcess -gt 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique)) {
    if ($processId -gt 0) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
if ($stopped -gt 0) {
    Start-Sleep -Milliseconds 300
    $remaining = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 })
    if ($remaining.Count -gt 0) {
        Write-Error "포트 ${Port}의 서버가 아직 종료되지 않았습니다. 관리자 권한 또는 다른 프로세스의 점유 여부를 확인하세요."
        exit 1
    }
    Write-Host "포트 ${Port}의 서버 프로세스를 정상 종료했습니다." -ForegroundColor Green
} else {
    Write-Host "실행 중인 서버 프로세스가 없습니다." -ForegroundColor Yellow
}
exit 0
