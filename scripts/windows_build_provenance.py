from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


class ProvenanceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvenanceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError(f"expected JSON object in {path}")
    return value


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ProvenanceError(f"required package is not installed: {name}") from exc


def _git_commit_timestamp() -> str:
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def controlled_inputs(manifest: dict[str, Any], *, inno_version: str) -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "pip_version": _package_version("pip"),
        "pyinstaller_version": _package_version("pyinstaller"),
        "pyinstaller_hooks_contrib_version": _package_version("pyinstaller-hooks-contrib"),
        "inno_setup_version": inno_version,
        "python_hash_seed": os.environ.get("PYTHONHASHSEED", ""),
        "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH", ""),
    }


def validate_controlled_inputs(
    manifest: dict[str, Any], inputs: dict[str, str], *, git_commit_timestamp: str
) -> None:
    expected = {
        "python_version": str(manifest["python_version"]),
        "pip_version": str(manifest["pip_version"]),
        "pyinstaller_version": str(manifest["pyinstaller_version"]),
        "pyinstaller_hooks_contrib_version": str(
            manifest["pyinstaller_hooks_contrib_version"]
        ),
        "inno_setup_version": str(manifest["inno_setup_version"]),
        "python_hash_seed": str(manifest["python_hash_seed"]),
        "source_date_epoch": git_commit_timestamp,
    }
    mismatches = [
        f"{key}: expected {expected[key]!r}, got {inputs.get(key)!r}"
        for key in expected
        if inputs.get(key) != expected[key]
    ]
    if mismatches:
        raise ProvenanceError("controlled build inputs differ:\n" + "\n".join(mismatches))


def build_evidence(
    *,
    manifest_path: Path,
    installer_path: Path,
    source_sha: str,
    inno_version: str,
    inputs: dict[str, str] | None = None,
    git_commit_timestamp: str | None = None,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    if manifest.get("task") != "DP-CI-001" or manifest.get("schema_version") != 1:
        raise ProvenanceError("unsupported Windows build manifest")

    installer = manifest.get("installer")
    if not isinstance(installer, dict):
        raise ProvenanceError("manifest.installer must be an object")
    max_size = int(installer["max_size_bytes"])

    if not installer_path.is_file():
        raise ProvenanceError(f"installer does not exist: {installer_path}")
    size = installer_path.stat().st_size
    if size > max_size:
        raise ProvenanceError(
            f"installer size {size} exceeds DP-CI-001 budget {max_size} bytes"
        )

    lock_path = Path(str(manifest["dependency_lock"]))
    if not lock_path.is_absolute():
        lock_path = manifest_path.parents[2] / lock_path
    if not lock_path.is_file():
        raise ProvenanceError(f"dependency lock does not exist: {lock_path}")

    actual_inputs = inputs if inputs is not None else controlled_inputs(manifest, inno_version=inno_version)
    timestamp = git_commit_timestamp if git_commit_timestamp is not None else _git_commit_timestamp()
    validate_controlled_inputs(manifest, actual_inputs, git_commit_timestamp=timestamp)

    return {
        "schema_version": 1,
        "task": "DP-CI-001",
        "source_sha": source_sha,
        "artifact": {
            "filename": installer_path.name,
            "size_bytes": size,
            "sha256": sha256_file(installer_path),
            "max_size_bytes": max_size,
        },
        "controlled_inputs": actual_inputs,
        "dependency_lock": {
            "path": str(manifest["dependency_lock"]),
            "sha256": sha256_file(lock_path),
        },
    }


def compare_evidence(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("source_sha") != second.get("source_sha"):
        raise ProvenanceError("replicas were not built from the same source SHA")
    if first.get("controlled_inputs") != second.get("controlled_inputs"):
        raise ProvenanceError("replicas used different controlled build inputs")
    if first.get("dependency_lock") != second.get("dependency_lock"):
        raise ProvenanceError("replicas used different dependency locks")

    first_artifact = first.get("artifact", {})
    second_artifact = second.get("artifact", {})
    if first_artifact.get("sha256") != second_artifact.get("sha256"):
        raise ProvenanceError(
            "Windows installer is not reproducible: SHA-256 differs: "
            f"{first_artifact.get('sha256')} != {second_artifact.get('sha256')}"
        )
    if first_artifact.get("size_bytes") != second_artifact.get("size_bytes"):
        raise ProvenanceError("Windows installer is not reproducible: byte size differs")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _create(args: argparse.Namespace) -> None:
    evidence = build_evidence(
        manifest_path=Path(args.manifest),
        installer_path=Path(args.installer),
        source_sha=args.source_sha,
        inno_version=args.inno_version,
    )
    write_json(Path(args.output), evidence)
    print(json.dumps(evidence, sort_keys=True))


def _compare(args: argparse.Namespace) -> None:
    first = load_json(Path(args.first))
    second = load_json(Path(args.second))
    compare_evidence(first, second)
    print(
        "DP-CI-001 REPRODUCIBILITY: PASS "
        f"sha256={first['artifact']['sha256']} size={first['artifact']['size_bytes']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Discount Parser Windows build provenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--manifest", required=True)
    create.add_argument("--installer", required=True)
    create.add_argument("--source-sha", required=True)
    create.add_argument("--inno-version", required=True)
    create.add_argument("--output", required=True)
    create.set_defaults(func=_create)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--first", required=True)
    compare.add_argument("--second", required=True)
    compare.set_defaults(func=_compare)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ProvenanceError, subprocess.CalledProcessError, KeyError, ValueError) as exc:
        print(f"DP-CI-001: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
