from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from src.modules.offers.models import Offer
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.sources.base import RawOffer
from src.sources.config import SourceConfig
from src.sources.runner import run_source


class MutableAdapter:
    def __init__(self, offer: RawOffer) -> None:
        self.offer = offer

    def collect(self) -> list[RawOffer]:
        return [self.offer]


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "updates.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_same_external_id_refreshes_discount_fields(sqlite_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = SourceConfig("stable", "Stable Source", "static", "https://source.example/")
    adapter = MutableAdapter(
        RawOffer(
            source_key="stable",
            external_id="deal-1",
            title="Pampers скидка",
            source_url="https://source.example/deal-1",
            merchant="Shop",
            discount_percent=Decimal("20"),
        )
    )
    monkeypatch.setattr("src.sources.runner.build_adapter", lambda _config: adapter)

    first = run_source(config)
    assert first.created == 1

    adapter.offer = RawOffer(
        source_key="stable",
        external_id="deal-1",
        title="Pampers скидка",
        source_url="https://source.example/deal-1",
        merchant="Shop",
        discount_percent=Decimal("30"),
    )
    second = run_source(config)
    assert second.created == 0
    assert second.updated == 1

    with create_session() as session:
        offers = session.scalars(select(Offer)).all()
        assert len(offers) == 1
        assert offers[0].discount_percent == Decimal("30.00")
