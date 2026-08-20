@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  Missing .venv
  echo  python -m venv .venv
  echo  .venv\Scripts\pip install -e ".[dev]"
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m kr_quant.web.app
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo Start failed.
  pause
  exit /b %ERR%
)
endlocal
