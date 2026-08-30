@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research - Stop Local Server
echo ===================================================
echo [KR Quant Research] 로컬 서버를 중단합니다...
echo ===================================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo.
    echo 서버 중단 중 오류가 발생했습니다.
    echo 포트 8790을 다른 프로그램이 사용 중인지 확인하세요.
)
echo.
if not "%ERR%"=="0" pause
endlocal & exit /b %ERR%
