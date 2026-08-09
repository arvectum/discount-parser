from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from src.shared.config import get_settings
from src.shared.network import NetworkRouteError, network_router

TELEGRAM_API_ROOT = "https://api.telegram.org"


def _proxy_url_with_credentials() -> str | None:
    settings = get_settings()
    raw = (settings.proxy_url or "").strip()
    if not raw:
        return None
    if not settings.proxy_username:
        return raw
    parts = urlsplit(raw)
    if not parts.scheme or not parts.hostname:
        return raw
    username = quote(settings.proxy_username, safe="")
    password = quote(settings.proxy_password or "", safe="")
    auth = username + (f":{password}" if settings.proxy_password is not None else "")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{auth}@{host}{port}", parts.path, parts.query, parts.fragment))


def resolve_telegram_route() -> str:
    settings = get_settings()
    requested = (settings.telegram_network_route or settings.network_mode or "auto").strip().lower()
    if requested in {"direct", "system"}:
        return requested
    if requested == "proxy":
        if not _proxy_url_with_credentials():
            raise NetworkRouteError("Telegram proxy route selected but proxy URL is empty")
        return "proxy"
    return network_router.choose_route(TELEGRAM_API_ROOT)


def build_bot(token: str) -> Bot:
    route = resolve_telegram_route()
    if route == "proxy":
        session = AiohttpSession(proxy=_proxy_url_with_credentials())
        return Bot(token=token, session=session)
    # aiohttp ignores HTTP(S)_PROXY environment variables by default. That is
    # intentional for the direct route; a TUN VPN still applies at OS level.
    return Bot(token=token)
