from __future__ import annotations

import asyncio

from src.modules.publishing.filters import get_or_create_default_filter
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import create_session
from src.telegram.client import build_bot
from src.telegram.publisher import PublishResult, publish_offer


async def run_autopost_cycle_async() -> list[PublishResult]:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        return []

    row = get_or_create_default_filter(min_discount_percent=settings.telegram_default_min_discount)
    if not row.enabled:
        return []

    criteria = PublishCriteria.from_filter(row)
    with create_session() as session:
        candidates = list_publish_candidates(session, channel_id=settings.telegram_channel_id, criteria=criteria)
        offer_ids = [offer.id for offer in candidates]

    if not offer_ids:
        return []

    bot = build_bot(settings.telegram_bot_token)
    results: list[PublishResult] = []
    try:
        for offer_id in offer_ids:
            results.append(await publish_offer(bot, offer_id=offer_id, channel_id=settings.telegram_channel_id))
    finally:
        await bot.session.close()
    return results


def run_autopost_cycle() -> list[PublishResult]:
    return asyncio.run(run_autopost_cycle_async())
