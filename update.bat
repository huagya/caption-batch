@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  caption-batch  update
echo ========================================
echo.

if not exist ".git" (
  echo [ERROR] This folder is not a git clone.
  echo Example: git clone https://github.com/huagya/caption-batch.git
  pause
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git not found.
  echo Install Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)

echo Pulling latest code: git pull
git pull
if errorlevel 1 (
  echo [ERROR] git pull failed. Check network or login.
  pause
  exit /b 1
)

echo.

if not exist ".venv\Scripts\python.exe" (
  echo [.venv] Missing. Running install.bat nopause ...
  call "%~dp0install.bat" nopause
  if errorlevel 1 (
    echo [ERROR] Install failed.
    pause
    exit /b 1
  )
) else (
  echo Upgrading pip...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  echo.
  echo Reinstalling: pip install -e ".[dev]" --upgrade
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]" --upgrade
  if errorlevel 1 (
    echo [ERROR] Dependency update failed
    pause
    exit /b 1
  )
)

echo.
echo ========================================
echo  [OK] Code and dependencies updated
echo  Next: double-click start.bat
echo ========================================
pause
exit /b 0
