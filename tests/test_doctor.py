from __future__ import annotations

from pathlib import Path

import pytest

from src.qa import doctor
from src.shared.config import get_settings


def test_doctor_optional_telegram_does_not_fail_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = tmp_path / 'sources.yaml'
    sources.write_text(
        'sources:\n  - key: demo\n    name: Demo\n    adapter: promokood\n    base_url: https://example.test\n    enabled: true\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'doctor.db'}")
    monkeypatch.setenv('DP_SOURCES_CONFIG_PATH', str(sources))
    monkeypatch.delenv('DP_TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.delenv('DP_TELEGRAM_CHANNEL_ID', raising=False)
    monkeypatch.delenv('DP_TELEGRAM_ADMIN_IDS', raising=False)
    monkeypatch.setattr(doctor, 'check_db_connection', lambda: True)
    get_settings.cache_clear()
    try:
        report = doctor.build_doctor_report(check_web_port=False)
    finally:
        get_settings.cache_clear()
    assert report.ok is True
    telegram = next(check for check in report.checks if check.name == 'telegram_config')
    assert telegram.ok is False
    assert telegram.required is False


def test_doctor_fails_on_missing_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'doctor.db'}")
    monkeypatch.setenv('DP_SOURCES_CONFIG_PATH', str(tmp_path / 'missing.yaml'))
    monkeypatch.setattr(doctor, 'check_db_connection', lambda: True)
    get_settings.cache_clear()
    try:
        report = doctor.build_doctor_report(check_web_port=False)
    finally:
        get_settings.cache_clear()
    assert report.ok is False
    source_check = next(check for check in report.checks if check.name == 'sources_config')
    assert source_check.ok is False


def test_doctor_fails_on_unknown_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = tmp_path / 'sources.yaml'
    sources.write_text(
        'sources:\n  - key: demo\n    name: Demo\n    adapter: missing_adapter\n    base_url: https://example.test\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'doctor.db'}")
    monkeypatch.setenv('DP_SOURCES_CONFIG_PATH', str(sources))
    monkeypatch.setattr(doctor, 'check_db_connection', lambda: True)
    get_settings.cache_clear()
    try:
        report = doctor.build_doctor_report(check_web_port=False)
    finally:
        get_settings.cache_clear()
    assert report.ok is False
    source_check = next(check for check in report.checks if check.name == 'sources_config')
    assert 'adapter registry' in source_check.detail


def test_doctor_report_json_is_serializable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, '_check_database', lambda: doctor.DoctorCheck('database', True, 'ok'))
    monkeypatch.setattr(doctor, '_check_writable_directory', lambda _path: doctor.DoctorCheck('data_directory', True, 'ok'))
    monkeypatch.setattr(doctor, '_check_sources', lambda: doctor.DoctorCheck('sources_config', True, 'ok'))
    monkeypatch.setattr(doctor, '_check_telegram', lambda: doctor.DoctorCheck('telegram_config', True, 'ok', required=False))
    report = doctor.build_doctor_report(check_web_port=False)
    text = report.to_json()
    assert '"ok": true' in text
    assert '"database"' in text
