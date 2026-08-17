from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release_gate import GateError, bundle, ci_evidence, installed_evidence, repro_evidence


COMMIT = "a" * 40


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_ci_gate_requires_successful_exact_main_push(tmp_path: Path) -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 10,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "head_sha": COMMIT,
                "head_branch": "main",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://example.test/run/10",
            }
        ]
    }
    evidence = ci_evidence(_write(tmp_path / "runs.json", payload), COMMIT, "arvectum/discount-parser")
    assert evidence["status"] == "PASS"
    assert evidence["workflow_run"]["id"] == "10"


@pytest.mark.parametrize("field,value", [("head_sha", "b" * 40), ("head_branch", "feature"), ("event", "pull_request"), ("conclusion", "failure")])
def test_ci_gate_rejects_noncanonical_run(tmp_path: Path, field: str, value: str) -> None:
    run = {
        "id": 10,
        "name": "ci",
        "path": ".github/workflows/ci.yml",
        "head_sha": COMMIT,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    run[field] = value
    with pytest.raises(GateError):
        ci_evidence(_write(tmp_path / "runs.json", {"workflow_runs": [run]}), COMMIT, "repo")


def _provenance(path: Path, sha: str) -> Path:
    return _write(path, {"source_sha": COMMIT, "artifact": {"sha256": sha}})


def test_repro_gate_binds_exact_release_installer(tmp_path: Path) -> None:
    primary = tmp_path / "primary.exe"
    replica = tmp_path / "replica.exe"
    primary.write_bytes(b"same-installer")
    replica.write_bytes(b"same-installer")
    import hashlib
    sha = hashlib.sha256(b"same-installer").hexdigest()
    evidence = repro_evidence(primary, replica, _provenance(tmp_path / "a.json", sha), _provenance(tmp_path / "b.json", sha), COMMIT)
    assert evidence["installer_sha256"] == sha


def test_repro_gate_rejects_different_bytes(tmp_path: Path) -> None:
    primary = tmp_path / "primary.exe"
    replica = tmp_path / "replica.exe"
    primary.write_bytes(b"one")
    replica.write_bytes(b"two")
    with pytest.raises(GateError, match="mismatch"):
        repro_evidence(primary, replica, _write(tmp_path / "a.json", {}), _write(tmp_path / "b.json", {}), COMMIT)


def test_installed_gate_requires_all_dp_ci_002_acceptance(tmp_path: Path) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    import hashlib
    sha = hashlib.sha256(b"installer").hexdigest()
    raw = {
        "status": "PASS",
        "source_sha": COMMIT,
        "installer": {"sha256": sha},
        "install": {"exit_code": 0, "database_created": True},
        "migrate": {"exit_code": 0},
        "doctor": {"exit_code": 0, "ok": True},
        "web": {"status_code": 200, "onboarding": True},
        "no_unconfigured_workers": True,
        "uninstall": {"exit_code": 0, "payload_removed": True},
    }
    evidence = installed_evidence(_write(tmp_path / "installed.json", raw), installer, COMMIT)
    assert evidence["status"] == "PASS"

    raw["doctor"]["ok"] = False
    with pytest.raises(GateError):
        installed_evidence(_write(tmp_path / "installed-fail.json", raw), installer, COMMIT)


def test_bundle_requires_all_three_gates_and_one_installer_hash(tmp_path: Path) -> None:
    common = {"schema": "https://arvectum.com/schemas/discount-parser/release-gate/v1", "task": "DP-CI-003", "status": "PASS", "source_sha": COMMIT}
    ci = _write(tmp_path / "ci.json", {**common, "gate": "canonical_ci"})
    repro = _write(tmp_path / "repro.json", {**common, "gate": "windows_reproducibility", "installer_sha256": "1" * 64})
    installed = _write(tmp_path / "installed.json", {**common, "gate": "windows_installed_acceptance", "installer_sha256": "1" * 64})
    result = bundle(ci, repro, installed, COMMIT, "v1.0.0")
    assert result["status"] == "PASS"
    assert result["windows_installer_sha256"] == "1" * 64
