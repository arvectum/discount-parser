from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'windows-installed-acceptance.yml'
HARNESS = ROOT / 'scripts' / 'windows_installed_acceptance.ps1'
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


def test_acceptance_evidence_is_uploaded_even_on_failure() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'if: always()' in workflow
    assert '${{ runner.temp }}/dp-ci-002/**' in workflow
    assert 'delivery/windows-build-provenance.json' in workflow
