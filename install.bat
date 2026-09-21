@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "DO_PAUSE=1"
if /I "%~1"=="nopause" set "DO_PAUSE=0"
if "%SKIP_PAUSE%"=="1" set "DO_PAUSE=0"

echo ========================================
echo  caption-batch  install
echo ========================================
echo.

set "PYEXE="
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  for /f "delims=" %%i in ('where python') do (
    if not defined PYEXE set "PYEXE=%%i"
  )
)

if not defined PYEXE (
  where py >nul 2>&1
  if %ERRORLEVEL%==0 (
    py -3.12 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.12"
    if not defined PYEXE py -3.11 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.11"
    if not defined PYEXE py -3.10 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.10"
    if not defined PYEXE py -3.13 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.13"
  )
)

if not defined PYEXE (
  echo [ERROR] Python not found.
  echo Install Python 3.10-3.13 from https://www.python.org/downloads/
  echo Check "Add python.exe to PATH" during install.
  if "%DO_PAUSE%"=="1" pause
  exit /b 1
)

echo Python: %PYEXE%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [.venv] Creating virtual environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    if "%DO_PAUSE%"=="1" pause
    exit /b 1
  )
  echo [.venv] Created.
) else (
  echo [.venv] Using existing virtual environment.
)

echo.
echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip upgrade failed
  if "%DO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo Installing: pip install -e ".[dev]"
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
  echo [ERROR] Dependency install failed
  if "%DO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo ========================================
echo  [OK] Install complete
echo  Next: copy .env.example to .env, set keys, then start.bat
echo ========================================
if "%DO_PAUSE%"=="1" pause
exit /b 0
