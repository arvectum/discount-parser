from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from src.shared.config import get_settings
from src.telegram.bot import router as control_router
from src.telegram.xlsx_handlers import router as xlsx_router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(control_router)
    dispatcher.include_router(xlsx_router)
    return dispatcher


async def run_bot_async() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("DP_TELEGRAM_BOT_TOKEN is not configured")
    if not settings.telegram_admin_id_set:
        raise RuntimeError("DP_TELEGRAM_ADMIN_IDS is not configured")
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = build_dispatcher()
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def run_bot() -> None:
    asyncio.run(run_bot_async())
