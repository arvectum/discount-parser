from __future__ import annotations

from urllib.parse import urlsplit

from src.shared.config import get_settings
from src.web.setup import _single_line, _write_env_values

ROUTES = {"auto", "direct", "proxy", "system"}
REQUIRED_BYPASS = ("127.0.0.1", "localhost", "::1")


def _validate_route(value: str, field: str) -> str:
    value = _single_line(value, field).lower() or "auto"
    if value not in ROUTES:
        raise ValueError(f"{field}: допустимы auto/direct/proxy/system")
    return value


def _validate_proxy_url(value: str) -> str:
    value = _single_line(value, "Proxy URL")
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https", "socks5", "socks5h"} or not parts.hostname:
        raise ValueError("Proxy URL должен быть вида http://host:port или socks5://host:port")
    return value


def save_network_settings(
    *,
    network_mode: str,
    proxy_url: str = "",
    proxy_username: str = "",
    proxy_password: str | None = None,
    telegram_network_route: str = "auto",
    no_proxy: str = "",
) -> None:
    network_mode = _validate_route(network_mode, "Режим сети")
    telegram_network_route = _validate_route(telegram_network_route, "Маршрут Telegram")
    proxy_url = _validate_proxy_url(proxy_url)
    proxy_username = _single_line(proxy_username, "Proxy login")
    if proxy_password is not None:
        proxy_password = _single_line(proxy_password, "Proxy password")

    bypass = [item.strip() for item in _single_line(no_proxy, "NO_PROXY").split(",") if item.strip()]
    for item in REQUIRED_BYPASS:
        if item not in bypass:
            bypass.append(item)

    if (network_mode == "proxy" or telegram_network_route == "proxy") and not proxy_url:
        raise ValueError("Для режима proxy укажите Proxy URL.")

    replacements = {
        "DP_NETWORK_MODE": network_mode,
        "DP_PROXY_URL": proxy_url,
        "DP_PROXY_USERNAME": proxy_username,
        "DP_NO_PROXY": ",".join(bypass),
        "DP_TELEGRAM_NETWORK_ROUTE": telegram_network_route,
    }
    # Empty password in the form means "keep the already saved secret".
    if proxy_password is not None and proxy_password != "":
        replacements["DP_PROXY_PASSWORD"] = proxy_password
    elif proxy_password is not None and not get_settings().proxy_password:
        replacements["DP_PROXY_PASSWORD"] = ""
    _write_env_values(replacements)
