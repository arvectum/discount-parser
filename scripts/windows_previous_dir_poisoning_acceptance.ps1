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
$Root = Join-Path $env:RUNNER_TEMP "dp-win-001-previous-dir"
$LegacyDir = Join-Path $Root "legacy-install-dir"
$CanonicalDir = Join-Path $env:LOCALAPPDATA "DiscountParser"
$LegacyLog = Join-Path $Root "legacy-install.log"
$UpgradeLog = Join-Path $Root "canonical-upgrade.log"
if (-not $EvidenceOutput) { $EvidenceOutput = Join-Path $Root "previous-dir-poisoning.json" }
$EvidenceOutput = [System.IO.Path]::GetFullPath($EvidenceOutput)

Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $CanonicalDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Root | Out-Null

function Invoke-Setup([string[]]$Arguments) {
    $process = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installer failed with exit code $($process.ExitCode): $($Arguments -join ' ')"
    }
}

try {
    # Seed Inno Setup's previous-install registry state with a deliberately wrong
    # directory. This reproduces the class of physical-machine state that can be
    # left behind by historical /DIR-based installer tests.
    Invoke-Setup @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=$LegacyDir",
        "/LOG=$LegacyLog"
    )

    $LegacyWorker = Join-Path $LegacyDir "DiscountParserWorker.exe"
    if (-not (Test-Path $LegacyWorker -PathType Leaf)) {
        throw "Legacy seed install did not create worker in overridden directory"
    }

    # Put a stale product-owned worker in the one supported production path.
    New-Item -ItemType Directory -Force $CanonicalDir | Out-Null
    $CanonicalWorker = Join-Path $CanonicalDir "DiscountParserWorker.exe"
    Copy-Item "$env:SystemRoot\System32\ping.exe" $CanonicalWorker -Force
    $StaleHash = (Get-FileHash $CanonicalWorker -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($StaleHash -eq $ExpectedHash) {
        throw "Synthetic stale worker unexpectedly matches canonical worker"
    }

    # Critical regression: do NOT pass /DIR. Setup must ignore the poisoned
    # previous install directory and return to {localappdata}\DiscountParser.
    Invoke-Setup @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/LOG=$UpgradeLog"
    )

    if (-not (Test-Path $CanonicalWorker -PathType Leaf)) {
        throw "Canonical worker missing after install without /DIR"
    }
    $ActualHash = (Get-FileHash $CanonicalWorker -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        throw "Setup followed poisoned previous directory or failed to replace canonical stale worker: expected $ExpectedHash actual $ActualHash"
    }

    Push-Location $CanonicalDir
    try {
        & .\DiscountParserWorker.exe status-json | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "status-json failed from canonical install directory: $LASTEXITCODE" }
        & .\DiscountParserWorker.exe db-status | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "db-status failed from canonical install directory: $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }

    $Evidence = [ordered]@{
        schema_version = 1
        task = "DP-WIN-001"
        scenario = "poisoned_previous_install_directory"
        status = "PASS"
        source_sha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
        installer_sha256 = (Get-FileHash $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        legacy_directory = $LegacyDir
        canonical_directory = $CanonicalDir
        stale_worker_sha256 = $StaleHash
        expected_worker_sha256 = $ExpectedHash
        installed_worker_sha256 = $ActualHash
        ignored_previous_app_dir = $true
        status_json = "PASS"
        db_status = "PASS"
        legacy_setup_log = $LegacyLog
        canonical_setup_log = $UpgradeLog
    }
    $parent = Split-Path -Parent $EvidenceOutput
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
    $Evidence | ConvertTo-Json -Depth 6 | Set-Content $EvidenceOutput -Encoding UTF8
    Write-Host "DP-WIN-001 PREVIOUS INSTALL DIRECTORY POISONING: PASS"
    Write-Host "Expected worker SHA256: $ExpectedHash"
    Write-Host "Evidence: $EvidenceOutput"
}
finally {
    # The runner is ephemeral, but keep this gate independent from subsequent
    # tests and avoid carrying AppId/install-path state forward inside the job.
    foreach ($dir in @($CanonicalDir, $LegacyDir)) {
        if (Test-Path $dir) {
            Get-ChildItem -LiteralPath $dir -Filter "unins*.exe" -File -ErrorAction SilentlyContinue |
                Select-Object -First 1 |
                ForEach-Object {
                    Start-Process -FilePath $_.FullName -ArgumentList @(
                        "/VERYSILENT",
                        "/SUPPRESSMSGBOXES",
                        "/NORESTART"
                    ) -Wait -ErrorAction SilentlyContinue | Out-Null
                }
        }
    }
    Remove-Item $CanonicalDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $LegacyDir -Recurse -Force -ErrorAction SilentlyContinue
}
