@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ===================================================
echo [KR Quant Research] 로컬 서버를 중단합니다...
echo ===================================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
echo.
pause
endlocal
