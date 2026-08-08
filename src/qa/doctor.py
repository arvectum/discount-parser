from __future__ import annotations

import json
import socket
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import inspect, select

from src.modules.source_registry.collectors import COLLECTORS
from src.modules.source_registry.models import RegisteredSource
from src.shared.config import get_settings
from src.shared.db import check_db_connection, create_session, get_engine
from src.sources.config import load_source_configs
from src.sources.registry import build_adapter


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
    try:
        for config in configs:
            build_adapter(config)
    except Exception as exc:
        return DoctorCheck('sources_config', False, f'Ошибка adapter registry: {type(exc).__name__}: {exc}')
    enabled = sum(1 for item in configs if item.enabled)
    return DoctorCheck('sources_config', True, f'источников: {len(configs)}, adapters: OK, включено по умолчанию: {enabled}')


def _check_source_registry() -> DoctorCheck:
    required_tables = {
        'registered_sources',
        'source_keywords',
        'source_candidates',
        'source_keyword_links',
        'source_items',
    }
    try:
        tables = set(inspect(get_engine()).get_table_names())
    except Exception as exc:
        return DoctorCheck('source_registry', False, f'{type(exc).__name__}: {exc}')
    missing = sorted(required_tables - tables)
    if missing:
        return DoctorCheck('source_registry', False, 'не применена миграция: ' + ', '.join(missing))

    try:
        with create_session() as session:
            sources = session.scalars(select(RegisteredSource)).all()
    except Exception as exc:
        return DoctorCheck('source_registry', False, f'не удалось прочитать registry: {type(exc).__name__}: {exc}')

    unknown_collectors = sorted(
        {source.collector_type for source in sources if source.collector_type != 'legacy_adapter' and source.collector_type not in COLLECTORS}
    )
    if unknown_collectors:
        return DoctorCheck('source_registry', False, 'неизвестные collectors: ' + ', '.join(unknown_collectors))

    enabled = sum(1 for source in sources if source.enabled)
    platforms = sorted({source.platform for source in sources})
    return DoctorCheck(
        'source_registry',
        True,
        f'зарегистрировано: {len(sources)}, enabled: {enabled}, platforms: {", ".join(platforms) if platforms else "—"}',
    )


def _check_social_credentials() -> DoctorCheck:
    settings = get_settings()
    try:
        with create_session() as session:
            enabled_vk = session.scalar(
                select(RegisteredSource.id).where(
                    RegisteredSource.enabled.is_(True),
                    RegisteredSource.collector_type == 'vk_api',
                ).limit(1)
            )
    except Exception:
        # source_registry required check will report schema problems.
        return DoctorCheck('social_credentials', True, 'registry пока недоступен для credential-check', required=False)
    missing: list[str] = []
    if enabled_vk is not None and not settings.vk_access_token:
        missing.append('DP_VK_ACCESS_TOKEN')
    if missing:
        return DoctorCheck('social_credentials', False, 'для включённых collectors не заполнено: ' + ', '.join(missing), required=False)
    return DoctorCheck('social_credentials', True, 'credential-dependent collectors настроены или не используются', required=False)


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
        _check_source_registry(),
        _check_social_credentials(),
        _check_telegram(),
    ]
    if check_web_port:
        checks.append(_check_web_port())
    ok = all(check.ok for check in checks if check.required)
    return DoctorReport(ok=ok, checks=tuple(checks))
