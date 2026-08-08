from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.config import SourceConfig
from src.sources.runner import run_source


class FixtureAdapter(PromokoodAdapter):
    def __init__(self, html: str) -> None:
        super().__init__("https://promokood.ru/")
        self.html = html

    def collect(self):
        return self.parse(self.html)


@pytest.fixture
def fixture_html() -> str:
    return Path("tests/fixtures/promokood.html").read_text(encoding="utf-8")


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "sources.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_promokood_fixture_parses_discount_values(fixture_html: str) -> None:
    offers = FixtureAdapter(fixture_html).collect()
    assert len(offers) == 3
    by_merchant = {offer.merchant: offer for offer in offers}
    assert by_merchant["ВкусВилл"].discount_amount == Decimal("200")
    assert by_merchant["Яндекс Афиша"].discount_amount == Decimal("300")
    assert by_merchant["Горздрав"].discount_percent == Decimal("10")
    assert by_merchant["ВкусВилл"].image_url == "https://promokood.ru/img/vkusvill.jpg"


def test_runner_second_run_updates_observations_without_duplicate_offers(
    fixture_html: str, sqlite_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = SourceConfig(
        key="promokood",
        name="PROMOKO/OD",
        adapter="promokood",
        base_url="https://promokood.ru/",
    )
    adapter = FixtureAdapter(fixture_html)
    monkeypatch.setattr("src.sources.runner.build_adapter", lambda _config: adapter)

    first = run_source(config)
    second = run_source(config)

    assert (first.fetched, first.created, first.updated, first.errors) == (3, 3, 0, 0)
    assert (second.fetched, second.created, second.updated, second.errors) == (3, 0, 3, 0)

    with create_session() as session:
        assert session.scalar(select(func.count()).select_from(Offer)) == 3
        assert session.scalar(select(func.count()).select_from(OfferSourceObservation)) == 3
        assert session.scalar(select(func.count()).select_from(ParseRun)) == 2
