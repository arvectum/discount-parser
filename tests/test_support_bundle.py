from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from src.qa import support_bundle as module
from src.shared.config import get_settings


def _read_zip_json(archive: zipfile.ZipFile, name: str) -> dict:
    return json.loads(archive.read(name).decode('utf-8'))


def test_sanitize_text_redacts_credentials() -> None:
    raw = (
        'telegram_bot_token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi '
        'password=hunter2 token=abc123 '
        'Authorization: Bearer supersecret\n'
        'Cookie: sid=secretcookie\n'
        'proxy=https://alice:letmein@proxy.example:8080 '
        'telegram_channel_id=-1004453906792 admin_id=123456789'
    )
    clean = module.sanitize_text(raw)
    for secret in (
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi',
        'hunter2',
        'abc123',
        'supersecret',
        'secretcookie',
        'alice',
        'letmein',
        '-1004453906792',
        '123456789',
    ):
        assert secret not in clean
    assert 'REDACTED' in clean


def test_support_bundle_is_allowlisted_redacted_and_hashed(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / 'runtime'
    logs = runtime / 'logs'
    logs.mkdir(parents=True)
    (runtime / '.env').write_text(
        'DP_TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi\n'
        'DP_TELEGRAM_CHANNEL_ID=-1004453906792\n'
        'DP_PROXY_URL=https://alice:letmein@proxy.example:8080\n',
        encoding='utf-8',
    )
    (runtime / 'discount_parser.db').write_bytes(b'PRIVATE DB BYTES')
    (logs / 'app.log').write_text(
        'Authorization: Bearer topsecret\npassword=hunter2\n'
        'telegram_channel_id=-1004453906792\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('DP_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('DP_ENV_FILE', str(runtime / '.env'))
    get_settings.cache_clear()
    monkeypatch.setattr(module, '_safe_doctor_report', lambda: {'ok': True, 'checks': []})
    monkeypatch.setattr(module, '_safe_smoke_report', lambda: {'offers_total': 7})
    monkeypatch.setattr(module, '_safe_operational_status', lambda: {'schema_version': 1, 'state': 'warning'})

    destination = module.build_support_bundle('support/test.zip')
    assert destination == runtime / 'support' / 'test.zip'

    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert names == {
            'diagnostics/runtime.json',
            'diagnostics/configuration.json',
            'diagnostics/operational-status.json',
            'diagnostics/doctor.json',
            'diagnostics/smoke-report.json',
            'logs/app.log',
            'manifest.json',
        }
        assert '.env' not in names
        assert 'discount_parser.db' not in names
        assert _read_zip_json(archive, 'diagnostics/operational-status.json')['state'] == 'warning'

        log_text = archive.read('logs/app.log').decode('utf-8')
        assert 'topsecret' not in log_text
        assert 'hunter2' not in log_text
        assert '-1004453906792' not in log_text

        config = _read_zip_json(archive, 'diagnostics/configuration.json')
        assert config['env_file_present'] is True
        assert config['secret_settings_configured']['telegram_bot_token'] is True
        assert config['secret_settings_configured']['telegram_channel_id'] is True
        assert config['secret_settings_configured']['proxy_url'] is True
        serialized_config = json.dumps(config, ensure_ascii=False)
        assert 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi' not in serialized_config
        assert '-1004453906792' not in serialized_config
        assert 'alice' not in serialized_config
        assert 'letmein' not in serialized_config

        manifest = _read_zip_json(archive, 'manifest.json')
        assert manifest['task'] == 'DP-DIAG-001'
        assert '.env' in manifest['excluded_by_policy']
        assert 'discount_parser.db' in manifest['excluded_by_policy']
        recorded = {item['path']: item for item in manifest['files']}
        assert set(recorded) == names - {'manifest.json'}
        for name, item in recorded.items():
            data = archive.read(name)
            assert item['size_bytes'] == len(data)
            assert item['sha256'] == module._sha256_bytes(data)

    get_settings.cache_clear()


def test_support_bundle_does_not_follow_unlisted_files(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / 'runtime'
    (runtime / 'logs').mkdir(parents=True)
    (runtime / 'logs' / 'app.log').write_text('safe log', encoding='utf-8')
    (runtime / 'customer-secrets.txt').write_text('do not include', encoding='utf-8')
    (runtime / 'logs' / 'random.log').write_text('do not include either', encoding='utf-8')

    monkeypatch.setenv('DP_RUNTIME_ROOT', str(runtime))
    get_settings.cache_clear()
    monkeypatch.setattr(module, '_safe_doctor_report', lambda: {'ok': True})
    monkeypatch.setattr(module, '_safe_smoke_report', lambda: {'available': True})
    monkeypatch.setattr(module, '_safe_operational_status', lambda: {'state': 'ok'})

    destination = module.build_support_bundle(runtime / 'bundle.zip')
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert 'customer-secrets.txt' not in names
        assert 'logs/random.log' not in names
        assert 'logs/app.log' in names

    get_settings.cache_clear()


def test_worker_support_bundle_command_returns_zero_and_writes_zip(tmp_path: Path, monkeypatch, capsys) -> None:
    from src import worker_entry

    destination = tmp_path / 'worker-support.zip'
    monkeypatch.setattr(worker_entry, '_prepare_runtime_directory', lambda: tmp_path)
    monkeypatch.setattr(worker_entry, 'build_support_bundle', lambda output=None: destination)
    monkeypatch.setattr(sys, 'argv', ['DiscountParserWorker.exe', 'support-bundle', str(destination)])

    assert worker_entry.main() == 0
    assert capsys.readouterr().out.strip() == str(destination)
