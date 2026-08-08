from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.modules.offers.models import Offer, ParseRun, Publication, Source
from src.qa.report import build_smoke_report, write_smoke_report
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "qa.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_smoke_report_contains_delivery_evidence(sqlite_db: Path, tmp_path: Path) -> None:
    with create_session() as session:
        source = Source(key="source-a", name="Source A")
        offer = Offer(title="Published offer", status="published")
        session.add_all([source, offer])
        session.flush()
        session.add(ParseRun(source_id=source.id, status="success", fetched_count=3, new_count=1))
        session.add(
            Publication(
                offer_id=offer.id,
                channel_id="@channel",
                status="published",
                telegram_message_id="777",
            )
        )
        session.commit()

    report = build_smoke_report()
    assert report["sources"] == 1
    assert report["offers_total"] == 1
    assert report["offers_published"] == 1
    assert report["publications_published"] == 1
    assert report["parse_runs"] == 1
    assert report["latest_telegram_message_id"] == "777"

    output = write_smoke_report(tmp_path / "smoke.json")
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["offers_total"] == 1
    assert stored["latest_telegram_message_id"] == "777"
