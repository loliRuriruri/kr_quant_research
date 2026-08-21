@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ==============================================================
    echo  [ERROR] Missing .venv virtual environment.
    echo  Please create virtualenv: python -m venv .venv
    echo  Install packages: .venv\Scripts\pip install -e .[dev]
    echo ==============================================================
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m kr_quant.web.app
if errorlevel 1 (
    echo.
    echo ==============================================================
    echo  [ERROR] Server stopped with error. (Code: %ERRORLEVEL%)
    echo ==============================================================
    echo.
    pause
    exit /b %ERRORLEVEL%
)
endlocal
