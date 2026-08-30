@echo off
chcp 65001 >nul
rem 호환용 별칭입니다. 일상 실행은 Start-KR-Quant.bat 하나만 사용하세요.
call "%~dp0Start-KR-Quant.bat"
exit /b %ERRORLEVEL%
