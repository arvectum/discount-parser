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

echo Starting Telegram bot...
start "Discount Parser - Bot" cmd /k "cd /d \"%CD%\" && \"%PYTHON%\" -m src.cli bot"

echo Starting scheduler...
start "Discount Parser - Scheduler" cmd /k "cd /d \"%CD%\" && \"%PYTHON%\" -m src.cli scheduler"

echo.
echo Started in two windows:
echo   1. Telegram bot
echo   2. Scheduler

echo Close those windows or press Ctrl+C in each to stop the program.
echo.
pause
endlocal
