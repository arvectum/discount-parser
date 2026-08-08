from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.qa.doctor import DoctorCheck, DoctorReport
from src.web.application import app
from src.web import launcher, processes, system_routes


def test_system_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert '/system' in paths
    assert '/shutdown' in paths
    assert '/system/logs/{name}/clear' in paths


def test_system_page_shows_process_logs_and_doctor(monkeypatch) -> None:
    monkeypatch.setattr(system_routes, 'is_setup_complete', lambda: True)
    monkeypatch.setattr(system_routes, 'read_process_log', lambda name: f'{name} sample log')
    monkeypatch.setattr(
        system_routes,
        'build_doctor_report',
        lambda **_kwargs: DoctorReport(
            ok=True,
            checks=(
                DoctorCheck('database', True, 'подключение к БД успешно'),
                DoctorCheck('telegram_config', False, 'не заполнено: bot token', required=False),
            ),
        ),
    )

    client = TestClient(app)
    response = client.get('/system')

    assert response.status_code == 200
    assert 'bot sample log' in response.text
    assert 'scheduler sample log' in response.text
    assert 'ГОТОВО К ЛОКАЛЬНОМУ ТЕСТУ' in response.text
    assert 'telegram_config' in response.text
    assert 'ПРОВЕРИТЬ' in response.text
    assert 'Завершить Discount Parser' in response.text


def test_repeated_web_launch_only_opens_existing_panel(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(launcher, '_panel_is_running', lambda port: True)
    monkeypatch.setattr(launcher, '_open_browser', lambda url, delay=0: opened.append(url))
    monkeypatch.setattr(launcher, '_autostart_packaged_services', lambda: (_ for _ in ()).throw(AssertionError('must not autostart')))
    monkeypatch.setattr(launcher.uvicorn, 'run', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not start server')))

    launcher.run_web_panel()

    assert opened
    assert opened[0].startswith('http://127.0.0.1:')


def test_frozen_windows_services_use_worker_executable(tmp_path: Path, monkeypatch) -> None:
    worker = tmp_path / 'DiscountParserWorker.exe'
    worker.write_bytes(b'worker')
    monkeypatch.setattr(processes, 'ROOT', tmp_path)
    monkeypatch.setattr(processes.sys, 'platform', 'win32')
    monkeypatch.setattr(processes.sys, 'frozen', True, raising=False)

    assert processes.ProcessManager._command('bot') == [str(worker), 'bot']
    assert processes.ProcessManager._command('scheduler') == [str(worker), 'scheduler']
