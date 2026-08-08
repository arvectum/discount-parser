@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo Discount Parser - Setup
 echo ========================================
echo.

if not exist "app\DiscountParser.exe" (
  echo [ERROR] Application files are missing.
  pause
  exit /b 1
)

set "TARGET=%LOCALAPPDATA%\DiscountParser"
if not exist "%TARGET%" mkdir "%TARGET%"

echo Installing to %TARGET% ...
robocopy "app" "%TARGET%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

pushd "%TARGET%"
echo Preparing database...
"DiscountParser.exe" migrate
if errorlevel 1 (
  popd
  goto :fail
)
popd

echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut($desktop + '\Discount Parser.lnk'); $s.TargetPath='%TARGET%\DiscountParser.exe'; $s.WorkingDirectory='%TARGET%'; $s.IconLocation='%TARGET%\DiscountParser.exe,0'; $s.Save()"
if errorlevel 1 goto :fail

echo.
echo Installation completed.
echo Use the "Discount Parser" shortcut on the Desktop.
echo On first launch the browser will open the setup wizard.
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Installation failed.
pause
exit /b 1
