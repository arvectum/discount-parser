from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from src.jobs.scheduler import run_scheduler
from src.modules.source_registry.seed import seed_registry
from src.qa.doctor import build_doctor_report
from src.shared.config import get_settings
from src.shared.db import check_and_recover_db, session_scope
from src.telegram.runner import run_bot
from src.web.launcher import run_web_panel


def _prepare_runtime_directory() -> Path:
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent
        os.chdir(root)
        return root
    return Path.cwd()


def migrate() -> None:
    _prepare_runtime_directory()
    command.upgrade(Config('alembic.ini'), 'head')
    settings = get_settings()
    with session_scope() as session:
        seed_registry(session, sources_config_path=settings.sources_config_path)


def doctor() -> int:
    _prepare_runtime_directory()
    report = build_doctor_report()
    print(report.to_json())
    return 0 if report.ok else 1


def main() -> int:
    _prepare_runtime_directory()
    check_and_recover_db()
    command_name = sys.argv[1] if len(sys.argv) > 1 else 'web'
    if command_name == 'web':
        run_web_panel()
        return 0
    if command_name == 'bot':
        run_bot()
        return 0
    if command_name == 'scheduler':
        run_scheduler()
        return 0
    if command_name == 'migrate':
        migrate()
        return 0
    if command_name == 'doctor':
        return doctor()
    print(f'Unknown command: {command_name}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
