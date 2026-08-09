from __future__ import annotations

from urllib.request import getproxies

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from src.shared.config import get_settings
from src.shared.network import NetworkRouteError, configured_proxy_url, network_router

TELEGRAM_API_ROOT = "https://api.telegram.org"


def system_proxy_url() -> str | None:
    """Return the proxy selected by macOS/environment proxy settings.

    ``aiohttp`` does not automatically honour proxy environment variables, so
    the route selected by NetworkRouter must be forwarded explicitly to
    aiogram's session.
    """
    proxies = getproxies()
    return proxies.get("https") or proxies.get("all") or proxies.get("http")


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
    if route == "system":
        proxy_url = system_proxy_url()
        if proxy_url:
            return Bot(token=token, session=AiohttpSession(proxy=proxy_url))
    # Direct intentionally bypasses HTTP(S)_PROXY. A TUN VPN still applies at
    # OS routing level, while SYSTEM above explicitly forwards proxy settings.
    return Bot(token=token)
