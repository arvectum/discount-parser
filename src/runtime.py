from __future__ import annotations

import asyncio
import logging

from src.jobs.scheduler import build_scheduler
from src.telegram.runner import run_bot_async

logger = logging.getLogger(__name__)


async def run_all_async() -> None:
    scheduler = build_scheduler(background=True)
    scheduler.start()
    logger.info("runtime_started", extra={"services": ["telegram_bot", "scheduler"]})
    try:
        await run_bot_async()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("runtime_stopped")


def run_all() -> None:
    asyncio.run(run_all_async())
