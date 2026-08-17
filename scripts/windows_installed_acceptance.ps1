param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,
    [string]$EvidenceOutput = "",
    [int]$WebPort = 18765
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$InstallerPath = (Resolve-Path $InstallerPath).Path
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$LogDir = Join-Path $env:RUNNER_TEMP "dp-ci-002"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$InstallerLog = Join-Path $LogDir "installer.log"
$UninstallerLog = Join-Path $LogDir "uninstaller.log"
$DoctorLog = Join-Path $LogDir "doctor.json"
$HttpLog = Join-Path $LogDir "http.txt"
if (-not $EvidenceOutput) {
    $EvidenceOutput = Join-Path $LogDir "installed-acceptance.json"
}
$EvidenceOutput = [System.IO.Path]::GetFullPath($EvidenceOutput)

$Evidence = [ordered]@{
    schema_version = 1
    task = "DP-CI-002"
    status = "IN_PROGRESS"
    source_sha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
    installer = [ordered]@{
        filename = [System.IO.Path]::GetFileName($InstallerPath)
        sha256 = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLowerInvariant()
    }
    install = [ordered]@{
        directory = $InstallDir
        exit_code = $null
        required_payload = @()
        database_created = $false
    }
    migrate = [ordered]@{ exit_code = $null }
    doctor = [ordered]@{ exit_code = $null; ok = $false }
    web = [ordered]@{ port = $WebPort; status_code = $null; onboarding = $false }
    no_unconfigured_workers = $false
    uninstall = [ordered]@{ exit_code = $null; payload_removed = $false }
}

$GuiProcess = $null

function Write-Evidence {
    $parent = Split-Path -Parent $EvidenceOutput
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
    $Evidence | ConvertTo-Json -Depth 8 | Set-Content -Path $EvidenceOutput -Encoding UTF8
}

function Assert-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required installed file missing: $Path"
    }
}

