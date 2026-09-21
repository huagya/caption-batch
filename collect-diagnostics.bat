@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  caption-batch  collect-diagnostics
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run install.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m caption_batch.diagnostics
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [FAIL] Diagnostics collect failed with code %RC%
  pause
  exit /b %RC%
)

echo [OK] Zip written under diagnostics\
echo Send that zip when asking for help.
pause
exit /b 0
