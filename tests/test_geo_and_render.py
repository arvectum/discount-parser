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


def test_unified_telegram_caption_uses_structured_fields_only() -> None:
    offer = Offer(
        title="Кофемашина со скидкой",
        description="Друзья! Огромный рекламный текст источника, который никогда не должен попадать в пост. " * 20,
        merchant="Магазин",
        city="Москва",
        region="Московская область",
        category="Бытовая техника",
        subcategory="Кофемашины",
        conditions="При заказе на сайте, скидка не более 5 000 ₽",
        old_price=Decimal("39990"),
        new_price=Decimal("29990"),
        discount_percent=Decimal("25"),
        promo_code="COFFEE25",
    )
    caption = render_offer_caption(offer)
    assert caption.startswith("<b>🔥 Кофемашина со скидкой</b>")
    assert "🏪 Поставщик: Магазин" in caption
    assert "💰 Цена:" in caption
    assert "💸 Скидка: <b>25%</b>" in caption
    assert "📂 Категория: Бытовая техника → Кофемашины" in caption
    assert "📌 Условия: При заказе на сайте" in caption
    assert "📍 ГЕО: Москва, Московская область" in caption
    assert "🎁 Промокод: <code>COFFEE25</code>" in caption
    assert "Друзья!" not in caption
    assert "рекламный текст" not in caption


def test_long_source_description_never_expands_publication() -> None:
    offer = Offer(
        title="Товар",
        description=("Очень длинное объявление со всеми деталями, ссылками и рекламой. " * 500),
        merchant="Поставщик",
        discount_percent=Decimal("15"),
        category="Дом и быт",
        conditions="При заказе от 3 000 ₽; не суммируется с другими акциями",
        geo_scope="all_russia",
    )
    caption = render_offer_caption(offer)
    assert len(caption) < 650
    assert "Очень длинное объявление" not in caption
    assert "Поставщик:" in caption
    assert "Скидка:" in caption
    assert "Категория:" in caption
    assert "Условия:" in caption
    assert "ГЕО: Вся Россия" in caption


def test_same_structured_offer_has_same_shape_despite_source_verbosity() -> None:
    short = Offer(
        title="Акция",
        description="Скидка 20%.",
        merchant="Ритейлер",
        discount_percent=Decimal("20"),
        category="Продукты",
        conditions="От 1 500 ₽",
        geo_scope="all_russia",
    )
    verbose = Offer(
        title="Акция",
        description="Рекламный текст " * 300,
        merchant="Ритейлер",
        discount_percent=Decimal("20"),
        category="Продукты",
        conditions="От 1 500 ₽",
        geo_scope="all_russia",
    )
    assert render_offer_caption(short) == render_offer_caption(verbose)
