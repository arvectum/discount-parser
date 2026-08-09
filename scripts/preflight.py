from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, args: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"\n== {label} ==")
    completed = subprocess.run(args, cwd=ROOT, env=env or os.environ.copy(), check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def free_local_port() -> int:
    """Return a temporary loopback port for isolated Doctor validation."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    python = sys.executable

    run("compile", [python, "-m", "compileall", "-q", "src", "tests"])
    run("tests", [python, "-m", "pytest"])

    with tempfile.TemporaryDirectory(prefix="discount-parser-preflight-") as tmp:
        db_path = Path(tmp) / "preflight.db"
        env = os.environ.copy()
        env["DP_DATABASE_URL"] = f"sqlite:///{db_path}"
        env["DP_WEB_PORT"] = str(free_local_port())
        run("migration", [python, "-m", "alembic", "upgrade", "head"], env=env)
        run("doctor", [python, "-m", "src.cli", "doctor"], env=env)

    for command in (
        ["--help"],
        ["parse", "--help"],
        ["maintenance", "--help"],
        ["scheduler", "--help"],
        ["bot", "--help"],
        ["run", "--help"],
        ["web", "--help"],
        ["doctor", "--help"],
        ["smoke-report", "--help"],
    ):
        run("cli " + " ".join(command), [python, "-m", "src.cli", *command])

    print("\nPRE-LIVE PREFLIGHT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
