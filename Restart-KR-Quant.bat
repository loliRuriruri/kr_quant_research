@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ===================================================
echo [KR Quant Research] 로컬 서버를 재시작합니다...
echo ===================================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart.ps1"
echo.
echo 서버 재시작이 완료되었습니다. 브라우저에서 Ctrl+F5를 눌러주세요.
pause
endlocal
