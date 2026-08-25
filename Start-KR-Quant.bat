@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1"
if errorlevel 1 (
    echo.
    echo 서버 실행 중 오류가 발생했습니다. 로그(logs/web.stderr.log)를 확인하세요.
    pause
)
endlocal
