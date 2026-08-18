from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.shared.config import get_settings
from src.shared.logging import redact_secrets
from src.telegram.client import build_bot
from src.telegram.publisher import PublishResult, publish_offer

logger = logging.getLogger(__name__)


def _clean_error(value: str | None) -> str:
    if not value:
        return "неизвестная ошибка Telegram"
    clean = redact_secrets(value).replace("\r", " ").replace("\n", " ").strip()
    if len(clean) > 260:
        clean = clean[:257] + "..."
    return clean


def _result_message(result: PublishResult) -> str:
    if result.status == "published":
        return "Публикация выполнена."
    if result.status == "duplicate":
        return "Это предложение уже зарезервировано или опубликовано."
    if result.status == "not_publishable":
        return "Предложение сейчас недоступно для публикации."
    if result.status == "not_found":
        return "Предложение не найдено."
    if result.status == "failed":
        return f"Публикация не выполнена: {_clean_error(result.error)}. Предложение осталось в очереди, отправку можно повторить."
    return f"Публикация завершилась со статусом: {result.status}."


def web_publish_hotfix(offer_id: int):
    """Manual publish path that uses the same network router as autoposting."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        return RedirectResponse('/setup', status_code=303)

    async def _publish() -> PublishResult:
        bot = build_bot(settings.telegram_bot_token)
        try:
            return await publish_offer(
                bot,
                offer_id=offer_id,
                channel_id=settings.telegram_channel_id,
            )
        finally:
            await bot.session.close()

    try:
        result = asyncio.run(_publish())
    except Exception as exc:
        clean = _clean_error(f"{type(exc).__name__}: {exc}")
        logger.warning("manual_publish_route_failed offer_id=%s error=%s", offer_id, clean)
        message = f"Публикация не выполнена: {clean}. Предложение осталось в очереди, отправку можно повторить."
        return RedirectResponse('/?message=' + quote(message, safe=''), status_code=303)

    if result.status == "failed":
        logger.warning(
            "manual_publish_failed offer_id=%s publication_id=%s error=%s",
            offer_id,
            result.publication_id,
            _clean_error(result.error),
        )
    return RedirectResponse('/?message=' + quote(_result_message(result), safe=''), status_code=303)


def install_customer_hotfixes(app: FastAPI) -> None:
    """Install upgrade-safe route replacements after the canonical app loads.

    The historical Web UI route constructed aiogram.Bot directly, bypassing the
    configured DIRECT/SYSTEM/PROXY router used by the scheduler/autoposter.  A
    frozen customer build enters through ``src.web.launcher``; replacing the
    legacy POST route there restores one network contract for both manual and
    automatic publishing without changing database semantics.
    """
    target_path = "/publish/{offer_id}"
    retained = []
    for route in app.router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", None) == target_path and "POST" in methods:
            continue
        retained.append(route)
    app.router.routes[:] = retained
    app.add_api_route(target_path, web_publish_hotfix, methods=["POST"])
