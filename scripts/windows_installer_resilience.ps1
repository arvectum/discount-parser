param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$EvidenceOutput = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$InstallerPath = (Resolve-Path $InstallerPath).Path
$LogDir = Join-Path $env:RUNNER_TEMP "dp-win-p0-2"
New-Item -ItemType Directory -Force $LogDir | Out-Null
if (-not $EvidenceOutput) {
    $EvidenceOutput = Join-Path $LogDir "installer-resilience.json"
}
$EvidenceOutput = [System.IO.Path]::GetFullPath($EvidenceOutput)

$DesktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
$ProgramsDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
if (-not $DesktopDir -or -not (Test-Path -LiteralPath $DesktopDir -PathType Container)) {
    throw "Current-user Desktop directory is unavailable: $DesktopDir"
}
if (-not $ProgramsDir -or -not (Test-Path -LiteralPath $ProgramsDir -PathType Container)) {
    throw "Current-user Start Menu Programs directory is unavailable: $ProgramsDir"
}

$DesktopShortcut = Join-Path $DesktopDir "Discount Parser.lnk"
$StartMenuShortcut = Join-Path (Join-Path $ProgramsDir "Discount Parser") "Discount Parser.lnk"

$Evidence = [ordered]@{
    schema_version = 1
    task = "DP-WIN-P0.2"
    status = "IN_PROGRESS"
    source_sha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
    installer = [ordered]@{
        filename = [System.IO.Path]::GetFileName($InstallerPath)
        sha256 = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLowerInvariant()
    }
    desktop = [ordered]@{
        path = $DesktopShortcut
        best_effort_failure_observed = $false
    }
    scenarios = [ordered]@{
        unicode_reinstall_cycle = [ordered]@{
            status = "PENDING"
            install_directory = $null
            initial_install_exit_code = $null
            reinstall_exit_code = $null
            uninstall_exit_code = $null
            post_uninstall_reinstall_exit_code = $null
            final_uninstall_exit_code = $null
            desktop_shortcut_valid = $false
            start_menu_shortcut_valid = $false
            desktop_removed_on_uninstall = $false
        }
        blocked_desktop_shortcut = [ordered]@{
            status = "PENDING"
            install_directory = $null
            install_exit_code = $null
            payload_present = $false
            start_menu_shortcut_valid = $false
            desktop_failure_nonfatal = $false
            uninstall_exit_code = $null
        }
    }
}

function Write-Evidence {
    $parent = Split-Path -Parent $EvidenceOutput
    if ($parent) { New-Item -ItemType Directory -Force $parent | Out-Null }
    $Evidence | ConvertTo-Json -Depth 10 | Set-Content -Path $EvidenceOutput -Encoding UTF8
}

function Remove-ShortcutCollision {
    if (Test-Path -LiteralPath $DesktopShortcut) {
        Remove-Item -LiteralPath $DesktopShortcut -Recurse -Force
    }
}

function Invoke-Installer([string]$InstallDir, [string]$LogPath) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $InstallDir) | Out-Null
    $process = Start-Process -FilePath $InstallerPath -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/TASKS=desktopicon",
        "/DIR=$InstallDir",
        "/LOG=$LogPath"
    ) -Wait -PassThru
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
        throw "Installer log was not created: $LogPath"
    }
    return $process.ExitCode
}

function Invoke-Uninstaller([string]$InstallDir, [string]$LogPath) {
    $uninstaller = Get-ChildItem -LiteralPath $InstallDir -Filter "unins*.exe" -File |
        Sort-Object Name |
        Select-Object -First 1
    if (-not $uninstaller) {
        throw "Inno Setup uninstaller was not found in $InstallDir"
    }
    $process = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/LOG=$LogPath"
    ) -Wait -PassThru
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
        throw "Uninstaller log was not created: $LogPath"
    }
    return $process.ExitCode
}

function Assert-InstalledPayload([string]$InstallDir) {
    foreach ($name in @("DiscountParser.exe", "DiscountParserWorker.exe")) {
        $path = Join-Path $InstallDir $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required installed payload missing: $path"
        }
    }
}

