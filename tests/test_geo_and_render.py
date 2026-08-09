from __future__ import annotations

from decimal import Decimal

from src.core.geo import extract_geo
from src.modules.offers.models import Offer, PublishFilter
from src.modules.publishing.service import PublishCriteria
from src.sources.base import RawOffer
from src.sources.runner import _raw_matches_geo
from src.telegram.render import render_offer_caption


def test_extract_geo_recognizes_city_and_region() -> None:
    result = extract_geo(
        "Скидка 30% в Санкт-Петербурге",
        "Предложение действует в Санкт-Петербурге и Ленинградской области.",
    )
    assert result.city == "Санкт-Петербург"
    assert result.region == "Ленинградская область"


def test_extract_geo_prefers_structured_source_values() -> None:
    result = extract_geo(
        "Скидка в Москве",
        city="Тула",
        region="Тульская область",
    )
    assert result.city == "Тула"
    assert result.region == "Тульская область"


def test_extract_geo_does_not_invent_location() -> None:
    result = extract_geo("Скидка 25% на бытовую технику", "Доставка по России")
    assert result.city is None
    assert result.region is None


def test_manual_parse_geo_scope_matches_only_requested_location() -> None:
    moscow = RawOffer(
        source_key="test",
        external_id="1",
        title="Скидка в Москве",
        source_url="https://example.test/1",
    )
    federal = RawOffer(
        source_key="test",
        external_id="2",
        title="Скидка по всей России",
        source_url="https://example.test/2",
    )
    assert _raw_matches_geo(moscow, city="Москва") is True
    assert _raw_matches_geo(moscow, city="Казань") is False
    assert _raw_matches_geo(federal, city="Москва") is False
    assert _raw_matches_geo(federal) is True


def test_publish_criteria_carries_geo_filter() -> None:
    row = PublishFilter(
        name="geo-test",
        city="Казань",
        region="Республика Татарстан",
        min_discount_percent=Decimal("15"),
        max_posts_per_cycle=7,
    )
    criteria = PublishCriteria.from_filter(row)
    assert criteria.city == "Казань"
    assert criteria.region == "Республика Татарстан"
    assert criteria.limit == 7


def test_richer_telegram_caption_contains_context_and_geo() -> None:
    offer = Offer(
        title="Кофемашина со скидкой",
        description="Автоматическая кофемашина для дома. Скидка доступна при оформлении заказа на сайте магазина.",
        merchant="Магазин",
        city="Москва",
        region="Московская область",
        category="Бытовая техника",
        old_price=Decimal("39990"),
        new_price=Decimal("29990"),
        discount_percent=Decimal("25"),
        promo_code="COFFEE25",
    )
    caption = render_offer_caption(offer)
    assert "📝 Автоматическая кофемашина" in caption
    assert "Цена:" in caption
    assert "Скидка: <b>25%</b>" in caption
    assert "📍 Москва, Московская область" in caption
    assert "Магазин:" in caption
    assert "COFFEE25" in caption


def test_caption_summary_is_bounded() -> None:
    offer = Offer(title="Товар", description="слово " * 200)
    caption = render_offer_caption(offer)
    assert len(caption) < 700
    assert "…" in caption
