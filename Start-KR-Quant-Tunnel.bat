@echo off
chcp 65001 >nul
rem 보조 기능: 외부 임시 공개가 필요할 때만 사용하세요. 일상 로컬 실행과는 별개입니다.
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Temporary Tunnel
set ERR=1

echo.
echo ==============================================================
echo  Temporary tunnel. This PC must stay on.
echo  External visitors are forced into read-only mode.
echo  Fixed public site: Start-KR-Quant-Public.bat
echo ==============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto NO_VENV
if not exist tools mkdir tools
if not exist tools\cloudflared.exe goto NO_CF

echo Checking local server on port 8790...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8790/api/status | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 goto START_SERVER
goto TUNNEL

:START_SERVER
echo Server is off. Starting local dashboard...
start "KR Quant Server" cmd /k "cd /d %~dp0 & .venv\Scripts\python.exe -m kr_quant.web.app"
timeout /t 6 /nobreak >nul

:TUNNEL
echo Opening read-only tunnel. A trycloudflare.com URL will appear.
echo Closing this window disconnects the tunnel.
echo.
tools\cloudflared.exe tunnel --url http://127.0.0.1:8790
set ERR=%ERRORLEVEL%
echo Tunnel stopped.
goto END

:NO_VENV
echo ERROR: missing .venv
goto END

:NO_CF
echo ERROR: tools\cloudflared.exe is missing.
goto END

:END
echo.
echo Press any key to close this window.
pause >nul
endlocal
exit /b %ERR%
