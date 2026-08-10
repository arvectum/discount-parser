from __future__ import annotations

import os
import sys
from pathlib import Path


def runtime_root() -> Path:
    """Return the directory that owns mutable runtime state.

    Frozen builds keep .env and SQLite next to the executable. Source/dev runs
    keep the existing cwd-based behaviour so local workflows remain simple.
    DP_RUNTIME_ROOT is an explicit override used by tests and controlled tools.
    """
    override = os.environ.get("DP_RUNTIME_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def env_path() -> Path:
    override = os.environ.get("DP_ENV_FILE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return runtime_root() / ".env"


def env_example_path() -> Path:
    return runtime_root() / ".env.example"
