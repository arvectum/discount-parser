param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$EvidenceOutput = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$InstallerPath = (Resolve-Path $InstallerPath).Path
$ExpectedWorker = (Resolve-Path "delivery\app\DiscountParserWorker.exe").Path
$ExpectedHash = (Get-FileHash $ExpectedWorker -Algorithm SHA256).Hash.ToLowerInvariant()
$Root = Join-Path $env:RUNNER_TEMP "dp-win-001-worker-overwrite"
$InstallDir = Join-Path $Root "DiscountParser"
$LogPath = Join-Path $Root "setup.log"
if (-not $EvidenceOutput) { $EvidenceOutput = Join-Path $Root "worker-overwrite.json" }
$EvidenceOutput = [System.IO.Path]::GetFullPath($EvidenceOutput)

Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $InstallDir | Out-Null

$InstalledWorker = Join-Path $InstallDir "DiscountParserWorker.exe"
Copy-Item "$env:SystemRoot\System32\ping.exe" $InstalledWorker -Force
$StaleHash = (Get-FileHash $InstalledWorker -Algorithm SHA256).Hash.ToLowerInvariant()
if ($StaleHash -eq $ExpectedHash) { throw "Synthetic stale worker unexpectedly matches canonical worker" }

$staleProcess = Start-Process -FilePath $InstalledWorker -ArgumentList @("-t", "127.0.0.1") -PassThru
Start-Sleep -Milliseconds 750
if ($staleProcess.HasExited) { throw "Synthetic stale worker process exited before installer test" }

$setup = Start-Process -FilePath $InstallerPath -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/SP-",
    "/DIR=$InstallDir",
    "/LOG=$LogPath"
) -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw "Installer failed during stale-worker replacement: $($setup.ExitCode)" }

$staleProcess.Refresh()
if (-not $staleProcess.HasExited) {
    Stop-Process -Id $staleProcess.Id -Force -ErrorAction SilentlyContinue
    throw "Restart Manager did not close the stale worker process"
}

if (-not (Test-Path $InstalledWorker -PathType Leaf)) { throw "Installed worker missing after setup" }
$ActualHash = (Get-FileHash $InstalledWorker -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) {
    throw "Installed worker hash mismatch after setup: expected $ExpectedHash actual $ActualHash"
}

Push-Location $InstallDir
try {
    & .\DiscountParserWorker.exe migrate
    if ($LASTEXITCODE -ne 0) { throw "migrate failed after worker replacement: $LASTEXITCODE" }
    & .\DiscountParserWorker.exe status-json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "status-json failed after worker replacement: $LASTEXITCODE" }
    & .\DiscountParserWorker.exe db-status | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "db-status failed after worker replacement: $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$Evidence = [ordered]@{
    schema_version = 1
    task = "DP-WIN-001"
    scenario = "stale_running_worker_replacement"
    status = "PASS"
    source_sha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
    installer_sha256 = (Get-FileHash $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    stale_worker_sha256 = $StaleHash
    expected_worker_sha256 = $ExpectedHash
    installed_worker_sha256 = $ActualHash
    stale_process_closed_by_setup = $true
    status_json = "PASS"
    db_status = "PASS"
    setup_log = $LogPath
}
$parent = Split-Path -Parent $EvidenceOutput
if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
$Evidence | ConvertTo-Json -Depth 6 | Set-Content $EvidenceOutput -Encoding UTF8
Write-Host "DP-WIN-001 STALE WORKER REPLACEMENT: PASS"
Write-Host "Expected worker SHA256: $ExpectedHash"
Write-Host "Evidence: $EvidenceOutput"
