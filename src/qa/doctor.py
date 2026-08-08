from __future__ import annotations

import json
import socket
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from src.shared.config import get_settings
from src.shared.db import check_db_connection
from src.sources.config import load_source_configs


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class DoctorReport:
    ok: bool
    checks: tuple[DoctorCheck, ...]

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'checks': [asdict(check) for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _data_directory() -> Path:
    settings = get_settings()
    if settings.database_url.startswith('sqlite:///'):
        database_path = Path(settings.database_url.removeprefix('sqlite:///'))
        return database_path.parent if database_path.parent != Path('') else Path('.')
    return Path('.')


def _check_database() -> DoctorCheck:
    ok = check_db_connection()
    return DoctorCheck('database', ok, 'подключение к БД успешно' if ok else 'подключение к БД не удалось')


def _check_writable_directory(path: Path) -> DoctorCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix='.discount-parser-doctor-', dir=path, delete=True):
            pass
        return DoctorCheck('data_directory', True, f'{path.resolve()} доступен для записи')
    except Exception as exc:
        return DoctorCheck('data_directory', False, f'{type(exc).__name__}: {exc}')


def _check_sources() -> DoctorCheck:
    settings = get_settings()
    try:
        configs = load_source_configs(settings.sources_config_path)
    except Exception as exc:
        return DoctorCheck('sources_config', False, f'{type(exc).__name__}: {exc}')
    if not configs:
        return DoctorCheck('sources_config', False, 'В sources.yaml нет источников')
    keys = [item.key for item in configs]
    if len(keys) != len(set(keys)):
        return DoctorCheck('sources_config', False, 'В sources.yaml есть дублирующиеся source key')
    enabled = sum(1 for item in configs if item.enabled)
    return DoctorCheck('sources_config', True, f'источников: {len(configs)}, включено по умолчанию: {enabled}')


def _check_telegram() -> DoctorCheck:
    settings = get_settings()
    missing = []
    if not settings.telegram_bot_token:
        missing.append('bot token')
    if not settings.telegram_channel_id:
        missing.append('channel')
    try:
        admin_ids = settings.telegram_admin_id_set
    except ValueError:
        return DoctorCheck('telegram_config', False, 'admin ID содержит нечисловое значение', required=False)
    if not admin_ids:
        missing.append('admin ID')
    if missing:
        return DoctorCheck('telegram_config', False, 'не заполнено: ' + ', '.join(missing), required=False)
    return DoctorCheck('telegram_config', True, 'Telegram-настройки заполнены', required=False)


def _check_web_port() -> DoctorCheck:
    settings = get_settings()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        result = sock.connect_ex(('127.0.0.1', settings.web_port))
    finally:
        sock.close()
    if result == 0:
        return DoctorCheck('web_port', False, f'127.0.0.1:{settings.web_port} уже занят')
    return DoctorCheck('web_port', True, f'127.0.0.1:{settings.web_port} свободен')


def build_doctor_report(*, check_web_port: bool = True) -> DoctorReport:
    checks: list[DoctorCheck] = [
        _check_database(),
        _check_writable_directory(_data_directory()),
        _check_sources(),
        _check_telegram(),
    ]
    if check_web_port:
        checks.append(_check_web_port())
    ok = all(check.ok for check in checks if check.required)
    return DoctorReport(ok=ok, checks=tuple(checks))
