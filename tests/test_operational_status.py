from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.jobs.status import SourceRunStatus
from src.qa.doctor import DoctorCheck, DoctorReport
from src.qa.operational_status import build_operational_status, classify_operational_state
from src.shared.config import get_settings


def _source(*, status: str = 'success', success_age_hours: int = 1, error: str | None = None) -> SourceRunStatus:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    return SourceRunStatus(
        source_key='example',
        source_name='Example',
        enabled=True,
        last_status=status,
        last_started_at=now - timedelta(minutes=5),
        last_finished_at=now - timedelta(minutes=4),
        last_success_at=now - timedelta(hours=success_age_hours),
        last_error=error,
        fetched_count=10,
        new_count=2,
        updated_count=1,
    )


def test_classification_ok_warning_error() -> None:
    doctor_ok = {'required_failures': [], 'optional_failures': []}
    assert classify_operational_state(doctor=doctor_ok, setup_complete=True, sources=[])[0] == 'ok'
    assert classify_operational_state(doctor=doctor_ok, setup_complete=False, sources=[])[0] == 'warning'
    assert classify_operational_state(
        doctor={'required_failures': ['database'], 'optional_failures': []},
        setup_complete=True,
        sources=[],
    )[0] == 'error'


def test_snapshot_marks_stale_source_and_redacts_error(monkeypatch) -> None:
    monkeypatch.setenv('DP_TELEGRAM_BOT_TOKEN', '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
    monkeypatch.setenv('DP_TELEGRAM_CHANNEL_ID', '-100111222333')
    monkeypatch.setenv('DP_TELEGRAM_ADMIN_IDS', '123456789')
    get_settings.cache_clear()

    doctor = DoctorReport(ok=True, checks=(DoctorCheck('database', True, 'ok'),))
    snapshot = build_operational_status(
        now=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        doctor_report=doctor,
        source_statuses=[_source(status='failed', success_age_hours=12, error='password=hunter2 token=abc123')],
        smoke_report={'offers_total': 5, 'latest_telegram_message_id': 999999},
        process_states={
            'bot': SimpleNamespace(running=True, pid=101),
            'scheduler': SimpleNamespace(running=False, pid=None),
        },
    )

    assert snapshot['state'] == 'warning'
    assert 'source_stale' in snapshot['reasons']
    assert 'source_run_failed' in snapshot['reasons']
    assert snapshot['sources'][0]['stale'] is True
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert 'hunter2' not in serialized
    assert 'abc123' not in serialized
    assert '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi' not in serialized
    assert '-100111222333' not in serialized
    assert 'latest_telegram_message_id' not in snapshot['aggregates']
    assert snapshot['processes']['bot'] == {'observed': True, 'running': True, 'pid': 101}

    get_settings.cache_clear()


def test_worker_cli_status_json_prints_valid_json(monkeypatch, capsys) -> None:
    from src import worker_entry

    payload = {'schema_version': 1, 'state': 'ok', 'reasons': []}
    monkeypatch.setattr(worker_entry, '_prepare_runtime_directory', lambda: None)
    monkeypatch.setattr(worker_entry, 'build_operational_status', lambda: payload)
    monkeypatch.setattr(worker_entry.sys, 'argv', ['DiscountParserWorker.exe', 'status-json'])

    assert worker_entry.main() == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_system_status_endpoint_is_secret_free(monkeypatch) -> None:
    from src.web import system_routes

    payload = {'schema_version': 1, 'state': 'ok', 'setup_complete': True, 'sources': []}
    monkeypatch.setattr(system_routes, 'is_setup_complete', lambda: True)
    monkeypatch.setattr(system_routes, 'build_operational_status', lambda **kwargs: payload)
    monkeypatch.setattr(system_routes.process_manager, 'states', lambda: {})

    response = system_routes.system_status_json()
    assert response.status_code == 200
    assert json.loads(response.body) == payload


def test_system_status_endpoint_refuses_incomplete_setup(monkeypatch) -> None:
    from src.web import system_routes

    monkeypatch.setattr(system_routes, 'is_setup_complete', lambda: False)
    response = system_routes.system_status_json()
    assert response.status_code == 409
    body = json.loads(response.body)
    assert body['state'] == 'warning'
    assert body['reasons'] == ['setup_incomplete']
