from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.modules.offers.models import Offer
from src.modules.offers.repository import OfferRepository
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_offer_crud_and_manual_override_survives_automatic_update(sqlite_db: Path) -> None:
    with create_session() as session:
        repo = OfferRepository(session)
        offer = repo.create(title="Pampers -20%", merchant="Shop", category="Другое")
        repo.set_manual_override(offer, "category", "Детские товары", source="test")
        session.commit()
        offer_id = offer.id

    with create_session() as session:
        repo = OfferRepository(session)
        offer = repo.get(offer_id)
        assert offer is not None
        assert offer.category == "Детские товары"
        repo.update(offer, {"category": "Электроника", "merchant": "New Shop"})
        session.commit()
        assert offer.category == "Детские товары"
        assert offer.merchant == "New Shop"


def test_publication_is_unique_per_offer_and_channel(sqlite_db: Path) -> None:
    with create_session() as session:
        repo = OfferRepository(session)
        offer = repo.create(title="Offer")
        repo.create_publication(offer, "@discounts")
        session.commit()

    with create_session() as session:
        repo = OfferRepository(session)
        offer = session.query(Offer).one()
        repo.create_publication(offer, "@discounts")
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_sqlite_runtime_pragmas(sqlite_db: Path) -> None:
    with get_engine().connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert str(journal_mode).lower() == "wal"
    assert busy_timeout >= 30000
    assert foreign_keys == 1


def test_initial_alembic_migration_creates_expected_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    assert {
        "sources",
        "offers",
        "offer_source_observations",
        "parse_runs",
        "classification_rules",
        "manual_overrides",
        "publications",
        "publish_filters",
        "alembic_version",
    } <= tables

    reset_db_runtime()
    get_settings.cache_clear()
