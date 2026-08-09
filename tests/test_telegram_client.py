from __future__ import annotations

import pytest

from src.telegram import client


def test_system_proxy_prefers_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "getproxies", lambda: {"http": "http://http-proxy", "all": "http://all-proxy", "https": "http://https-proxy"})
    assert client.system_proxy_url() == "http://https-proxy"


def test_build_bot_for_system_route_uses_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str | None] = {}

    class FakeSession:
        def __init__(self, *, proxy: str | None = None) -> None:
            seen["proxy"] = proxy

    monkeypatch.setattr(client, "resolve_telegram_route", lambda: "system")
    monkeypatch.setattr(client, "system_proxy_url", lambda: "http://system-proxy:8080")
    monkeypatch.setattr(client, "AiohttpSession", FakeSession)

    bot = client.build_bot("123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    assert seen["proxy"] == "http://system-proxy:8080"
    assert bot.session is not None
