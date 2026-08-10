from decimal import Decimal

from src.core.conditions import extract_conditions
from src.core.geo import extract_geo
from src.modules.offers.models import Offer
from src.telegram.render import render_offer_caption


def test_all_russia_geo_scope_is_explicit() -> None:
    result = extract_geo("Скидка действует по всей России")
    assert result.scope == "all_russia"
    assert result.city is None
    assert result.region is None


def test_city_and_region_scopes_are_distinct() -> None:
    city = extract_geo("Акция действует в Москве")
    region = extract_geo("Акция действует в Московской области")
    assert city.scope == "city"
    assert city.city == "Москва"
    assert region.scope == "region"
    assert region.region == "Московская область"


def test_unknown_geo_is_not_treated_as_all_russia() -> None:
    result = extract_geo("Скидка на кофе 10%")
    assert result.scope == "unknown"


def test_conditions_extract_max_discount_and_min_order() -> None:
    result = extract_conditions("Скидка 7%, но не более 1 000 руб. при заказе от 3 000 ₽.")
    assert result.max_discount_amount == Decimal("1000")
    assert result.min_order_amount == Decimal("3000")
    assert result.conditions is not None
    assert "не более" in result.conditions.casefold()


def test_explicit_conditions_take_precedence_over_generated_text() -> None:
    result = extract_conditions(
        "При заказе от 5000 ₽ скидка 10%",
        explicit="Только для новых клиентов",
    )
    assert result.conditions == "Только для новых клиентов"
    assert result.min_order_amount == Decimal("5000")


def test_telegram_caption_shows_conditions_and_all_russia() -> None:
    offer = Offer(
        title="Скидка на заказ",
        status="ready",
        offer_type="discount",
        discount_percent=Decimal("7"),
        geo_scope="all_russia",
        conditions="Скидка 7%, но не более 1000 ₽ при заказе от 3000 ₽.",
        max_discount_amount=Decimal("1000"),
        min_order_amount=Decimal("3000"),
        currency="RUB",
    )
    caption = render_offer_caption(offer)
    assert "📍 ГЕО: Вся Россия" in caption
    assert "📌 Условия:" in caption
    assert "не более 1000 ₽" in caption
    assert "от 3000 ₽" in caption
    assert caption.count("скидка не более") == 0
