$ErrorActionPreference = 'SilentlyContinue'
$connections = Get-NetTCPConnection -LocalPort 8790 -ErrorAction SilentlyContinue
$stopped = 0
foreach ($conn in $connections) {
    if ($conn.OwningProcess -gt 0) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
if ($stopped -gt 0) {
    Write-Host "포트 8790의 서버 프로세스를 정상 종료했습니다." -ForegroundColor Green
} else {
    Write-Host "실행 중인 서버 프로세스가 없습니다." -ForegroundColor Yellow
}
