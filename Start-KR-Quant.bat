@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research - Local Server
echo ===================================================
echo [KR Quant Research] 기존 서버를 정리하고 새로 시작합니다...
echo ===================================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart.ps1"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo.
    echo 서버 재시작 중 오류가 발생했습니다.
    echo 로그: %~dp0logs\web.stderr.log
    pause
)
if "%ERR%"=="0" (
    echo.
    echo 서버가 시작되었습니다. 브라우저에서 http://127.0.0.1:8790 을 확인하세요.
)
endlocal & exit /b %ERR%
