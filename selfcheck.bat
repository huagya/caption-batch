@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  caption-batch  selfcheck
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run install.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "%~dp0scripts\selfcheck.py"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [FAIL] Selfcheck failed with code %RC%
  pause
  exit /b %RC%
)

echo [OK] Selfcheck passed.
pause
exit /b 0
