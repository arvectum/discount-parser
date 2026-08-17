param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

function Get-InstalledInnoSetupVersion {
    $line = & choco list --exact innosetup --limit-output 2>$null |
        Where-Object { $_ -match '^InnoSetup\|' } |
        Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        throw "Chocolatey failed while reading installed Inno Setup package identity"
    }
    if (-not $line) {
        return $null
    }
    $parts = $line -split '\|', 2
    if ($parts.Count -ne 2) {
        throw "Unexpected Chocolatey package identity: $line"
    }
    return $parts[1].Trim()
}

$installed = Get-InstalledInnoSetupVersion
if ($installed -ne $Version) {
    Write-Host "Installing controlled Inno Setup $Version (currently: $installed)..."
    & choco install innosetup --version=$Version --allow-downgrade -y --no-progress
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to install Inno Setup $Version"
    }
    $installed = Get-InstalledInnoSetupVersion
}

if ($installed -ne $Version) {
    throw "Inno Setup package version mismatch: expected $Version, got $installed"
}

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup $Version package is installed but ISCC.exe was not found"
}

if ($env:GITHUB_ENV) {
    "DP_INNO_SETUP_VERSION=$Version" >> $env:GITHUB_ENV
    "DP_ISCC_PATH=$iscc" >> $env:GITHUB_ENV
}
else {
    $env:DP_INNO_SETUP_VERSION = $Version
    $env:DP_ISCC_PATH = $iscc
}

Write-Host "DP-CI-001 Inno Setup package identity: PASS version=$Version path=$iscc"
