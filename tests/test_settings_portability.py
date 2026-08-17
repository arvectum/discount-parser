from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.qa.settings_portability import SettingsImportError, build_settings_export, export_settings, import_settings
from src.shared.config import get_settings


def test_export_is_versioned_and_secret_free(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(tmp_path))
    monkeypatch.setenv('DP_TELEGRAM_BOT_TOKEN', '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
    monkeypatch.setenv('DP_TELEGRAM_CHANNEL_ID', '-1004453906792')
    monkeypatch.setenv('DP_TELEGRAM_ADMIN_IDS', '987654321')
    monkeypatch.setenv('DP_PROXY_URL', 'https://alice:letmein@proxy.example:8080')
    get_settings.cache_clear()
    payload = build_settings_export()
    assert payload['schema_version'] == 1
    assert payload['contains_secrets'] is False
    serialized = json.dumps(payload, ensure_ascii=False)
    for secret in ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi', '-1004453906792', '987654321', 'alice', 'letmein'):
        assert secret not in serialized
    destination = export_settings('portable.json')
    assert destination.is_file()
    get_settings.cache_clear()


def test_import_preserves_existing_secret_lines(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    env = runtime / '.env'
    runtime.mkdir()
    env.write_text(
        'DP_TELEGRAM_BOT_TOKEN=SECRET_TOKEN\n'
        'DP_TELEGRAM_CHANNEL_ID=-100123\n'
        'DP_TELEGRAM_ADMIN_IDS=456\n'
        'DP_COLLECT_INTERVAL_MINUTES=120\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('DP_ENV_FILE', str(env))
    get_settings.cache_clear()
    source = tmp_path / 'settings.json'
    source.write_text(json.dumps({
        'schema_version': 1,
        'contains_secrets': False,
        'settings': {'collect_interval_minutes': 45, 'network_mode': 'auto'},
    }), encoding='utf-8')
    result = import_settings(source)
    assert 'collect_interval_minutes' in result['imported']
    text = env.read_text(encoding='utf-8')
    assert 'DP_TELEGRAM_BOT_TOKEN=SECRET_TOKEN' in text
    assert 'DP_TELEGRAM_CHANNEL_ID=-100123' in text
    assert 'DP_TELEGRAM_ADMIN_IDS=456' in text
    assert 'DP_COLLECT_INTERVAL_MINUTES=45' in text
    get_settings.cache_clear()


def test_import_rejects_unknown_or_secret_fields(tmp_path: Path) -> None:
    source = tmp_path / 'bad.json'
    source.write_text(json.dumps({
        'schema_version': 1,
        'contains_secrets': False,
        'settings': {'telegram_bot_token': 'nope'},
    }), encoding='utf-8')
    with pytest.raises(SettingsImportError):
        import_settings(source)
