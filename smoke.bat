@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  caption-batch  smoke (dry-run)
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run install.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m caption_batch.cli run --provider gemini --model dry --input-dir _smoke --dry-run --limit 3
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [ERROR] smoke failed with code %RC%
  pause
  exit /b %RC%
)

echo [OK] Smoke dry-run passed.
pause
exit /b 0
