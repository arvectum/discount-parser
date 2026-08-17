from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'windows-installed-acceptance.yml'
HARNESS = ROOT / 'scripts' / 'windows_installed_acceptance.ps1'
RESILIENCE = ROOT / 'scripts' / 'windows_installer_resilience.ps1'
INSTALLER = ROOT / 'packaging' / 'windows' / 'installer.iss'


def test_installed_acceptance_reuses_controlled_windows_build() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'runs-on: windows-2025' in workflow
    assert './scripts/ensure_inno_setup.ps1' in workflow
    assert './scripts/build_windows_ci.ps1' in workflow
    assert './scripts/windows_installed_acceptance.ps1' in workflow
    assert workflow.index('./scripts/build_windows_ci.ps1') < workflow.index('./scripts/windows_installed_acceptance.ps1')


def test_installed_acceptance_has_no_repository_secret_dependency() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8').lower()
    assert 'secrets.' not in workflow
    assert 'telegram_bot_token' not in workflow
    assert 'telegram_channel_id' not in workflow


def test_silent_installer_does_not_autolaunch_gui() -> None:
    installer = INSTALLER.read_text(encoding='utf-8')
    assert '#define MyWorkerExeName "DiscountParserWorker.exe"' in installer
    assert 'Filename: "{app}\\{#MyWorkerExeName}"; Parameters: "migrate"' in installer
    assert '#define MyAppExeName "DiscountParser.exe"' in installer
    assert 'Filename: "{app}\\{#MyAppExeName}"; WorkingDir: "{app}"' in installer
    assert 'postinstall skipifsilent' in installer


def test_desktop_shortcut_is_best_effort_and_cannot_abort_payload_install() -> None:
    installer = INSTALLER.read_text(encoding='utf-8')
    icons_section = installer.split('[Icons]', 1)[1].split('[Code]', 1)[0]
    code_section = installer.split('[Code]', 1)[1].split('[Run]', 1)[0]

    # The customer failure was raised while Inno processed a Desktop [Icons]
    # entry. Desktop must therefore never be an installer-managed fatal icon.
    assert '{autodesktop}' not in icons_section
    assert '{userdesktop}' not in icons_section
    assert 'Name: "{group}\\Discount Parser"' in icons_section

    assert '[Tasks]' in installer
    assert 'Name: "desktopicon"' in installer
    assert "WizardIsTaskSelected('desktopicon')" in code_section
    assert "FileExists(TargetPath)" in code_section
    assert 'CreateShellLink(' in code_section
    assert 'try' in code_section
    assert 'except' in code_section
    assert 'GetExceptionMessage' in code_section
    assert 'desktop shortcut creation failed; installation continues' in code_section
    assert 'CurStep = ssPostInstall' in code_section

    # A manually-created product shortcut remains product-owned on uninstall.
    assert 'Type: files; Name: "{userdesktop}\\{#MyDesktopShortcutName}"' in installer


def test_installed_harness_waits_for_gui_subsystem_installers() -> None:
    harness = HARNESS.read_text(encoding='utf-8')
    assert '$InstallProcess = Start-Process -FilePath $InstallerPath' in harness
    assert '$UninstallProcess = Start-Process -FilePath $Uninstaller.FullName' in harness
    assert harness.count('-Wait -PassThru') >= 2
    assert '$InstallExit = $InstallProcess.ExitCode' in harness
    assert '$UninstallExit = $UninstallProcess.ExitCode' in harness


def test_installed_harness_exercises_runtime_not_staging_directory() -> None:
    harness = HARNESS.read_text(encoding='utf-8')
    required = [
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART',
        'DiscountParserWorker.exe',
        'DiscountParser.exe',
        'discount_parser.db',
        'migrate',
        'doctor',
        '/onboarding/1',
        'Get-Process -Name "DiscountParserWorker"',
        'unins*.exe',
        'payload_removed',
        'installed-acceptance.json',
    ]
    for token in required:
        assert token in harness

    assert 'Source checkout contains runtime database before installed acceptance' in harness
    assert 'Installed migration leaked runtime database into source checkout' in harness
    assert harness.index('Installer failed with exit code') < harness.index('Second installed migrate failed')
    assert harness.index('Second installed migrate failed') < harness.index('Installed web UI did not become ready')
    assert harness.index('Installed web UI did not become ready') < harness.index('Uninstaller failed with exit code')


def test_dp_win_p0_2_resilience_gate_exercises_unicode_and_shortcut_failure() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    harness = RESILIENCE.read_text(encoding='utf-8')

    assert './scripts/windows_installer_resilience.ps1' in workflow
    assert '${{ runner.temp }}/dp-win-p0-2/**' in workflow

    required = [
        'DP-WIN-P0.2',
        'Пользователь-Анастасия',
        'Анастасия\\BlockedDesktop\\DiscountParser',
        '/TASKS=desktopicon',
        'Assert-ShortcutLaunchesTarget',
        "Get-CimInstance Win32_Process -Filter \"Name = 'DiscountParser.exe'\"",
        'Start-Process -FilePath $ShortcutPath',
        'New-Item -ItemType Directory -Path $DesktopShortcut',
        'best_effort_failure_observed',
        'desktop_failure_nonfatal',
        'StartMenuShortcut',
        'reinstall_exit_code',
        'post_uninstall_reinstall_exit_code',
        'desktop_removed_on_uninstall',
        'desktop shortcut creation failed; installation continues',
    ]
    for token in required:
        assert token in harness

    # The blocked-shortcut scenario must require a successful installer exit and
    # the installed payload, not merely observe that shortcut creation failed.
    assert 'if ($blockedExit -ne 0)' in harness
    assert 'Assert-InstalledPayload $BlockedInstallDir' in harness
    assert 'Assert-ShortcutLaunchesTarget $StartMenuShortcut $blockedExe' in harness


def test_acceptance_evidence_is_uploaded_even_on_failure() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'if: always()' in workflow
    assert '${{ runner.temp }}/dp-ci-002/**' in workflow
    assert '${{ runner.temp }}/dp-win-p0-2/**' in workflow
    assert 'delivery/windows-build-provenance.json' in workflow
