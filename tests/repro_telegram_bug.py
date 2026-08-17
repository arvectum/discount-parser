from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.modules.offers.models import Offer, Publication
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.telegram.publisher import publish_offer


class FakeBot:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.messages = []
        self.next_message_id = 100

    async def send_message(self, **kwargs):
        if self.should_fail:
            raise Exception("Telegram API Error")
        self.messages.append(kwargs)
        self.next_message_id += 1
        return SimpleNamespace(message_id=self.next_message_id)

    async def send_photo(self, **kwargs):
        if self.should_fail:
            raise Exception("Telegram API Error")
        self.messages.append(kwargs)
        self.next_message_id += 1
        return SimpleNamespace(message_id=self.next_message_id)

@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "repro.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()

def test_failed_publication_removes_from_queue_FIXED(sqlite_db: Path):
    """Verifies the fix: failed publication does NOT remove offer from candidates."""
    channel_id = "@testchannel"
    with create_session() as session:
        offer = Offer(title="Buggy Offer", status="ready", discount_percent=Decimal("50"))
        session.add(offer)
        session.commit()
        offer_id = offer.id

    # Verify it is in candidates initially
    with create_session() as session:
        candidates = list_publish_candidates(session, channel_id=channel_id)
        assert len(candidates) == 1
        assert candidates[0].id == offer_id

    # Simulate failed publication
    bot = FakeBot(should_fail=True)
    result = asyncio.run(publish_offer(bot, offer_id=offer_id, channel_id=channel_id))
    assert result.status == "failed"

    # FIXED: It should still be in candidates
    with create_session() as session:
        candidates = list_publish_candidates(session, channel_id=channel_id)
        assert len(candidates) == 1, "Offer should remain in candidates after failed publication"

def test_retry_after_failure_FIXED(sqlite_db: Path):
    """Verifies the fix: publication successfully retries after failure."""
    channel_id = "@testchannel"
    with create_session() as session:
        offer = Offer(title="Retry Offer", status="ready", discount_percent=Decimal("50"))
        session.add(offer)
        session.commit()
        offer_id = offer.id

    # First attempt fails
    bot_fail = FakeBot(should_fail=True)
    asyncio.run(publish_offer(bot_fail, offer_id=offer_id, channel_id=channel_id))

    # Second attempt (retry)
    bot_ok = FakeBot(should_fail=False)
    result = asyncio.run(publish_offer(bot_ok, offer_id=offer_id, channel_id=channel_id))

    # FIXED: It should now succeed
    assert result.status == "published"
    assert result.telegram_message_id == "101"
    
    with create_session() as session:
        offer = session.get(Offer, offer_id)
        assert offer.status == "published"
        pub = session.scalar(select(Publication).where(Publication.offer_id == offer_id))
        assert pub.status == "published"
        assert pub.telegram_message_id == "101"

def test_pending_protection(sqlite_db: Path):
    """Verifies that 'pending' status protects against concurrent publication (at-most-once)."""
    channel_id = "@testchannel"
    with create_session() as session:
        offer = Offer(title="Pending Offer", status="ready", discount_percent=Decimal("50"))
        session.add(offer)
        session.commit()
        offer_id = offer.id
        
        # Manually create a pending publication
        pub = Publication(offer_id=offer_id, channel_id=channel_id, status="pending")
        session.add(pub)
        session.commit()

    bot = FakeBot()
    result = asyncio.run(publish_offer(bot, offer_id=offer_id, channel_id=channel_id))
    
    assert result.status == "duplicate"
    assert len(bot.messages) == 0
