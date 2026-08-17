from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "https://arvectum.com/schemas/discount-parser/release-provenance/v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(directory: Path) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for path in sorted(directory.glob("discount-parser-*.zip"), key=lambda item: item.name):
        artifacts.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    if not artifacts:
        raise SystemExit("no release archives found")
    return artifacts


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    artifact_dir = Path(args.artifact_dir)
    return {
        "schema": SCHEMA,
        "product": "Discount Parser",
        "repository": args.repository,
        "tag": args.tag,
        "commit_sha": args.commit,
        "workflow": {
            "name": args.workflow,
            "run_id": str(args.run_id),
            "run_attempt": str(args.run_attempt),
            "url": f"{args.server_url}/{args.repository}/actions/runs/{args.run_id}",
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts": collect_artifacts(artifact_dir),
    }


def verify_manifest(manifest_path: Path, artifact_dir: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise SystemExit("unsupported provenance schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SystemExit("manifest contains no artifacts")

    expected_names: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise SystemExit("invalid artifact record")
        filename = item.get("filename")
        expected_hash = item.get("sha256")
        expected_size = item.get("size_bytes")
        if not isinstance(filename, str) or not isinstance(expected_hash, str):
            raise SystemExit("invalid artifact metadata")
        path = artifact_dir / filename
        if not path.is_file():
            raise SystemExit(f"missing artifact: {filename}")
        actual_hash = sha256_file(path)
        actual_size = path.stat().st_size
        if actual_hash != expected_hash:
            raise SystemExit(f"sha256 mismatch: {filename}")
        if actual_size != expected_size:
            raise SystemExit(f"size mismatch: {filename}")
        expected_names.add(filename)

    actual_names = {path.name for path in artifact_dir.glob("discount-parser-*.zip")}
    if actual_names != expected_names:
        raise SystemExit("manifest artifact set does not match release archives")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or verify Discount Parser release provenance")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--verify")
    parser.add_argument("--tag")
    parser.add_argument("--commit")
    parser.add_argument("--repository")
    parser.add_argument("--workflow")
    parser.add_argument("--run-id")
    parser.add_argument("--run-attempt")
    parser.add_argument("--server-url")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.verify:
        return args

    required = [
        "tag",
        "commit",
        "repository",
        "workflow",
        "run_id",
        "run_attempt",
        "server_url",
        "output",
    ]
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("missing generation arguments: " + ", ".join(missing))
    return args


def main() -> None:
    args = parse_args()
    artifact_dir = Path(args.artifact_dir)
    if args.verify:
        verify_manifest(Path(args.verify), artifact_dir)
        return

    manifest = build_manifest(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
