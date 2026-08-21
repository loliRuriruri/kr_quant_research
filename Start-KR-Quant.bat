@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title KR Quant Research - 퀀트 투자 분석 시스템

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
chcp 65001 >nul

cls
echo.
echo  ==============================================================
echo    🚀 KR Quant Research 통합 퀀트 투자 시스템을 시작합니다...
echo  ==============================================================
echo.
echo   [1/3] 파이썬 가상환경(.venv) 점검 중...

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  [오류] .venv 가상환경을 찾을 수 없습니다.
  echo  가상환경 생성: python -m venv .venv
  echo  패키지 설치: .venv\Scripts\pip install -e ".[dev]"
  echo.
  pause
  exit /b 1
)

echo   [2/3] 가상환경 확인 완료!
echo   [3/3] 퀀트 분석 엔진 및 로컬 웹 서버 구동 중... (잠시만 기다려주세요)
echo.

".venv\Scripts\python.exe" -m kr_quant.web.app
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo  [오류] 서버 실행 중 문제가 발생했습니다. (Error Code: %ERR%)
  echo.
  pause
  exit /b %ERR%
)
endlocal
