from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "release_provenance.py"
SPEC = importlib.util.spec_from_file_location("release_provenance", MODULE_PATH)
assert SPEC and SPEC.loader
release_provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_provenance)


def generation_args(tmp_path: Path) -> Namespace:
    return Namespace(
        artifact_dir=str(tmp_path),
        tag="v1.2.3",
        commit="a" * 40,
        repository="arvectum/discount-parser",
        workflow="build-delivery",
        run_id="12345",
        run_attempt="1",
        server_url="https://github.com",
        output=str(tmp_path / "release-provenance.json"),
        verify=None,
    )


def test_manifest_binds_release_context_and_artifact_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "discount-parser-windows-x64.zip"
    artifact.write_bytes(b"immutable bytes")

    manifest = release_provenance.build_manifest(generation_args(tmp_path))

    assert manifest["schema"] == release_provenance.SCHEMA
    assert manifest["tag"] == "v1.2.3"
    assert manifest["commit_sha"] == "a" * 40
    assert manifest["workflow"]["run_id"] == "12345"
    assert manifest["artifacts"] == [
        {
            "filename": artifact.name,
            "sha256": release_provenance.sha256_file(artifact),
            "size_bytes": artifact.stat().st_size,
        }
    ]


def test_verify_rejects_tampered_release_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "discount-parser-windows-x64.zip"
    artifact.write_bytes(b"original")
    manifest_path = tmp_path / "release-provenance.json"
    manifest_path.write_text(
        json.dumps(release_provenance.build_manifest(generation_args(tmp_path))),
        encoding="utf-8",
    )

    release_provenance.verify_manifest(manifest_path, tmp_path)
    artifact.write_bytes(b"tampered")

    with pytest.raises(SystemExit, match="sha256 mismatch"):
        release_provenance.verify_manifest(manifest_path, tmp_path)


def test_verify_rejects_unrecorded_release_archive(tmp_path: Path) -> None:
    artifact = tmp_path / "discount-parser-windows-x64.zip"
    artifact.write_bytes(b"recorded")
    manifest_path = tmp_path / "release-provenance.json"
    manifest_path.write_text(
        json.dumps(release_provenance.build_manifest(generation_args(tmp_path))),
        encoding="utf-8",
    )
    (tmp_path / "discount-parser-extra.zip").write_bytes(b"not recorded")

    with pytest.raises(SystemExit, match="artifact set"):
        release_provenance.verify_manifest(manifest_path, tmp_path)


def test_release_workflow_has_fail_closed_provenance_controls() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "build-delivery.yml").read_text(
        encoding="utf-8"
    )

    required_fragments = [
        "git merge-base --is-ancestor",
        "refusing to replace or mutate it",
        "actions/attest@v4",
        "release/SHA256SUMS",
        "release/release-provenance.json",
        "--verify-tag",
        "--draft",
        "--draft=false",
    ]
    for fragment in required_fragments:
        assert fragment in workflow