function Stop-DiscountParserProcesses {
    Get-Process -Name "DiscountParser" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Assert-ShortcutLaunchesTarget([string]$ShortcutPath, [string]$ExpectedTarget) {
    if (-not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf)) {
        throw "Expected shortcut is missing: $ShortcutPath"
    }

    # WScript.Shell's Shortcut.TargetPath adapter on the hosted runner degrades
    # non-ASCII path text to question marks even when the actual .lnk is valid.
    # Exercise the shortcut through the Windows shell instead and prove that the
    # process that starts is the expected Unicode-path DiscountParser.exe.
    $expectedTargetFull = [System.IO.Path]::GetFullPath($ExpectedTarget)
    Stop-DiscountParserProcesses
    Start-Process -FilePath $ShortcutPath | Out-Null

    $deadline = (Get-Date).AddSeconds(20)
    $matched = $null
    $lastObserved = @()
    while ((Get-Date) -lt $deadline -and -not $matched) {
        $lastObserved = @(
            Get-CimInstance Win32_Process -Filter "Name = 'DiscountParser.exe'" -ErrorAction SilentlyContinue
        )
        foreach ($process in $lastObserved) {
            if (-not $process.ExecutablePath) { continue }
            $actualTarget = [System.IO.Path]::GetFullPath([string]$process.ExecutablePath)
            if ([string]::Equals($actualTarget, $expectedTargetFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                $matched = $process
                break
            }
        }
        if (-not $matched) { Start-Sleep -Milliseconds 500 }
    }

    if (-not $matched) {
        $observedPaths = @($lastObserved | ForEach-Object { $_.ExecutablePath }) -join '; '
        Stop-DiscountParserProcesses
        throw "Shortcut did not launch expected target: $ShortcutPath -> expected $expectedTargetFull; observed: $observedPaths"
    }

    Stop-Process -Id $matched.ProcessId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Stop-DiscountParserProcesses
}

$UnicodeInstallDir = Join-Path $env:RUNNER_TEMP "Пользователь-Анастасия\AppData\Local\DiscountParser"
$BlockedInstallDir = Join-Path $env:RUNNER_TEMP "Анастасия\BlockedDesktop\DiscountParser"
$Evidence.scenarios.unicode_reinstall_cycle.install_directory = $UnicodeInstallDir
$Evidence.scenarios.blocked_desktop_shortcut.install_directory = $BlockedInstallDir

try {
    # Scenario 1: Unicode path + desktop/start-menu launch validation + reinstall
    # + uninstall + reinstall after uninstall. This models a Cyrillic user-profile
    # component without requiring the hosted runner account itself to be renamed.
    Remove-ShortcutCollision
    if (Test-Path -LiteralPath $UnicodeInstallDir) {
        Remove-Item -LiteralPath $UnicodeInstallDir -Recurse -Force
    }

    $initialLog = Join-Path $LogDir "unicode-initial-install.log"
    $initialExit = Invoke-Installer $UnicodeInstallDir $initialLog
    $Evidence.scenarios.unicode_reinstall_cycle.initial_install_exit_code = $initialExit
    if ($initialExit -ne 0) { throw "Unicode-path initial install failed with exit code $initialExit" }
    Assert-InstalledPayload $UnicodeInstallDir

    $unicodeExe = Join-Path $UnicodeInstallDir "DiscountParser.exe"
    Assert-ShortcutLaunchesTarget $DesktopShortcut $unicodeExe
    $Evidence.scenarios.unicode_reinstall_cycle.desktop_shortcut_valid = $true
    Assert-ShortcutLaunchesTarget $StartMenuShortcut $unicodeExe
    $Evidence.scenarios.unicode_reinstall_cycle.start_menu_shortcut_valid = $true

    $reinstallLog = Join-Path $LogDir "unicode-reinstall.log"
    $reinstallExit = Invoke-Installer $UnicodeInstallDir $reinstallLog
    $Evidence.scenarios.unicode_reinstall_cycle.reinstall_exit_code = $reinstallExit
    if ($reinstallExit -ne 0) { throw "In-place reinstall failed with exit code $reinstallExit" }
    Assert-InstalledPayload $UnicodeInstallDir
    Assert-ShortcutLaunchesTarget $DesktopShortcut $unicodeExe
    Assert-ShortcutLaunchesTarget $StartMenuShortcut $unicodeExe

    $firstUninstallLog = Join-Path $LogDir "unicode-uninstall.log"
    $firstUninstallExit = Invoke-Uninstaller $UnicodeInstallDir $firstUninstallLog
    $Evidence.scenarios.unicode_reinstall_cycle.uninstall_exit_code = $firstUninstallExit
    if ($firstUninstallExit -ne 0) { throw "Unicode-path uninstall failed with exit code $firstUninstallExit" }
    if (Test-Path -LiteralPath $DesktopShortcut -PathType Leaf) {
        throw "Desktop shortcut remained after uninstall: $DesktopShortcut"
    }
    $Evidence.scenarios.unicode_reinstall_cycle.desktop_removed_on_uninstall = $true

    $postUninstallLog = Join-Path $LogDir "unicode-post-uninstall-reinstall.log"
    $postUninstallExit = Invoke-Installer $UnicodeInstallDir $postUninstallLog
    $Evidence.scenarios.unicode_reinstall_cycle.post_uninstall_reinstall_exit_code = $postUninstallExit
    if ($postUninstallExit -ne 0) { throw "Reinstall after uninstall failed with exit code $postUninstallExit" }
    Assert-InstalledPayload $UnicodeInstallDir
    Assert-ShortcutLaunchesTarget $DesktopShortcut $unicodeExe
    Assert-ShortcutLaunchesTarget $StartMenuShortcut $unicodeExe

    $finalUninstallLog = Join-Path $LogDir "unicode-final-uninstall.log"
    $finalUninstallExit = Invoke-Uninstaller $UnicodeInstallDir $finalUninstallLog
    $Evidence.scenarios.unicode_reinstall_cycle.final_uninstall_exit_code = $finalUninstallExit
    if ($finalUninstallExit -ne 0) { throw "Final Unicode-path uninstall failed with exit code $finalUninstallExit" }
    $Evidence.scenarios.unicode_reinstall_cycle.status = "PASS"

    # Scenario 2: force CreateShellLink to fail by occupying the .lnk pathname
    # with a directory. The exact HRESULT can differ from a customer's ACL error,
    # but this exercises the same Inno CreateShellLink exception boundary. Setup
    # must still return success, keep the payload, and provide the Start Menu path.
    Remove-ShortcutCollision
    if (Test-Path -LiteralPath $BlockedInstallDir) {
        Remove-Item -LiteralPath $BlockedInstallDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $DesktopShortcut -Force | Out-Null

    $blockedLog = Join-Path $LogDir "blocked-desktop-install.log"
    $blockedExit = Invoke-Installer $BlockedInstallDir $blockedLog
    $Evidence.scenarios.blocked_desktop_shortcut.install_exit_code = $blockedExit
    if ($blockedExit -ne 0) { throw "Installer rolled back/failed when Desktop shortcut could not be saved: exit $blockedExit" }
    Assert-InstalledPayload $BlockedInstallDir
    $Evidence.scenarios.blocked_desktop_shortcut.payload_present = $true

    if (-not (Test-Path -LiteralPath $DesktopShortcut -PathType Container)) {
        throw "Desktop shortcut blocker directory unexpectedly disappeared; failure path was not exercised"
    }
    $blockedText = Get-Content -LiteralPath $blockedLog -Raw
    if ($blockedText -notmatch 'DP-WIN-P0\.2: warning: desktop shortcut creation failed; installation continues') {
        throw "Installer log does not prove the best-effort Desktop shortcut failure path was exercised"
    }
    $Evidence.desktop.best_effort_failure_observed = $true
    $Evidence.scenarios.blocked_desktop_shortcut.desktop_failure_nonfatal = $true

    $blockedExe = Join-Path $BlockedInstallDir "DiscountParser.exe"
    Assert-ShortcutLaunchesTarget $StartMenuShortcut $blockedExe
    $Evidence.scenarios.blocked_desktop_shortcut.start_menu_shortcut_valid = $true

    # Remove only the synthetic test blocker before uninstall; production
    # [UninstallDelete] owns real .lnk files, not arbitrary colliding directories.
    Remove-Item -LiteralPath $DesktopShortcut -Recurse -Force
    $blockedUninstallLog = Join-Path $LogDir "blocked-desktop-uninstall.log"
    $blockedUninstallExit = Invoke-Uninstaller $BlockedInstallDir $blockedUninstallLog
    $Evidence.scenarios.blocked_desktop_shortcut.uninstall_exit_code = $blockedUninstallExit
    if ($blockedUninstallExit -ne 0) { throw "Blocked-Desktop scenario uninstall failed with exit code $blockedUninstallExit" }
    $Evidence.scenarios.blocked_desktop_shortcut.status = "PASS"

    $Evidence.status = "PASS"
    Write-Evidence
    Write-Host "DP-WIN-P0.2 INSTALLER RESILIENCE: PASS"
    Write-Host "Evidence: $EvidenceOutput"
}
catch {
    $Evidence.status = "FAIL"
    $Evidence.error = $_.Exception.Message
    Write-Evidence
    throw
}
finally {
    Stop-DiscountParserProcesses
    if (Test-Path -LiteralPath $DesktopShortcut -PathType Container) {
        Remove-Item -LiteralPath $DesktopShortcut -Recurse -Force -ErrorAction SilentlyContinue
    }
}
