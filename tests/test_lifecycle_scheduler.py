from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.jobs.lifecycle import expire_offers, mark_stale_for_review
from src.jobs.scheduler import build_scheduler
from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun, Source
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "lifecycle.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_expire_offers_marks_only_past_active_offers(sqlite_db: Path) -> None:
    now = datetime.now(UTC)
    with create_session() as session:
        session.add_all(
            [
                Offer(title="expired", status="ready", valid_until=now - timedelta(minutes=1)),
                Offer(title="future", status="ready", valid_until=now + timedelta(days=1)),
                Offer(title="published", status="published", valid_until=now - timedelta(days=1)),
            ]
        )
        session.commit()

    assert expire_offers(now=now) == 1

    with create_session() as session:
        statuses = {offer.title: offer.status for offer in session.scalars(select(Offer)).all()}
        assert statuses == {
            "expired": "expired",
            "future": "ready",
            "published": "published",
        }


def test_failed_fetch_does_not_mark_undated_offer_stale(sqlite_db: Path) -> None:
    now = datetime.now(UTC)
    observed_at = now - timedelta(days=10)
    with create_session() as session:
        source = Source(key="source-a", name="Source A")
        offer = Offer(title="undated", status="ready", first_seen_at=observed_at, last_seen_at=observed_at)
        session.add_all([source, offer])
        session.flush()
        session.add(
            OfferSourceObservation(
                offer_id=offer.id,
                source_id=source.id,
                external_id="a-1",
                source_url="https://example.test/a-1",
                observed_at=observed_at,
            )
        )
        session.add(
            ParseRun(
                source_id=source.id,
                status="failed",
                started_at=now - timedelta(days=1),
                finished_at=now - timedelta(days=1),
                error_count=1,
            )
        )
        session.commit()

    assert mark_stale_for_review(stale_after_days=7, now=now) == 0
    with create_session() as session:
        assert session.scalar(select(Offer)).status == "ready"


def test_successful_later_fetch_marks_missing_undated_offer_for_review(sqlite_db: Path) -> None:
    now = datetime.now(UTC)
    observed_at = now - timedelta(days=10)
    with create_session() as session:
        source = Source(key="source-b", name="Source B")
        offer = Offer(title="missing", status="ready", first_seen_at=observed_at, last_seen_at=observed_at)
        session.add_all([source, offer])
        session.flush()
        session.add(
            OfferSourceObservation(
                offer_id=offer.id,
                source_id=source.id,
                external_id="b-1",
                source_url="https://example.test/b-1",
                observed_at=observed_at,
            )
        )
        session.add(
            ParseRun(
                source_id=source.id,
                status="success",
                started_at=now - timedelta(days=1, minutes=1),
                finished_at=now - timedelta(days=1),
            )
        )
        session.commit()

    assert mark_stale_for_review(stale_after_days=7, now=now) == 1
    with create_session() as session:
        assert session.scalar(select(Offer)).status == "needs_review"


def test_accelerated_scheduler_executes_collection_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DP_TIMEZONE", "UTC")
    get_settings.cache_clear()
    calls: list[float] = []

    scheduler = build_scheduler(
        collect_callable=lambda: calls.append(time.monotonic()),
        maintenance_callable=lambda: None,
        autopost_callable=lambda: None,
        background=True,
        collect_interval_seconds=0.1,
    )
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"collect_sources", "maintenance", "autopost"}
    assert jobs["collect_sources"].max_instances == 1
    assert jobs["maintenance"].max_instances == 1
    assert jobs["autopost"].max_instances == 1

    scheduler.start()
    try:
        deadline = time.monotonic() + 2.0
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        scheduler.shutdown(wait=True)
        get_settings.cache_clear()

    assert len(calls) >= 2
