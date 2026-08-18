from __future__ import annotations

import json
import logging.config
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from src.jobs.scheduler import run_scheduler
from src.modules.source_registry.image_profiles import install_profile_image_extraction
from src.modules.source_registry.seed import seed_registry
from src.qa.doctor import build_doctor_report
from src.qa.operational_status import build_operational_status
from src.qa.recovery import backup_database, database_integrity, recover_if_needed
from src.qa.settings_portability import export_settings, import_settings
from src.qa.source_network_sweep import run_real_source_network_sweep
from src.qa.support_bundle import build_support_bundle
from src.qa.telegram_e2e import run_real_telegram_e2e
from src.shared.config import get_settings
from src.shared.db import session_scope
from src.telegram.runner import run_bot


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass


def _prepare_runtime_directory() -> Path:
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent
        os.chdir(root)
        return root
    return Path.cwd()


def migrate() -> int:
    _prepare_runtime_directory()
    command.upgrade(Config('alembic.ini'), 'head')
    settings = get_settings()
    with session_scope() as session:
        seed_registry(session, sources_config_path=settings.sources_config_path)
    return 0


def doctor() -> int:
    _prepare_runtime_directory()
    report = build_doctor_report()
    print(report.to_json())
    return 0 if report.ok else 1


def status_json() -> int:
    _prepare_runtime_directory()
    print(json.dumps(build_operational_status(), ensure_ascii=False, indent=2, default=str))
    return 0


def db_status() -> int:
    _prepare_runtime_directory()
    payload = database_integrity()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get('healthy') else 1


def db_backup() -> int:
    _prepare_runtime_directory()
    destination = backup_database()
    print(str(destination) if destination else 'NO_DATABASE')
    return 0


def db_recover() -> int:
    _prepare_runtime_directory()
    payload = recover_if_needed()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get('after', {}).get('healthy') else 1


def settings_export() -> int:
    _prepare_runtime_directory()
    output = sys.argv[2] if len(sys.argv) > 2 else None
    destination = export_settings(output)
    print(str(destination))
    return 0


def settings_import() -> int:
    _prepare_runtime_directory()
    if len(sys.argv) < 3:
        print('settings-import requires a JSON file path', file=sys.stderr)
        return 2
    payload = import_settings(sys.argv[2])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def support_bundle() -> int:
    _prepare_runtime_directory()
    output = sys.argv[2] if len(sys.argv) > 2 else None
    destination = build_support_bundle(output)
    print(str(destination))
    return 0


def telegram_e2e() -> int:
    _prepare_runtime_directory()
    output = sys.argv[2] if len(sys.argv) > 2 else None
    payload = run_real_telegram_e2e(output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get('status') == 'PASS' else 1


def source_network_sweep() -> int:
    _prepare_runtime_directory()
    output = sys.argv[2] if len(sys.argv) > 2 else None
    payload = run_real_source_network_sweep(output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get('status') == 'PASS' else 1


def main() -> int:
    _configure_console_encoding()
    _prepare_runtime_directory()
    install_profile_image_extraction()
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
    if command_name == 'status-json':
        return status_json()
    if command_name == 'db-status':
        return db_status()
    if command_name == 'db-backup':
        return db_backup()
    if command_name == 'db-recover':
        return db_recover()
    if command_name == 'settings-export':
        return settings_export()
    if command_name == 'settings-import':
        return settings_import()
    if command_name == 'support-bundle':
        return support_bundle()
    if command_name == 'telegram-e2e':
        return telegram_e2e()
    if command_name == 'source-network-sweep':
        return source_network_sweep()
    print(f'Unknown worker command: {command_name}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
