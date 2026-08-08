@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo Discount Parser - installation
echo ========================================
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.11 --version >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=py -3.11"
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo [ERROR] Python 3.11+ was not found.
  echo Install Python 3.11 or newer and run this installer again.
  echo https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.11 or newer is required.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :fail
)

set "VPY=%CD%\.venv\Scripts\python.exe"

echo Installing application dependencies...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%VPY%" -m pip install -e ".[dev]"
if errorlevel 1 goto :fail

echo Preparing database...
"%CD%\.venv\Scripts\alembic.exe" upgrade head
if errorlevel 1 goto :fail

echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Discount Parser.lnk'); $s.TargetPath='%CD%\start_web_windows.bat'; $s.WorkingDirectory='%CD%'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,220'; $s.Save()"
if errorlevel 1 goto :fail

echo.
echo ========================================
echo Installation completed successfully.
echo A shortcut named "Discount Parser" was created on the Desktop.
echo Double-click it to open the web interface.
echo ========================================
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Installation failed. See the messages above.
pause
exit /b 1
