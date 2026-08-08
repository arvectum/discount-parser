@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo Discount Parser - one-click launcher
echo ========================================

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found: .venv
  echo Run the installation steps from docs\USER_INSTALLATION_GUIDE.md first.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [ERROR] .env file not found.
  echo Copy .env.example to .env and fill in Telegram settings first.
  pause
  exit /b 1
)

set "PYTHON=%CD%\.venv\Scripts\python.exe"

echo Starting Discount Parser...
echo Telegram bot + scheduler will run in this window.
echo Press Ctrl+C to stop.
echo.

"%PYTHON%" -m src.cli run

if errorlevel 1 (
  echo.
  echo [ERROR] Discount Parser stopped with an error.
  pause
)

endlocal
