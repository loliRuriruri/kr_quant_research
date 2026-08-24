@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set ERR=0

echo.
echo ==============================================================
echo  KR Quant Research local dashboard
echo  http://127.0.0.1:8790
echo ==============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto NO_VENV

".venv\Scripts\python.exe" -m kr_quant.web.app
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" goto FAIL
goto END

:NO_VENV
echo ERROR: missing .venv
set ERR=1
goto END

:FAIL
echo.
echo ERROR: server stopped. Code %ERR%
echo If port 8790 is busy, dashboard may already be running.
echo Open http://127.0.0.1:8790

:END
echo.
echo Press any key to close this window.
pause >nul
endlocal
exit /b %ERR%
