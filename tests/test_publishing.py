from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from src.modules.offers.models import Offer, Publication
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.telegram.publisher import publish_offer
from src.telegram.render import render_offer_caption


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.photos: list[dict] = []
        self.next_message_id = 100

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        self.next_message_id += 1
        return SimpleNamespace(message_id=self.next_message_id)

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        self.next_message_id += 1
        return SimpleNamespace(message_id=self.next_message_id)


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "publishing.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_publish_candidates_apply_discount_and_publication_ledger(sqlite_db: Path) -> None:
    with create_session() as session:
        low = Offer(title="10 percent", status="ready", discount_percent=Decimal("10"))
        good = Offer(title="30 percent", status="ready", discount_percent=Decimal("30"))
        used = Offer(title="50 percent", status="ready", discount_percent=Decimal("50"))
        session.add_all([low, good, used])
        session.flush()
        session.add(Publication(offer_id=used.id, channel_id="@channel", status="published"))
        session.commit()

    with create_session() as session:
        result = list_publish_candidates(
            session,
            channel_id="@channel",
            criteria=PublishCriteria(min_discount_percent=Decimal("20"), limit=10),
        )
        assert [offer.title for offer in result] == ["30 percent"]


def test_renderer_escapes_user_content(sqlite_db: Path) -> None:
    offer = Offer(
        title="<b>Unsafe</b>",
        status="ready",
        merchant="A & B",
        discount_percent=Decimal("25"),
        promo_code="A<B",
    )
    caption = render_offer_caption(offer)
    assert "&lt;b&gt;Unsafe&lt;/b&gt;" in caption
    assert "A &amp; B" in caption
    assert "A&lt;B" in caption


def test_publisher_sends_once_and_records_message(sqlite_db: Path) -> None:
    with create_session() as session:
        offer = Offer(
            title="Скидка 25%",
            status="ready",
            merchant="Shop",
            discount_percent=Decimal("25"),
            canonical_url="https://example.test/deal",
        )
        session.add(offer)
        session.commit()
        offer_id = offer.id

    bot = FakeBot()
    first = asyncio.run(publish_offer(bot, offer_id=offer_id, channel_id="@channel"))
    second = asyncio.run(publish_offer(bot, offer_id=offer_id, channel_id="@channel"))

    assert first.status == "published"
    assert first.telegram_message_id == "101"
    assert second.status == "duplicate"
    assert len(bot.messages) == 1
    assert len(bot.photos) == 0

    with create_session() as session:
        assert session.scalar(select(func.count()).select_from(Publication)) == 1
        publication = session.scalar(select(Publication))
        offer = session.get(Offer, offer_id)
        assert publication.status == "published"
        assert publication.telegram_message_id == "101"
        assert offer.status == "published"
