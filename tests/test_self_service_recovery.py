from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.qa import recovery
from src.shared.config import get_settings


def _point_database(monkeypatch, tmp_path: Path) -> Path:
    db = tmp_path / 'discount_parser.db'
    monkeypatch.setenv('DP_DATABASE_URL', f'sqlite:///{db}')
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    get_settings.cache_clear()
    return db


def test_database_integrity_healthy_and_backup(monkeypatch, tmp_path: Path) -> None:
    db = _point_database(monkeypatch, tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute('create table sample(id integer primary key, value text)')
        connection.execute("insert into sample(value) values ('ok')")
        connection.commit()
    status = recovery.database_integrity()
    assert status['exists'] is True
    assert status['healthy'] is True
    backup = recovery.backup_database()
    assert backup is not None
    copied = backup / db.name
    assert copied.is_file()
    with sqlite3.connect(copied) as connection:
        assert connection.execute('select value from sample').fetchone()[0] == 'ok'
    get_settings.cache_clear()


def test_recover_if_needed_is_noop_for_healthy_database(monkeypatch, tmp_path: Path) -> None:
    db = _point_database(monkeypatch, tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute('create table sample(id integer primary key)')
        connection.commit()
    result = recovery.recover_if_needed()
    assert result['action'] == 'none'
    assert result['recovered'] is False
    assert result['after']['healthy'] is True
    get_settings.cache_clear()


def test_worker_recovery_commands_emit_machine_readable_output(monkeypatch, capsys, tmp_path: Path) -> None:
    from src import worker_entry
    monkeypatch.setattr(worker_entry, '_prepare_runtime_directory', lambda: tmp_path)
    monkeypatch.setattr(worker_entry, 'database_integrity', lambda: {'healthy': True, 'exists': True})
    monkeypatch.setattr(worker_entry.sys, 'argv', ['DiscountParserWorker.exe', 'db-status'])
    assert worker_entry.main() == 0
    assert json.loads(capsys.readouterr().out)['healthy'] is True
    monkeypatch.setattr(worker_entry, 'recover_if_needed', lambda: {'after': {'healthy': True}, 'recovered': True})
    monkeypatch.setattr(worker_entry.sys, 'argv', ['DiscountParserWorker.exe', 'db-recover'])
    assert worker_entry.main() == 0
    assert json.loads(capsys.readouterr().out)['recovered'] is True
