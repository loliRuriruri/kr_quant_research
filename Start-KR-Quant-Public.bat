@echo off
chcp 65001 >nul
rem 보조 기능: 일상 로컬 실행은 Start-KR-Quant.bat / Stop-KR-Quant.bat만 사용하세요.
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Public Web Update
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PATH=%ProgramFiles%\nodejs;%PATH%
set ERR=1

echo.
echo ==============================================================
echo  KR Quant public web snapshot upload
echo  URL: https://korea-quant-research.pages.dev/
echo  Progress prints here. Takes 1-2 minutes.
echo  Do not close until DONE or FAIL.
echo ==============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto NO_VENV
where node >nul 2>&1
if errorlevel 1 goto NO_NODE

echo START: build snapshot and upload to Cloudflare Pages
echo        API keys stay on this PC. Public site is read-only.
echo.
".venv\Scripts\python.exe" scripts\publish_public.py
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" goto FAIL
echo ==============================================================
echo  DONE: public site updated
echo  https://korea-quant-research.pages.dev/
echo  Refresh browser with Ctrl+F5
echo ==============================================================
goto END

:NO_VENV
echo ERROR: missing .venv
goto END

:NO_NODE
echo ERROR: Node.js not found. Install Node.js first.
goto END

:FAIL
echo ==============================================================
echo  FAIL: public site was NOT updated. Read the log above.
echo ==============================================================

:END
echo.
echo Press any key to close this window.
pause >nul
endlocal
exit /b %ERR%