try {
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
    if (Test-Path -LiteralPath (Join-Path (Get-Location) "discount_parser.db")) {
        throw "Source checkout contains runtime database before installed acceptance"
    }

    Write-Host "DP-CI-002 installing $InstallerPath -> $InstallDir"
    $InstallProcess = Start-Process -FilePath $InstallerPath -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=$InstallDir",
        "/LOG=$InstallerLog"
    ) -Wait -PassThru
    $InstallExit = $InstallProcess.ExitCode
    $Evidence.install.exit_code = $InstallExit
    if ($InstallExit -ne 0) {
        throw "Installer failed with exit code $InstallExit"
    }
    if (-not (Test-Path -LiteralPath $InstallerLog -PathType Leaf)) {
        throw "Installer log was not created"
    }

    $RequiredRelativePaths = @(
        "DiscountParser.exe",
        "DiscountParserWorker.exe",
        "alembic.ini",
        ".env.example",
        "config\sources.yaml"
    )
    foreach ($RelativePath in $RequiredRelativePaths) {
        $FullPath = Join-Path $InstallDir $RelativePath
        Assert-File $FullPath
        $Evidence.install.required_payload += $RelativePath
    }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "migrations") -PathType Container)) {
        throw "Required installed migrations directory missing"
    }
    $Evidence.install.required_payload += "migrations/"

    $InstalledDb = Join-Path $InstallDir "discount_parser.db"
    if (-not (Test-Path -LiteralPath $InstalledDb -PathType Leaf)) {
        throw "Installer did not create migrated runtime database"
    }
    $Evidence.install.database_created = $true
    if (Test-Path -LiteralPath (Join-Path (Get-Location) "discount_parser.db")) {
        throw "Installed migration leaked runtime database into source checkout"
    }

    $Worker = Join-Path $InstallDir "DiscountParserWorker.exe"
    Push-Location $InstallDir
    try {
        & $Worker migrate
        $MigrateExit = $LASTEXITCODE
        $Evidence.migrate.exit_code = $MigrateExit
        if ($MigrateExit -ne 0) {
            throw "Second installed migrate failed with exit code $MigrateExit"
        }

        $env:DP_WEB_PORT = [string]$WebPort
        $DoctorOutput = & $Worker doctor 2>&1
        $DoctorExit = $LASTEXITCODE
        $Evidence.doctor.exit_code = $DoctorExit
        $DoctorText = $DoctorOutput -join [Environment]::NewLine
        $DoctorText | Set-Content -Path $DoctorLog -Encoding UTF8
        if ($DoctorExit -ne 0) {
            throw "Installed doctor failed with exit code $DoctorExit"
        }
        $DoctorJson = $DoctorText | ConvertFrom-Json
        if (-not $DoctorJson.ok) {
            throw "Installed doctor returned ok=false"
        }
        $Evidence.doctor.ok = $true
    }
    finally {
        Pop-Location
    }

    $Gui = Join-Path $InstallDir "DiscountParser.exe"
    $env:DP_WEB_PORT = [string]$WebPort
    $GuiProcess = Start-Process -FilePath $Gui -WorkingDirectory $InstallDir -PassThru

    $Response = $null
    $LastHttpError = $null
    for ($Attempt = 1; $Attempt -le 40; $Attempt++) {
        if ($GuiProcess.HasExited) {
            throw "Installed GUI exited before binding web port (exit $($GuiProcess.ExitCode))"
        }
        try {
            $Response = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/onboarding/1" -UseBasicParsing -TimeoutSec 2
            if ($Response.StatusCode -eq 200) { break }
        }
        catch {
            $LastHttpError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Response -or $Response.StatusCode -ne 200) {
        throw "Installed web UI did not become ready on loopback: $LastHttpError"
    }
    $Response.Content | Set-Content -Path $HttpLog -Encoding UTF8
    $Evidence.web.status_code = [int]$Response.StatusCode
    if ($Response.Content -notmatch '/onboarding/1') {
        throw "Installed web UI response is not the local onboarding page"
    }
    $Evidence.web.onboarding = $true

    $UnexpectedWorkers = @(Get-Process -Name "DiscountParserWorker" -ErrorAction SilentlyContinue)
    if ($UnexpectedWorkers.Count -ne 0) {
        throw "Unconfigured installed UI unexpectedly started DiscountParserWorker process(es)"
    }
    $Evidence.no_unconfigured_workers = $true

    if ($GuiProcess -and -not $GuiProcess.HasExited) {
        Stop-Process -Id $GuiProcess.Id -Force
        $GuiProcess.WaitForExit()
    }
    $GuiProcess = $null

    $Uninstaller = Get-ChildItem -LiteralPath $InstallDir -Filter "unins*.exe" -File |
        Sort-Object Name |
        Select-Object -First 1
    if (-not $Uninstaller) {
        throw "Inno Setup uninstaller was not found in installed directory"
    }

    $UninstallProcess = Start-Process -FilePath $Uninstaller.FullName -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/LOG=$UninstallerLog"
    ) -Wait -PassThru
    $UninstallExit = $UninstallProcess.ExitCode
    $Evidence.uninstall.exit_code = $UninstallExit
    if ($UninstallExit -ne 0) {
        throw "Uninstaller failed with exit code $UninstallExit"
    }
    if (-not (Test-Path -LiteralPath $UninstallerLog -PathType Leaf)) {
        throw "Uninstaller log was not created"
    }
    foreach ($Payload in @("DiscountParser.exe", "DiscountParserWorker.exe", "alembic.ini")) {
        if (Test-Path -LiteralPath (Join-Path $InstallDir $Payload)) {
            throw "Installed payload remains after uninstall: $Payload"
        }
    }
    $Evidence.uninstall.payload_removed = $true

    $Evidence.status = "PASS"
    Write-Evidence
    Write-Host "DP-CI-002 INSTALLED WINDOWS ACCEPTANCE: PASS"
    Write-Host "Evidence: $EvidenceOutput"
}
catch {
    $Evidence.status = "FAIL"
    $Evidence.error = $_.Exception.Message
    Write-Evidence
    throw
}
finally {
    if ($GuiProcess -and -not $GuiProcess.HasExited) {
        Stop-Process -Id $GuiProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
