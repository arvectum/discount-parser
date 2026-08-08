from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.sources.adapters.berikod import BerikodAdapter
from src.sources.adapters.promko import PromkoAdapter
from src.sources.adapters.promokodik import PromokodikAdapter
from src.sources.adapters.promokodi_net_ru import PromokodiNetRuAdapter


@pytest.mark.parametrize(
    ("fixture", "adapter", "expected_count"),
    [
        ("promokodik.html", PromokodikAdapter("https://promokodik.ru/"), 2),
        ("berikod.html", BerikodAdapter("https://berikod.ru/global/ru/"), 2),
        ("promokodi_net_ru.html", PromokodiNetRuAdapter("https://promokodi.net.ru/ru/"), 2),
        ("promko.html", PromkoAdapter("https://promko.net/ru"), 3),
    ],
)
def test_source_fixture_counts(fixture: str, adapter, expected_count: int) -> None:
    html = Path("tests/fixtures", fixture).read_text(encoding="utf-8")
    assert len(adapter.parse(html)) == expected_count


def test_promokodik_parses_date_cashback_and_merchant() -> None:
    html = Path("tests/fixtures/promokodik.html").read_text(encoding="utf-8")
    offers = PromokodikAdapter("https://promokodik.ru/").parse(html)
    assert offers[0].merchant == "Детский мир"
    assert offers[0].discount_percent == Decimal("20")
    assert offers[0].valid_until == datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert offers[1].cashback_percent == Decimal("12")
    assert offers[1].discount_percent is None


def test_berikod_extracts_codes_and_benefits() -> None:
    html = Path("tests/fixtures/berikod.html").read_text(encoding="utf-8")
    offers = BerikodAdapter("https://berikod.ru/global/ru/").parse(html)
    assert offers[0].promo_code == "MTS55"
    assert offers[0].discount_amount == Decimal("5000")
    assert offers[1].promo_code == "ERNOW"
    assert offers[1].discount_percent == Decimal("20")


def test_promokodi_net_ru_extracts_merchant() -> None:
    html = Path("tests/fixtures/promokodi_net_ru.html").read_text(encoding="utf-8")
    offers = PromokodiNetRuAdapter("https://promokodi.net.ru/ru/").parse(html)
    assert offers[0].merchant == "Мвидео"
    assert offers[0].discount_percent == Decimal("25")
    assert offers[1].merchant == "Детский мир"


def test_promko_extracts_live_summary_cards() -> None:
    html = Path("tests/fixtures/promko.html").read_text(encoding="utf-8")
    offers = PromkoAdapter("https://promko.net/ru").parse(html)
    assert [(item.merchant, item.discount_percent) for item in offers] == [
        ("Яндекс Плюс", Decimal("100")),
        ("Askona", Decimal("99")),
        ("Aravia", Decimal("70")),
    ]
