from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.modules.offers.models import Offer, ParseRun, Source
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.web.application import app
from src.web import management_pages


@pytest.fixture
def web_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'web.db'}")
    monkeypatch.setattr(management_pages, 'is_setup_complete', lambda: True)
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_management_routes_are_registered() -> None:
    paths = {route.path for route in app.routes if hasattr(route, 'path')}
    assert '/offers' in paths
    assert '/offers/{offer_id}' in paths
    assert '/runs' in paths


def test_offers_page_lists_seeded_offer(web_db) -> None:
    with create_session() as session:
        session.add(
            Offer(
                title='Тестовая скидка 40%',
                display_title='Тестовая скидка',
                merchant='Тестовый магазин',
                status='ready',
                offer_type='discount',
                category='Тест',
                discount_percent=40,
            )
        )
        session.commit()

    client = TestClient(app)
    response = client.get('/offers?q=Тестовая')
    assert response.status_code == 200
    assert 'Тестовая скидка' in response.text
    assert 'Тестовый магазин' in response.text


def test_runs_page_shows_error_details(web_db) -> None:
    with create_session() as session:
        source = Source(key='demo', name='Demo source', base_url='https://example.test', enabled=True)
        session.add(source)
        session.flush()
        session.add(
            ParseRun(
                source_id=source.id,
                status='failed',
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                fetched_count=0,
                error_count=1,
                error='ConnectionError: demo failure',
            )
        )
        session.commit()

    client = TestClient(app)
    response = client.get('/runs')
    assert response.status_code == 200
    assert 'Demo source' in response.text
    assert 'ConnectionError: demo failure' in response.text
