from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from src.shared.config import get_settings
from src.shared.network import NetworkRouteError, configured_proxy_url, network_router

TELEGRAM_API_ROOT = "https://api.telegram.org"


def resolve_telegram_route() -> str:
    settings = get_settings()
    requested = (settings.telegram_network_route or settings.network_mode or "auto").strip().lower()
    if requested in {"direct", "system"}:
        return requested
    if requested == "proxy":
        if not configured_proxy_url():
            raise NetworkRouteError("Telegram proxy route selected but proxy URL is empty")
        return "proxy"
    return network_router.choose_route(TELEGRAM_API_ROOT)


def build_bot(token: str) -> Bot:
    route = resolve_telegram_route()
    if route == "proxy":
        session = AiohttpSession(proxy=configured_proxy_url())
        return Bot(token=token, session=session)
    # aiohttp ignores HTTP(S)_PROXY environment variables by default. That is
    # intentional for direct; a TUN VPN still applies at OS routing level.
    return Bot(token=token)
