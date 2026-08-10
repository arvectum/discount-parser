from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.modules.source_registry.models import RegisteredSource
from src.shared.config import get_settings
from src.shared.db import Base, get_engine, reset_db_runtime, session_scope
from src.sources.config import SourceConfig, load_source_configs
from src.sources.http import HttpClient
from src.sources.runner import _effective_config


def test_legacy_http_client_uses_network_router(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return httpx.Response(200, text="ok", request=httpx.Request("GET", url))

    monkeypatch.setattr("src.sources.http.network_router.get", fake_get)
    client = HttpClient(network_policy="direct", retries=1)
    assert client.get_text("https://example.test/deals") == "ok"
    assert calls[0]["route"] == "direct"
    assert calls[0]["retry_statuses"] == set()


def test_legacy_http_auto_allows_geo_block_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return httpx.Response(200, text="ok", request=httpx.Request("GET", url))

    monkeypatch.setattr("src.sources.http.network_router.get", fake_get)
    HttpClient(network_policy="auto", retries=1).get_text("https://example.test/deals")
    assert calls[0]["route"] == "auto"
    assert calls[0]["retry_statuses"] == {403, 451}


def test_source_config_reads_network_policy(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - key: one\n"
        "    name: One\n"
        "    adapter: promokood\n"
        "    base_url: https://example.test/\n"
        "    network_policy: proxy\n",
        encoding="utf-8",
    )
    configs = load_source_configs(path)
    assert configs[0].network_policy == "proxy"


def test_registry_policy_overrides_legacy_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'network.db'}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        with session_scope() as session:
            session.add(
                RegisteredSource(
                    key="promokood",
                    name="Promokood",
                    platform="promo_aggregator",
                    source_type="promo_aggregator",
                    url="https://promokood.ru/",
                    collector_type="legacy_adapter",
                    enabled=True,
                    status="unknown",
                    trust_level="aggregator",
                    priority=50,
                    check_interval_minutes=120,
                    network_policy="direct",
                )
            )
        config = SourceConfig(
            key="promokood",
            name="Promokood",
            adapter="promokood",
            base_url="https://promokood.ru/",
            network_policy="auto",
        )
        assert _effective_config(config).network_policy == "direct"
    finally:
        reset_db_runtime()
        get_settings.cache_clear()
