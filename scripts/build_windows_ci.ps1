param(
    [string]$EvidenceOutput = "delivery\windows-build-provenance.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$ManifestPath = "packaging\windows\build-manifest.json"
$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json

if (-not $env:PYTHONHASHSEED) {
    $env:PYTHONHASHSEED = [string]$Manifest.python_hash_seed
}
if (-not $env:SOURCE_DATE_EPOCH) {
    $env:SOURCE_DATE_EPOCH = (& git show -s --format=%ct HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $env:SOURCE_DATE_EPOCH) {
        throw "Unable to derive SOURCE_DATE_EPOCH from the source commit"
    }
}

$ExpectedInnoVersion = [string]$Manifest.inno_setup_version
if ($env:DP_INNO_SETUP_VERSION -ne $ExpectedInnoVersion) {
    throw "Verified Inno Setup identity is required: expected $ExpectedInnoVersion, got $env:DP_INNO_SETUP_VERSION"
}
$IsccPath = $env:DP_ISCC_PATH
if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
    throw "Verified ISCC.exe path is missing: $IsccPath"
}

Write-Host "DP-CI-001 controlled build inputs:"
Write-Host "  Python: $($Manifest.python_version)"
Write-Host "  PyInstaller: $($Manifest.pyinstaller_version)"
Write-Host "  Inno Setup: $ExpectedInnoVersion"
Write-Host "  PYTHONHASHSEED: $env:PYTHONHASHSEED"
Write-Host "  SOURCE_DATE_EPOCH: $env:SOURCE_DATE_EPOCH"

Remove-Item -Recurse -Force dist-ui, dist-worker, build-ui, build-worker, delivery -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force packaging\windows\output -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force delivery\app | Out-Null

Write-Host "Building deterministic UI bundle..."
& python -m PyInstaller --noconfirm --clean --onedir --noconsole `
  --distpath dist-ui `
  --workpath build-ui `
  --name DiscountParser `
  --hidden-import src.web.app `
  --hidden-import src.web.application `
  --hidden-import src.web.management_pages `
  --hidden-import src.web.system_routes `
  --hidden-import src.web.onboarding_routes `
  --hidden-import src.web.source_registry_routes `
  --hidden-import src.web.source_registry_static_routes `
  --collect-submodules src.modules.source_registry `
  --collect-all uvicorn `
  --collect-all python_calamine `
  src/distribution_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller UI build failed with exit code $LASTEXITCODE" }

Write-Host "Building deterministic worker bundle..."
& python -m PyInstaller --noconfirm --clean --onefile --console `
  --distpath dist-worker `
  --workpath build-worker `
  --name DiscountParserWorker `
  --collect-submodules src.modules.source_registry `
  --collect-all python_calamine `
  src/worker_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller worker build failed with exit code $LASTEXITCODE" }

$UiExePath = "dist-ui\DiscountParser\DiscountParser.exe"
$WorkerExePath = "dist-worker\DiscountParserWorker.exe"
if (-not (Test-Path $UiExePath)) { throw "DiscountParser.exe was not produced" }
if (-not (Test-Path $WorkerExePath)) { throw "DiscountParserWorker.exe was not produced" }
if ((Get-Item $UiExePath).Length -le 1024) { throw "DiscountParser.exe is suspiciously small" }
if ((Get-Item $WorkerExePath).Length -le 1024) { throw "DiscountParserWorker.exe is suspiciously small" }

Copy-Item dist-ui\DiscountParser\* delivery\app -Recurse -Force
Copy-Item $WorkerExePath delivery\app\DiscountParserWorker.exe -Force
Copy-Item config delivery\app\config -Recurse -Force
Copy-Item migrations delivery\app\migrations -Recurse -Force
Copy-Item alembic.ini delivery\app\alembic.ini -Force
Copy-Item .env.example delivery\app\.env.example -Force
Copy-Item packaging\windows\install.bat delivery\install.bat -Force

Push-Location delivery\app
try {
    & .\DiscountParserWorker.exe migrate
    if ($LASTEXITCODE -ne 0) { throw "Frozen migration smoke failed with exit code $LASTEXITCODE" }
    & .\DiscountParserWorker.exe doctor
    if ($LASTEXITCODE -ne 0) { throw "Frozen doctor smoke failed with exit code $LASTEXITCODE" }
    Remove-Item .\discount_parser.db, .\discount_parser.db-wal, .\discount_parser.db-shm -Force -ErrorAction SilentlyContinue
    if (Test-Path .\discount_parser.db) { throw "Smoke database must not be packaged" }
}
finally {
    Pop-Location
}

Get-ChildItem delivery\app -Recurse -Force -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem delivery\app -Recurse -Force -Include *.pyc, *.rej, .pytest_cache -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if (-not (Test-Path "delivery\app\DiscountParser.exe")) { throw "DiscountParser.exe missing from staging" }
if (-not (Test-Path "delivery\app\DiscountParserWorker.exe")) { throw "DiscountParserWorker.exe missing from staging" }

Write-Host "Compiling installer with Inno Setup $ExpectedInnoVersion..."
& $IsccPath "packaging\windows\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compiler failed with exit code $LASTEXITCODE" }

$InstallerPath = "packaging\windows\output\DiscountParser-Setup.exe"
if (-not (Test-Path $InstallerPath)) { throw "Installer was not produced" }
Copy-Item $InstallerPath "delivery\DiscountParser-Setup.exe" -Force

$SourceSha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
& python scripts\windows_build_provenance.py create `
  --manifest $ManifestPath `
  --installer "delivery\DiscountParser-Setup.exe" `
  --source-sha $SourceSha `
  --inno-version $ExpectedInnoVersion `
  --output $EvidenceOutput
if ($LASTEXITCODE -ne 0) { throw "Windows build provenance validation failed" }

Write-Host "DP-CI-001 WINDOWS BUILD: PASS"
Write-Host "Installer: delivery\DiscountParser-Setup.exe"
Write-Host "Evidence: $EvidenceOutput"
