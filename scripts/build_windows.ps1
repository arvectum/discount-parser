$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Remove-Item -Recurse -Force dist-ui, dist-worker, build-ui, build-worker, delivery -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force delivery\app | Out-Null

pyinstaller --noconfirm --clean --onedir --noconsole `
  --distpath dist-ui `
  --workpath build-ui `
  --name DiscountParser `
  --hidden-import src.web.app `
  --hidden-import src.web.application `
  --hidden-import src.web.management_pages `
  --hidden-import src.web.system_routes `
  --collect-all uvicorn `
  --collect-all python_calamine `
  src/distribution_entry.py

pyinstaller --noconfirm --clean --onefile --console `
  --distpath dist-worker `
  --workpath build-worker `
  --name DiscountParserWorker `
  --collect-all python_calamine `
  src/worker_entry.py

Copy-Item dist-ui\DiscountParser\* delivery\app -Recurse -Force
Copy-Item dist-worker\DiscountParserWorker.exe delivery\app\DiscountParserWorker.exe -Force
Copy-Item config delivery\app\config -Recurse -Force
Copy-Item migrations delivery\app\migrations -Recurse -Force
Copy-Item alembic.ini delivery\app\alembic.ini -Force
Copy-Item .env.example delivery\app\.env.example -Force
Copy-Item packaging\windows\install.bat delivery\install.bat -Force

Push-Location delivery\app
.\DiscountParserWorker.exe migrate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
.\DiscountParserWorker.exe doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Pop-Location

$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) {
  throw "Inno Setup 6 not found at $Iscc"
}

& $Iscc "packaging\windows\installer.iss"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item "packaging\windows\output\DiscountParser-Setup.exe" "delivery\DiscountParser-Setup.exe" -Force

Write-Host "LOCAL WINDOWS DELIVERY BUILD: PASSED"
Write-Host "Installer: delivery\DiscountParser-Setup.exe"
