@echo off
cd /d "%~dp0"
echo ========================================
echo  caption-batch UI
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
echo Starting UI. Leave this window open.
echo Stop: Ctrl+C or close this window.
echo Browser should open automatically.
echo.
python app.py
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo [ERROR] Failed to start. Try setup.bat again,
  echo or close other caption-batch / Gradio windows.
  pause
  exit /b %ERR%
)
pause
