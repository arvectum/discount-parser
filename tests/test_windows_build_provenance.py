from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.windows_build_provenance import (
    ProvenanceError,
    build_evidence,
    compare_evidence,
)


def _fixture(tmp_path: Path, *, max_size: int = 1024) -> tuple[Path, Path, dict[str, str]]:
    manifest_path = tmp_path / "packaging" / "windows" / "build-manifest.json"
    lock_path = tmp_path / "requirements" / "windows-build.lock"
    installer_path = tmp_path / "delivery" / "DiscountParser-Setup.exe"
    manifest_path.parent.mkdir(parents=True)
    lock_path.parent.mkdir(parents=True)
    installer_path.parent.mkdir(parents=True)
    lock_path.write_text("example==1.0\n", encoding="utf-8")
    installer_path.write_bytes(b"deterministic-installer")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task": "DP-CI-001",
                "python_version": "3.11.9",
                "pip_version": "26.2.1",
                "pyinstaller_version": "6.22.1",
                "pyinstaller_hooks_contrib_version": "2026.6",
                "inno_setup_version": "6.7.1",
                "dependency_lock": "requirements/windows-build.lock",
                "python_hash_seed": "1",
                "source_date_epoch": "git-commit-timestamp",
                "installer": {
                    "path": "delivery/DiscountParser-Setup.exe",
                    "max_size_bytes": max_size,
                },
            }
        ),
        encoding="utf-8",
    )
    inputs = {
        "python_version": "3.11.9",
        "pip_version": "26.2.1",
        "pyinstaller_version": "6.22.1",
        "pyinstaller_hooks_contrib_version": "2026.6",
        "inno_setup_version": "6.7.1",
        "python_hash_seed": "1",
        "source_date_epoch": "1700000000",
    }
    return manifest_path, installer_path, inputs


def _evidence(tmp_path: Path, *, source_sha: str = "a" * 40) -> dict:
    manifest_path, installer_path, inputs = _fixture(tmp_path)
    return build_evidence(
        manifest_path=manifest_path,
        installer_path=installer_path,
        source_sha=source_sha,
        inno_version="6.7.1",
        inputs=inputs,
        git_commit_timestamp="1700000000",
    )


def test_matching_independent_build_evidence_passes(tmp_path: Path) -> None:
    first = _evidence(tmp_path / "a")
    second = _evidence(tmp_path / "b")

    compare_evidence(first, second)
    assert first["artifact"]["sha256"] == second["artifact"]["sha256"]
    assert first["artifact"]["size_bytes"] == second["artifact"]["size_bytes"]


def test_changed_installer_bytes_fail_reproducibility(tmp_path: Path) -> None:
    first = _evidence(tmp_path / "a")
    manifest_path, installer_path, inputs = _fixture(tmp_path / "b")
    installer_path.write_bytes(b"different-installer")
    second = build_evidence(
        manifest_path=manifest_path,
        installer_path=installer_path,
        source_sha="a" * 40,
        inno_version="6.7.1",
        inputs=inputs,
        git_commit_timestamp="1700000000",
    )

    with pytest.raises(ProvenanceError, match="SHA-256 differs"):
        compare_evidence(first, second)


def test_installer_size_budget_is_fail_closed(tmp_path: Path) -> None:
    manifest_path, installer_path, inputs = _fixture(tmp_path, max_size=4)

    with pytest.raises(ProvenanceError, match="exceeds DP-CI-001 budget"):
        build_evidence(
            manifest_path=manifest_path,
            installer_path=installer_path,
            source_sha="a" * 40,
            inno_version="6.7.1",
            inputs=inputs,
            git_commit_timestamp="1700000000",
        )


def test_toolchain_version_drift_is_rejected(tmp_path: Path) -> None:
    manifest_path, installer_path, inputs = _fixture(tmp_path)
    inputs["pyinstaller_version"] = "6.99.0"

    with pytest.raises(ProvenanceError, match="pyinstaller_version"):
        build_evidence(
            manifest_path=manifest_path,
            installer_path=installer_path,
            source_sha="a" * 40,
            inno_version="6.7.1",
            inputs=inputs,
            git_commit_timestamp="1700000000",
        )
