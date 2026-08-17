from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'build-delivery.yml'


def test_release_requires_all_dp_ci_003_gate_jobs() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'release-source-gate:' in workflow
    assert 'release-repro-gate:' in workflow
    assert 'release-installed-gate:' in workflow
    required_needs = 'needs: [build, release-source-gate, release-repro-gate, release-installed-gate]'
    assert required_needs in workflow
    assert workflow.index(required_needs) < workflow.index('gh release create "$TAG"')


def test_source_gate_requires_exact_current_main_and_exact_ci() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'git rev-parse origin/main' in workflow
    assert 'Release tag must point to the exact current canonical origin/main HEAD' in workflow
    assert 'actions/runs?head_sha=$GITHUB_SHA&event=push&per_page=100' in workflow
    assert 'scripts/release_gate.py ci' in workflow


def test_release_repro_gate_compares_release_artifact_to_independent_build() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    repro = workflow[workflow.index('release-repro-gate:'):workflow.index('release-installed-gate:')]
    assert 'name: discount-parser-windows-x64' in repro
    assert './scripts/build_windows_ci.ps1' in repro
    assert 'scripts/release_gate.py repro' in repro
    assert '--primary primary/DiscountParser-Setup.exe' in repro
    assert '--replica delivery/DiscountParser-Setup.exe' in repro


def test_release_installed_gate_exercises_exact_primary_installer_without_secrets() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    installed = workflow[workflow.index('release-installed-gate:'):workflow.index('\n  release:\n')]
    assert 'scripts/windows_installed_acceptance.ps1' in installed
    assert '-InstallerPath "primary\\DiscountParser-Setup.exe"' in installed
    assert 'scripts/release_gate.py installed' in installed
    assert 'secrets.' not in installed.lower()


def test_release_payload_contains_and_attests_gate_evidence() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    release = workflow[workflow.index('\n  release:\n'):]
    assert 'scripts/release_gate.py bundle' in release
    assert 'release/release-gate.json' in release
    assert 'sha256sum discount-parser-*.zip release-gate.json release-provenance.json' in release
    assert 'Attest release payload and gate evidence' in release
    assert 'release/release-gate.json' in release[release.index('uses: actions/attest@v4'):]
    create = release.index('gh release create "$TAG"')
    publish = release.index('gh release edit "$TAG"')
    assert create < publish
