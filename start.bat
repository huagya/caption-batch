@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV=.venv"

echo ========================================
echo  caption-batch  start
echo ========================================
echo.

if not exist "%VENV%\Scripts\python.exe" (
  echo [.venv] Missing. Running install.bat nopause ...
  echo.
  call "%~dp0install.bat" nopause
  if errorlevel 1 (
    echo [ERROR] Install failed. Cannot start.
    pause
    exit /b 1
  )
)

echo Starting server via port.json (default 8771). Auto free-port if needed.
echo Keep this window open. Look for URL: and PORT= lines below.
echo Stop with Ctrl+C.
echo.

"%VENV%\Scripts\python.exe" -m caption_batch.run_server
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [ERROR] Server exited with code %RC%
  echo Try install.bat or update.bat, or check the log above.
  pause
  exit /b %RC%
)

echo Server stopped.
pause
exit /b 0
