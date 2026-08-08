@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Discount Parser is not installed yet.
  echo Run install_windows.bat first.
  pause
  exit /b 1
)

"%CD%\.venv\Scripts\python.exe" -m src.cli web
endlocal
