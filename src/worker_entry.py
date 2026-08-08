from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from src.jobs.scheduler import run_scheduler
from src.qa.doctor import build_doctor_report
from src.telegram.runner import run_bot


def _prepare_runtime_directory() -> Path:
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent
        os.chdir(root)
        return root
    return Path.cwd()


def migrate() -> int:
    _prepare_runtime_directory()
    command.upgrade(Config('alembic.ini'), 'head')
    return 0


def doctor() -> int:
    _prepare_runtime_directory()
    report = build_doctor_report()
    print(report.to_json())
    return 0 if report.ok else 1


def main() -> int:
    _prepare_runtime_directory()
    command_name = sys.argv[1] if len(sys.argv) > 1 else ''
    if command_name == 'bot':
        run_bot()
        return 0
    if command_name == 'scheduler':
        run_scheduler()
        return 0
    if command_name == 'migrate':
        return migrate()
    if command_name == 'doctor':
        return doctor()
    print(f'Unknown worker command: {command_name}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
