@echo off
cd /d "%~dp0"
echo ========================================
echo  caption-batch setup
echo ========================================
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1
  if %ERRORLEVEL%==0 (
    set "PY=python"
  ) else (
    echo [ERROR] Python not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo and check "Add python.exe to PATH".
    pause
    exit /b 1
  )
)

echo Python:
%PY% --version
if errorlevel 1 (
  echo [ERROR] Failed to run Python.
  pause
  exit /b 1
)

echo.
echo Creating .venv ...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] venv failed.
    pause
    exit /b 1
  )
) else (
  echo Using existing .venv
)

echo.
echo Installing requirements ...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo.
    echo Created .env - put your API keys in:
    echo   %cd%\.env
  )
)

echo.
echo ========================================
echo  Setup done.
echo  Next: edit .env then run run_ui.bat
echo ========================================
pause
