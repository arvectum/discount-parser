from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.modules.offers.models import Offer
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.web import application, ux_routes
from src.web.application import app


@pytest.fixture
def ux_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'ux.db'}")
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(tmp_path))
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    monkeypatch.setattr(ux_routes, 'is_setup_complete', lambda: True)
    monkeypatch.setattr(application, 'is_setup_complete', lambda: True)
    with create_session() as session:
        session.add_all([
            Offer(title='Review me', status='needs_review'),
            Offer(title='Ready', status='ready', discount_percent=20),
            Offer(title='Published', status='published'),
        ])
        session.commit()
    try:
        yield
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_root_redirects_to_simplified_home(ux_db) -> None:
    client = TestClient(app)
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/home'


def test_home_exposes_three_step_workflow_not_technical_dashboard(ux_db) -> None:
    client = TestClient(app)
    response = client.get('/home')
    assert response.status_code == 200
    assert 'ШАГ 01' in response.text
    assert 'ШАГ 02' in response.text
    assert 'ШАГ 03' in response.text
    assert 'Собрать предложения' in response.text
    assert 'Открыть проверку' in response.text
    assert 'Посмотреть готовые' in response.text
    assert 'Расширенные функции' in response.text
    assert 'Главная' in response.text
    assert 'Настройки' in response.text
    assert 'Помощь' in response.text


def test_settings_groups_advanced_features(ux_db) -> None:
    client = TestClient(app)
    response = client.get('/settings')
    assert response.status_code == 200
    assert 'Telegram и интеграции' in response.text
    assert 'Источники' in response.text
    assert 'Сеть и VPN' in response.text
    assert 'Система и автоматизация' in response.text
    assert 'Расширенная панель' in response.text


def test_help_and_compact_footer_use_requested_arvectum_copy(ux_db) -> None:
    client = TestClient(app)
    response = client.get('/help')
    assert response.status_code == 200
    assert 'Первая установка на Mac' in response.text
    assert 'Собрать → Проверить → Опубликовать' not in response.text  # embedded help uses headings instead
    assert 'ИИ-Автоматизация' in response.text
    assert 'ИНН 7716261422' in response.text
    assert 'ОГРН 1267700213725' in response.text
    assert 'Ярославское ш.' not in response.text
    assert 'IT-компания: цифровые продукты' not in response.text
