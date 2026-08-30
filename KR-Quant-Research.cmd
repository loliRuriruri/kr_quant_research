@echo off
setlocal
powershell.exe -NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0scripts\restart.ps1" -NoBrowser
if errorlevel 1 pause
endlocal
