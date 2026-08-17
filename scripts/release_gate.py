from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "https://arvectum.com/schemas/discount-parser/release-gate/v1"


class GateError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise GateError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ci_evidence(runs_path: Path, commit: str, repository: str) -> dict[str, Any]:
    payload = _load(runs_path)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateError("workflow_runs missing")
    matches = [
        run for run in runs
        if isinstance(run, dict)
        and run.get("name") == "ci"
        and run.get("path") == ".github/workflows/ci.yml"
        and run.get("head_sha") == commit
        and run.get("head_branch") == "main"
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ]
    if not matches:
        raise GateError("no successful canonical main CI push run for exact release commit")
    selected = max(matches, key=lambda item: int(item.get("id", 0)))
    return {
        "schema": SCHEMA,
        "task": "DP-CI-003",
        "gate": "canonical_ci",
        "status": "PASS",
        "repository": repository,
        "source_sha": commit,
        "workflow_run": {
            "id": str(selected["id"]),
            "name": selected["name"],
            "event": selected["event"],
            "head_branch": selected["head_branch"],
            "conclusion": selected["conclusion"],
            "html_url": selected.get("html_url"),
        },
    }


def repro_evidence(
    primary: Path,
    replica: Path,
    primary_provenance: Path,
    replica_provenance: Path,
    commit: str,
) -> dict[str, Any]:
    primary_hash = _sha256(primary)
    replica_hash = _sha256(replica)
    if primary_hash != replica_hash:
        raise GateError(f"release installer reproducibility mismatch: {primary_hash} != {replica_hash}")
    a = _load(primary_provenance)
    b = _load(replica_provenance)
    for label, evidence in (("primary", a), ("replica", b)):
        if evidence.get("source_sha") != commit:
            raise GateError(f"{label} provenance source SHA does not match release commit")
        artifact = evidence.get("artifact")
        if not isinstance(artifact, dict) or artifact.get("sha256") != primary_hash:
            raise GateError(f"{label} provenance installer hash does not match release installer")
    return {
        "schema": SCHEMA,
        "task": "DP-CI-003",
        "gate": "windows_reproducibility",
        "status": "PASS",
        "source_sha": commit,
        "installer_sha256": primary_hash,
        "size_bytes": primary.stat().st_size,
    }


def installed_evidence(installed_path: Path, installer: Path, commit: str) -> dict[str, Any]:
    evidence = _load(installed_path)
    installer_hash = _sha256(installer)
    checks = [
        evidence.get("status") == "PASS",
        evidence.get("source_sha") == commit,
        isinstance(evidence.get("installer"), dict) and evidence["installer"].get("sha256") == installer_hash,
        isinstance(evidence.get("install"), dict) and evidence["install"].get("exit_code") == 0 and evidence["install"].get("database_created") is True,
        isinstance(evidence.get("migrate"), dict) and evidence["migrate"].get("exit_code") == 0,
        isinstance(evidence.get("doctor"), dict) and evidence["doctor"].get("exit_code") == 0 and evidence["doctor"].get("ok") is True,
        isinstance(evidence.get("web"), dict) and evidence["web"].get("status_code") == 200 and evidence["web"].get("onboarding") is True,
        evidence.get("no_unconfigured_workers") is True,
        isinstance(evidence.get("uninstall"), dict) and evidence["uninstall"].get("exit_code") == 0 and evidence["uninstall"].get("payload_removed") is True,
    ]
    if not all(checks):
        raise GateError("installed acceptance evidence does not satisfy release requirements")
    return {
        "schema": SCHEMA,
        "task": "DP-CI-003",
        "gate": "windows_installed_acceptance",
        "status": "PASS",
        "source_sha": commit,
        "installer_sha256": installer_hash,
        "install_exit_code": 0,
        "doctor_ok": True,
        "http_status": 200,
        "uninstall_exit_code": 0,
    }


def bundle(ci: Path, repro: Path, installed: Path, commit: str, tag: str) -> dict[str, Any]:
    items = [_load(ci), _load(repro), _load(installed)]
    expected = {"canonical_ci", "windows_reproducibility", "windows_installed_acceptance"}
    actual = {str(item.get("gate")) for item in items}
    if actual != expected:
        raise GateError(f"release gate evidence set mismatch: {sorted(actual)}")
    for item in items:
        if item.get("schema") != SCHEMA or item.get("task") != "DP-CI-003" or item.get("status") != "PASS":
            raise GateError("invalid or failing release gate evidence")
        if item.get("source_sha") != commit:
            raise GateError("release gate evidence source SHA mismatch")
    hashes = {
        str(item["installer_sha256"])
        for item in items
        if "installer_sha256" in item
    }
    if len(hashes) != 1:
        raise GateError("release Windows gate evidence does not bind one installer hash")
    return {
        "schema": SCHEMA,
        "task": "DP-CI-003",
        "status": "PASS",
        "tag": tag,
        "source_sha": commit,
        "windows_installer_sha256": next(iter(hashes)),
        "gates": {str(item["gate"]): item for item in items},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    ci = sub.add_parser("ci")
    ci.add_argument("--runs-json", required=True)
    ci.add_argument("--commit", required=True)
    ci.add_argument("--repository", required=True)
    ci.add_argument("--output", required=True)

    repro = sub.add_parser("repro")
    repro.add_argument("--primary", required=True)
    repro.add_argument("--replica", required=True)
    repro.add_argument("--primary-provenance", required=True)
    repro.add_argument("--replica-provenance", required=True)
    repro.add_argument("--commit", required=True)
    repro.add_argument("--output", required=True)

    installed = sub.add_parser("installed")
    installed.add_argument("--evidence", required=True)
    installed.add_argument("--installer", required=True)
    installed.add_argument("--commit", required=True)
    installed.add_argument("--output", required=True)

    pack = sub.add_parser("bundle")
    pack.add_argument("--ci", required=True)
    pack.add_argument("--repro", required=True)
    pack.add_argument("--installed", required=True)
    pack.add_argument("--commit", required=True)
    pack.add_argument("--tag", required=True)
    pack.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        if args.command == "ci":
            result = ci_evidence(Path(args.runs_json), args.commit, args.repository)
        elif args.command == "repro":
            result = repro_evidence(Path(args.primary), Path(args.replica), Path(args.primary_provenance), Path(args.replica_provenance), args.commit)
        elif args.command == "installed":
            result = installed_evidence(Path(args.evidence), Path(args.installer), args.commit)
        else:
            result = bundle(Path(args.ci), Path(args.repro), Path(args.installed), args.commit, args.tag)
        _write(Path(args.output), result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GateError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"DP-CI-003: FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
