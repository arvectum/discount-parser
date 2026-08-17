from __future__ import annotations

import httpx
import pytest
from pathlib import Path
from sqlalchemy import select

from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.promko_reveal import reveal_promko_code
from src.modules.source_registry.runner import collect_registered_source
from src.modules.source_registry.service import ItemPayload
from src.modules.offers.models import Offer
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


def _source(url: str, **extra) -> RegisteredSource:
    values = dict(key="promko", name="PROMKO", platform="website", source_type="promo_page", url=url, collector_type="generic_web", network_policy="direct", enabled=True, status="unknown", trust_level="aggregator", priority=50, check_interval_minutes=120)
    values.update(extra)
    return RegisteredSource(**values)


def test_known_site_routing_and_profile_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    html = '<article class="coupon"><h3>Скидка 17%</h3><button data-coupon-id="15796">Показать промокод</button></article>'
    collector = GenericWebCollector()
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    payload = collector.collect(_source("https://promko.net/ru/shops/aravia"))[0]
    assert payload.external_id == "promko-coupon:15796" and payload.raw_payload["needs_reveal"]
    profile = _source("https://promko.net/ru/shops/aravia", item_selector=".coupon", reveal_selector="button", reveal_code_attribute="data-coupon-id")
    payload = collector.collect(profile)[0]
    assert payload.raw_payload["collector"] == "css_profile"
    assert payload.raw_payload["promo_code"] is None and payload.raw_payload["promko_coupon_id"] == "15796"


def test_promokood_known_site_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    html = '<article><h3>Скидка 10%</h3><p>Промокод FIRST1</p><button>Получить промокод</button></article>'
    collector = GenericWebCollector()
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    payload = collector.collect(_source("https://promokood.ru/o/vseinstrumenti"))[0]
    assert payload.raw_payload["adapter"] == "promokood" and payload.raw_payload["promo_code"] == "FIRST1"


def test_sanctum_xsrf_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path, request.headers.get("X-XSRF-TOKEN")))
        if request.method == "GET": return httpx.Response(204, headers={"set-cookie": "XSRF-TOKEN=a%2Fb; Path=/"}, request=request)
        return httpx.Response(200, json={"promocode": "admitad16"}, request=request)
    class Client:
        def __enter__(self): self.client = httpx.Client(transport=httpx.MockTransport(handler)); return self.client
        def __exit__(self, *args): self.client.close()
    monkeypatch.setattr("src.modules.source_registry.promko_reveal._client_for_route", lambda *args: Client())
    assert reveal_promko_code("15796", referer="https://promko.net/ru/shops/aravia", route="direct") == "admitad16"
    assert calls == [("GET", "/sanctum/csrf-cookie", None), ("POST", "/api/promocodes/15796/use", "a/b")]


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'r12.db'}")
    get_settings.cache_clear(); reset_db_runtime(); Base.metadata.create_all(get_engine())
    try: yield
    finally: reset_db_runtime(); get_settings.cache_clear()


def _payload(coupon: str) -> ItemPayload:
    return ItemPayload(f"promko-coupon:{coupon}", "https://promko.net/ru/shops/aravia", "Скидка 16%", "Скидка 16% Показать промокод", raw_payload={"promko_coupon_id": coupon, "promo_code": None, "valid_until": "2026-12-31T23:59:59+00:00"})


def test_registry_does_not_retry_failed_promko_reveal(db, monkeypatch: pytest.MonkeyPatch) -> None:
    with create_session() as session:
        source = _source("https://promko.net/ru/shops/aravia"); session.add(source); session.commit(); source_id = source.id
    class Collector:
        def collect(self, source): return [_payload("99999")]
    calls = []
    def fail(*args, **kwargs): calls.append(1); raise RuntimeError("temporary upstream failure")
    monkeypatch.setattr("src.modules.source_registry.runner.build_collector", lambda _: Collector())
    monkeypatch.setattr("src.modules.source_registry.runner.reveal_promko_code", fail)
    first, second = collect_registered_source(source_id), collect_registered_source(source_id)
    with create_session() as session: offer = session.scalar(select(Offer)); source = session.get(RegisteredSource, source_id)
    assert first.errors == second.errors == 1 and len(calls) == 1
    assert "automatic retry disabled" in (second.error or "")
    assert source.status == "degraded" and offer.promo_code is None
