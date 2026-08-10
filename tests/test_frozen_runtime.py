from __future__ import annotations

import sys
from pathlib import Path

from src.web.processes import ProcessManager


def test_source_mode_uses_python_module_command(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/python")
    assert ProcessManager._command("bot") == ["/python", "-m", "src.cli", "bot"]


def test_frozen_mode_reexecutes_application(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/app/DiscountParser")
    assert ProcessManager._command("scheduler") == [str(Path(sys.executable)), "scheduler"]
