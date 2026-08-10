from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.shared.config import get_settings
from src.shared.network import NetworkRouter, is_loopback_url
from src.web.application import app
from src.web.network_settings import save_network_settings


class _FakeClient:
    def __init__(self, route: str, calls: list[str], responses: dict[str, object]):
        self.route = route
        self.calls = calls
        self.responses = responses

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method: str, url: str, **kwargs):
        self.calls.append(self.route)
        outcome = self.responses[self.route]
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(int(outcome), request=httpx.Request(method, url))


def test_loopback_is_always_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    router = NetworkRouter()
    monkeypatch.setenv("DP_NETWORK_MODE", "proxy")
    monkeypatch.setenv("DP_PROXY_URL", "http://127.0.0.1:7890")
    get_settings.cache_clear()
    assert is_loopback_url("http://127.0.0.1:8765/health") is True
    assert is_loopback_url("http://localhost:8765") is True
    assert router._candidate_routes("http://127.0.0.1:8765/health") == ["direct"]
    get_settings.cache_clear()


def test_auto_falls_back_to_proxy_and_remembers(monkeypatch: pytest.MonkeyPatch) -> None:
    router = NetworkRouter()
    calls: list[str] = []
    monkeypatch.setenv("DP_NETWORK_MODE", "auto")
    monkeypatch.setenv("DP_PROXY_URL", "http://127.0.0.1:7890")
    get_settings.cache_clear()
    responses = {
        "direct": httpx.ConnectError("blocked"),
        "proxy": 200,
        "system": 200,
    }
    monkeypatch.setattr(router, "_client", lambda route, timeout, headers=None: _FakeClient(route, calls, responses))
    response = router.get("https://example.test/path")
    assert response.status_code == 200
    assert calls == ["direct", "proxy"]
    assert router._candidate_routes("https://example.test/other")[0] == "proxy"
    get_settings.cache_clear()


def test_network_settings_persist_and_force_loopback_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env.example").write_text("DP_NETWORK_MODE=auto\n", encoding="utf-8")
    monkeypatch.setenv("DP_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("DP_ENV_FILE", raising=False)
    get_settings.cache_clear()
    save_network_settings(
        network_mode="auto",
        proxy_url="socks5://127.0.0.1:1080",
        proxy_username="user",
        proxy_password="secret",
        telegram_network_route="proxy",
        no_proxy="internal.example",
    )
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.proxy_url == "socks5://127.0.0.1:1080"
    assert settings.proxy_password == "secret"
    assert settings.telegram_network_route == "proxy"
    for required in ("127.0.0.1", "localhost", "::1"):
        assert required in settings.no_proxy


def test_network_page_requires_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env.example").write_text("DP_NETWORK_MODE=auto\n", encoding="utf-8")
    monkeypatch.setenv("DP_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("DP_ENV_FILE", raising=False)
    get_settings.cache_clear()
    response = TestClient(app).get("/network", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"
    get_settings.cache_clear()
