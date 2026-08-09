from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.modules.offers.models import Offer
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.web import review_routes
from src.web.application import app


@pytest.fixture
def review_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DP_DATABASE_URL', f"sqlite:///{tmp_path / 'review.db'}")
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(tmp_path))
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    monkeypatch.setattr(review_routes, 'is_setup_complete', lambda: True)
    try:
        yield
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_review_page_approves_offer_and_persists_manual_overrides(review_db) -> None:
    with create_session() as session:
        offer = Offer(
            title='Скидка на кофе',
            description='Скидка 20% по промокоду, действует в Москве',
            status='needs_review',
            category='Другое',
            subcategory='Не определено',
            city='Москва',
            geo_scope='city',
            discount_percent=20,
        )
        session.add(offer)
        session.commit()
        offer_id = offer.id

    client = TestClient(app)
    page = client.get('/review')
    assert page.status_code == 200
    assert 'Проверка предложений' in page.text
    assert 'Одобрить → ready' in page.text
    assert 'ООО «Арвектум»' in page.text
    assert 'ИНН 7716261422' in page.text
    assert '<svg' in page.text

    response = client.post(
        f'/review/{offer_id}',
        data={
            'action': 'approve',
            'display_title': 'Кофе со скидкой 20%',
            'category': 'Продукты',
            'subcategory': 'Кофе',
            'geo_scope': 'city',
            'region': '',
            'city': 'Москва',
            'conditions': 'По промокоду, пока действует акция',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with create_session() as session:
        saved = session.get(Offer, offer_id)
        assert saved is not None
        assert saved.status == 'ready'
        assert saved.display_title == 'Кофе со скидкой 20%'
        assert saved.category == 'Продукты'
        assert saved.subcategory == 'Кофе'
        assert saved.conditions == 'По промокоду, пока действует акция'
        protected = {row.field_name for row in saved.overrides}
        assert {'status', 'display_title', 'category', 'subcategory', 'geo_scope', 'region', 'city', 'conditions'} <= protected


def test_review_page_can_reject_offer(review_db) -> None:
    with create_session() as session:
        offer = Offer(title='Сомнительное предложение', status='needs_review', category='Другое')
        session.add(offer)
        session.commit()
        offer_id = offer.id

    client = TestClient(app)
    response = client.post(
        f'/review/{offer_id}',
        data={
            'action': 'reject',
            'display_title': 'Сомнительное предложение',
            'category': 'Другое',
            'subcategory': '',
            'geo_scope': 'unknown',
            'region': '',
            'city': '',
            'conditions': '',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    with create_session() as session:
        saved = session.get(Offer, offer_id)
        assert saved is not None
        assert saved.status == 'rejected'
        assert any(row.field_name == 'status' and row.value == 'rejected' for row in saved.overrides)
