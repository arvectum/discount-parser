from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.modules.offers.models import Offer
from src.telegram.publication_format import (
    DEFAULT_ORDER,
    load_publication_format,
    publication_format_path,
    save_publication_format,
)
from src.telegram.render import render_offer_caption
from src.web import telegram_format_routes
from src.web.application import app


@pytest.fixture
def format_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DP_RUNTIME_ROOT', str(tmp_path))
    monkeypatch.setattr(telegram_format_routes, 'is_setup_complete', lambda: True)
    yield tmp_path


def _offer() -> Offer:
    return Offer(
        title='Скидка на продукты',
        merchant='Лента',
        old_price=Decimal('4000'),
        new_price=Decimal('3000'),
        discount_percent=Decimal('25'),
        cashback_percent=Decimal('10'),
        delivery_price=Decimal('0'),
        category='Продукты',
        conditions='Заказ от 3 000 ₽',
        geo_scope='all_russia',
        promo_code='SUMMER25',
    )


def test_default_format_preserves_r11_fields(format_runtime: Path) -> None:
    current = load_publication_format()
    assert current.order == DEFAULT_ORDER
    caption = render_offer_caption(_offer(), current)
    assert '🏪 Поставщик: Лента' in caption
    assert '💸 Скидка: <b>25%</b>' in caption
    assert '📂 Категория: Продукты' in caption
    assert '📌 Условия: Заказ от 3 000 ₽' in caption
    assert '📍 ГЕО: Вся Россия' in caption


def test_saved_format_controls_visible_fields_and_order(format_runtime: Path) -> None:
    saved = save_publication_format(
        order=['discount', 'merchant', 'conditions', 'category'],
        enabled=['merchant', 'discount', 'category', 'conditions'],
    )
    caption = render_offer_caption(_offer(), saved)
    assert 'Цена:' not in caption
    assert 'Кэшбэк:' not in caption
    assert 'ГЕО:' not in caption
    assert 'Промокод:' not in caption
    discount_at = caption.index('💸 Скидка:')
    merchant_at = caption.index('🏪 Поставщик:')
    conditions_at = caption.index('📌 Условия:')
    category_at = caption.index('📂 Категория:')
    assert discount_at < merchant_at < conditions_at < category_at


def test_format_file_is_persisted_in_runtime_root(format_runtime: Path) -> None:
    save_publication_format(order=['merchant', 'discount'], enabled=['merchant'])
    assert publication_format_path() == format_runtime / 'telegram_publication_format.json'
    assert publication_format_path().exists()
    loaded = load_publication_format()
    assert loaded.order[:2] == ('merchant', 'discount')
    assert loaded.enabled == frozenset({'merchant'})


def test_unknown_and_duplicate_fields_are_safely_normalized(format_runtime: Path) -> None:
    saved = save_publication_format(
        order=['discount', 'unknown', 'discount', 'merchant'],
        enabled=['unknown', 'merchant'],
    )
    assert saved.order[:2] == ('discount', 'merchant')
    assert len(saved.order) == len(DEFAULT_ORDER)
    assert saved.enabled == frozenset({'merchant'})


def test_format_editor_page_and_post(format_runtime: Path) -> None:
    client = TestClient(app)
    page = client.get('/settings/telegram-format')
    assert page.status_code == 200
    assert 'Формат публикации Telegram' in page.text
    assert 'Поставщик' in page.text
    assert 'Скидка' in page.text
    assert 'Предпросмотр' in page.text
    assert 'Вернуть стандартный' in page.text
    assert 'const samples = {' in page.text

    response = client.post(
        '/settings/telegram-format',
        data=[
            ('field_order', 'merchant,discount,category,conditions,geo'),
            ('enabled', 'merchant'),
            ('enabled', 'discount'),
            ('enabled', 'conditions'),
        ],
        follow_redirects=False,
    )
    assert response.status_code == 303
    loaded = load_publication_format()
    assert loaded.order[:5] == ('merchant', 'discount', 'category', 'conditions', 'geo')
    assert loaded.enabled == frozenset({'merchant', 'discount', 'conditions'})


def test_renderer_uses_persisted_customer_format(format_runtime: Path) -> None:
    save_publication_format(
        order=['merchant', 'discount', 'category', 'conditions'],
        enabled=['merchant', 'discount'],
    )
    caption = render_offer_caption(_offer())
    assert 'Поставщик:' in caption
    assert 'Скидка:' in caption
    assert 'Категория:' not in caption
    assert 'Условия:' not in caption
    assert 'ГЕО:' not in caption
