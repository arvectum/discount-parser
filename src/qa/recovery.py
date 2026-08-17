from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.shared.config import get_settings
from src.shared.db import check_and_recover_db, reset_db_runtime
from src.shared.runtime_paths import runtime_root


class RecoveryError(RuntimeError):
    pass


def sqlite_database_path() -> Path:
    url = get_settings().database_url
    prefix = 'sqlite:///'
    if not url.startswith(prefix):
        raise RecoveryError('self-service database recovery is available only for SQLite')
    raw = url.removeprefix(prefix)
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def database_integrity() -> dict[str, Any]:
    path = sqlite_database_path()
    if not path.exists():
        return {'exists': False, 'healthy': True, 'detail': 'database_not_created', 'path': str(path)}
    try:
        connection = sqlite3.connect(str(path), timeout=5)
        try:
            row = connection.execute('PRAGMA quick_check').fetchone()
            detail = str(row[0]) if row else 'no_result'
            healthy = detail.lower() == 'ok'
        finally:
            connection.close()
        return {'exists': True, 'healthy': healthy, 'detail': detail, 'path': str(path)}
    except Exception as exc:
        return {
            'exists': True,
            'healthy': False,
            'detail': f'{type(exc).__name__}: {exc}',
            'path': str(path),
        }


def backup_database() -> Path | None:
    path = sqlite_database_path()
    if not path.exists():
        return None

    reset_db_runtime()
    timestamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    destination = runtime_root() / 'recovery' / f'db-backup-{timestamp}'
    destination.mkdir(parents=True, exist_ok=False)

    copied = False
    for suffix in ('', '-wal', '-shm'):
        source = path.with_name(path.name + suffix)
        if source.exists():
            shutil.copy2(source, destination / source.name)
            copied = True
    if not copied:
        destination.rmdir()
        return None
    return destination


def recover_if_needed() -> dict[str, Any]:
    before = database_integrity()
    if before['healthy']:
        return {'action': 'none', 'before': before, 'backup': None, 'recovered': False, 'after': before}

    backup = backup_database()
    recovered = check_and_recover_db()
    after = database_integrity()
    return {
        'action': 'recover',
        'before': before,
        'backup': str(backup) if backup else None,
        'recovered': bool(recovered),
        'after': after,
    }
