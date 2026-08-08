from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.core.classification import classify_offer
from src.core.dedup import find_existing_offer
from src.core.normalization import canonicalize_url, normalize_raw_offer
from src.modules.offers.models import ClassificationRule, Offer
from src.modules.offers.repository import OfferRepository
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.sources.base import RawOffer


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "core.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_canonicalize_url_removes_tracking_and_fragment() -> None:
    assert canonicalize_url(
        "HTTPS://Example.COM/deal/?utm_source=tg&id=42&yclid=abc#promo"
    ) == "https://example.com/deal?id=42"


def test_normalization_computes_discount_percent_from_prices() -> None:
    raw = RawOffer(
        source_key="x",
        external_id="1",
        title="Товар",
        source_url="https://example.com/deal",
        old_price=Decimal("1000"),
        new_price=Decimal("750"),
    )
    normalized = normalize_raw_offer(raw)
    assert normalized.discount_percent == Decimal("25.00")
    assert normalized.offer_type == "discount"


def test_keyword_and_rule_classification(sqlite_db: Path) -> None:
    with create_session() as session:
        keyword = classify_offer(session, title="Скидка на подгузники Pampers", merchant="Магазин")
        assert keyword.category == "Детские товары"

        session.add(
            ClassificationRule(
                match_key="merchant",
                match_value="Особый магазин",
                category="Продукты",
                subcategory="Супермаркет",
                priority=500,
            )
        )
        session.commit()
        ruled = classify_offer(session, title="Любое предложение", merchant="Особый магазин")
        assert ruled.category == "Продукты"
        assert ruled.subcategory == "Супермаркет"
        assert ruled.reason.startswith("rule:")


def test_manual_category_override_has_priority(sqlite_db: Path) -> None:
    with create_session() as session:
        repo = OfferRepository(session)
        offer = repo.create(title="Pampers", merchant="Shop", category="Другое")
        repo.set_manual_override(offer, "category", "Моя категория")
        session.commit()
        result = classify_offer(session, title="Pampers подгузники", merchant="Shop", offer=offer)
        assert result.category == "Моя категория"
        assert result.reason == "manual_override"


def test_fuzzy_same_offer_matches_but_different_benefit_does_not(sqlite_db: Path) -> None:
    with create_session() as session:
        existing_raw = RawOffer(
            source_key="a",
            external_id="a1",
            title="Скидка 20% на повторный заказ",
            source_url="https://one.example/promo-a",
            merchant="Shop",
            discount_percent=Decimal("20"),
        )
        existing_norm = normalize_raw_offer(existing_raw)
        offer = Offer(
            title=existing_norm.title,
            merchant=existing_norm.merchant,
            discount_percent=existing_norm.discount_percent,
            canonical_url=existing_norm.canonical_url,
            fingerprint=existing_norm.fingerprint,
        )
        session.add(offer)
        session.commit()

        same = normalize_raw_offer(
            RawOffer(
                source_key="b",
                external_id="b1",
                title="Повторный заказ — скидка 20%",
                source_url="https://two.example/other-link",
                merchant="Shop",
                discount_percent=Decimal("20"),
            )
        )
        assert find_existing_offer(session, same).offer is not None

        different = normalize_raw_offer(
            RawOffer(
                source_key="b",
                external_id="b2",
                title="Скидка 50% на смартфоны",
                source_url="https://two.example/phone-sale",
                merchant="Shop",
                discount_percent=Decimal("50"),
            )
        )
        assert find_existing_offer(session, different).offer is None
