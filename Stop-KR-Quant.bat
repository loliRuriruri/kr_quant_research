@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ===================================================
echo [KR Quant Research] 로컬 서버를 중단합니다...
echo ===================================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "
$procs = Get-Process python -ErrorAction SilentlyContinue | Where-Object { (Get-NetTCPConnection -OwningProcess $_.Id -LocalPort 8790 -ErrorAction SilentlyContinue) }
if ($procs) {
    $procs | Stop-Process -Force
    Write-Host '포트 8790의 Python 서버 프로세스를 정상 종료했습니다.' -ForegroundColor Green
} else {
    Write-Host '현재 실행 중인 8790 포트 서버 프로세스가 없습니다.' -ForegroundColor Yellow
}
"
echo.
pause
endlocal
