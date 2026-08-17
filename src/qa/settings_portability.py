from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.shared.config import get_settings
from src.shared.runtime_paths import runtime_root
from src.web.setup import _write_env_values

SETTINGS_EXPORT_SCHEMA_VERSION = 1

_PORTABLE_FIELDS = {
    'collect_interval_minutes': 'DP_COLLECT_INTERVAL_MINUTES',
    'autopost_interval_minutes': 'DP_AUTOPOST_INTERVAL_MINUTES',
    'maintenance_hour': 'DP_MAINTENANCE_HOUR',
    'maintenance_minute': 'DP_MAINTENANCE_MINUTE',
    'stale_after_days': 'DP_STALE_AFTER_DAYS',
    'telegram_default_min_discount': 'DP_TELEGRAM_DEFAULT_MIN_DISCOUNT',
    'telegram_bot_name': 'DP_TELEGRAM_BOT_NAME',
    'network_mode': 'DP_NETWORK_MODE',
    'no_proxy': 'DP_NO_PROXY',
    'telegram_network_route': 'DP_TELEGRAM_NETWORK_ROUTE',
    'telegram_collector_mode': 'DP_TELEGRAM_COLLECTOR_MODE',
    'vk_api_version': 'DP_VK_API_VERSION',
}

_SECRET_FIELD_MARKERS = (
    'token', 'password', 'secret', 'api_id', 'api_hash', 'session',
    'channel_id', 'admin_ids', 'proxy_url', 'proxy_username', 'access_token',
)
_INTEGER_RANGES = {
    'collect_interval_minutes': (1, 10080),
    'autopost_interval_minutes': (1, 10080),
    'maintenance_hour': (0, 23),
    'maintenance_minute': (0, 59),
    'stale_after_days': (1, 365),
    'telegram_default_min_discount': (0, 100),
}
_ENUMS = {
    'network_mode': {'auto', 'direct', 'proxy'},
    'telegram_network_route': {'auto', 'direct', 'proxy'},
    'telegram_collector_mode': {'public', 'mtproto'},
}


class SettingsImportError(ValueError):
    pass


def build_settings_export() -> dict[str, Any]:
    settings = get_settings()
    values = {name: getattr(settings, name) for name in sorted(_PORTABLE_FIELDS)}
    return {
        'schema_version': SETTINGS_EXPORT_SCHEMA_VERSION,
        'generated_at': datetime.now(UTC).isoformat(),
        'product': 'Discount Parser',
        'contains_secrets': False,
        'settings': values,
    }


def export_settings(path: str | Path | None = None) -> Path:
    destination = Path(path) if path else runtime_root() / 'exports' / 'discount-parser-settings.json'
    if not destination.is_absolute():
        destination = (runtime_root() / destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.tmp')
    temporary.write_text(
        json.dumps(build_settings_export(), ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temporary.replace(destination)
    return destination


def _validated_value(name: str, value: Any) -> Any:
    if name in _INTEGER_RANGES:
        if isinstance(value, bool):
            raise SettingsImportError(f'{name} must be an integer')
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsImportError(f'{name} must be an integer') from exc
        minimum, maximum = _INTEGER_RANGES[name]
        if not minimum <= parsed <= maximum:
            raise SettingsImportError(f'{name} must be between {minimum} and {maximum}')
        return parsed
    if name in _ENUMS:
        if not isinstance(value, str) or value not in _ENUMS[name]:
            raise SettingsImportError(f'{name} has unsupported value')
        return value
    if name in {'telegram_bot_name', 'no_proxy', 'vk_api_version'}:
        if value is not None and not isinstance(value, str):
            raise SettingsImportError(f'{name} must be a string')
        if isinstance(value, str) and any(char in value for char in ('\n', '\r', '\x00')):
            raise SettingsImportError(f'{name} must be a single line')
        return value
    return value


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SettingsImportError('settings export must be a JSON object')
    if payload.get('schema_version') != SETTINGS_EXPORT_SCHEMA_VERSION:
        raise SettingsImportError('unsupported settings export schema_version')
    if payload.get('contains_secrets') is not False:
        raise SettingsImportError('settings import refuses payloads that declare secrets')
    values = payload.get('settings')
    if not isinstance(values, dict):
        raise SettingsImportError('settings must be a JSON object')
    unknown = sorted(set(values) - set(_PORTABLE_FIELDS))
    if unknown:
        raise SettingsImportError(f'unknown or non-portable settings: {", ".join(unknown)}')
    validated: dict[str, Any] = {}
    for key, value in values.items():
        lower = key.lower()
        if any(marker in lower for marker in _SECRET_FIELD_MARKERS):
            raise SettingsImportError(f'secret-bearing setting is not portable: {key}')
        validated[key] = _validated_value(key, value)
    return validated


def import_settings(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding='utf-8'))
    values = _validate_payload(payload)
    replacements: dict[str, str] = {}
    for name, value in values.items():
        if value is None:
            value = ''
        rendered = ('true' if value else 'false') if isinstance(value, bool) else str(value)
        replacements[_PORTABLE_FIELDS[name]] = rendered
    _write_env_values(replacements)
    return {'schema_version': SETTINGS_EXPORT_SCHEMA_VERSION, 'imported': sorted(values)}
