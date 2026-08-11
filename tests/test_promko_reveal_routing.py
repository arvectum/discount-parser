from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from src.modules.offers.models import Offer
from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.models import RegisteredSource, SourceItem
from src.modules.source_registry.promko_reveal import reveal_promko_code
from src.modules.source_registry.runner import collect_registered_source
from src.modules.source_registry.service import ItemPayload
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


def _source(url: str) -> RegisteredSource:
    return RegisteredSource(key="test", name="test", platform="website", source_type="promo_page", url=url,
                            collector_type="generic_web", network_policy="direct", enabled=True, status="unknown",
                            trust_level="aggregator", priority=50, check_interval_minutes=120)


def test_automatic_promko_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector()
    html = '<article><h3>Скидка 17% от 3500 руб.</h3><div>Активный до 31.12.2026</div><a data-coupon-id="15796">Показать промокод</a></article>'
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    item = collector.collect(_source("https://promko.net/ru/shops/aravia"))[0]
    assert item.external_id == "promko-coupon:15796"
    assert item.raw_payload["adapter"] == "promko"
    assert item.raw_payload["promko_coupon_id"] == "15796"
    assert item.raw_payload["needs_reveal"] is True


def test_automatic_promokood_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector()
    html = '''<article><h3>Скидка 10%</h3><div>Промокод FIRST1 до 31.12.2026</div><button>Получить промокод</button></article>
    <article><h3>Скидка 20%</h3><div>Промокод SECOND2 до 30.11.2026</div><button>Получить промокод</button></article>'''
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    items = collector.collect(_source("https://promokood.ru/o/vseinstrumenti"))
    assert len(items) == 2
    assert {item.raw_payload["promo_code"] for item in items} == {"FIRST1", "SECOND2"}
    assert all(item.raw_payload["adapter"] == "promokood" for item in items)
    assert all(item.raw_payload["valid_until"] for item in items)


def test_promko_profile_coupon_id_is_not_code(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector()
    source = _source("https://promko.net/ru/shops/aravia")
    source.extraction_profile_json = json.dumps({"item_selector": ".coupon", "title_selector": ".title", "promo_code_selector": ".masked", "reveal_selector": "button.reveal", "reveal_code_attribute": "data-coupon-id"})
    html = '<div class="coupon"><span class="title">Скидка 17%</span><span class="masked">••••••••</span><button class="reveal" data-coupon-id="15796">Показать промокод</button></div>'
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    payload = collector.collect(source)[0].raw_payload
    assert payload["promo_code"] is None
    assert payload["promko_coupon_id"] == "15796"
    assert payload["needs_reveal"] is True


def test_sanctum_xsrf_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str | None]] = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers.get("X-XSRF-TOKEN")))
        if request.url.path == "/sanctum/csrf-cookie":
            return httpx.Response(204, headers={"set-cookie": "XSRF-TOKEN=a%2Fb; Path=/"}, request=request)
        return httpx.Response(200, json={"promocode": "admitad16"}, request=request)
    class Client:
        def __init__(self): self.client = httpx.Client(transport=httpx.MockTransport(handler))
        def __enter__(self): return self.client
        def __exit__(self, *args): self.client.close()
    monkeypatch.setattr("src.modules.source_registry.promko_reveal._client_for_route", lambda *args: Client())
    assert reveal_promko_code("15796", referer="https://promko.net/ru/shops/aravia", route="direct") == "admitad16"
    assert calls == [("GET", "/sanctum/csrf-cookie", None), ("POST", "/api/promocodes/15796/use", "a/b")]


@pytest.fixture
def reveal_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'r.db'}")
    get_settings.cache_clear(); reset_db_runtime(); Base.metadata.create_all(get_engine())
    try: yield
    finally: reset_db_runtime(); get_settings.cache_clear()


def _registered() -> int:
    with create_session() as session:
        row = _source("https://promko.net/ru/shops/aravia")
        session.add(row); session.commit()
        return row.id


def _payload(coupon_id: str) -> ItemPayload:
    return ItemPayload(f"promko-coupon:{coupon_id}", f"https://promko.net/ru/shops/aravia#offer-{coupon_id}", "Скидка 16% на весь заказ", "Скидка 16% на весь заказ Активный до 31.12.2026 Показать промокод", raw_payload={"adapter": "promko", "promko_coupon_id": coupon_id, "needs_reveal": True, "promo_code": None, "valid_until": "2026-12-31T23:59:59+00:00"})


def test_registry_reveals_once_and_reuses(reveal_db, monkeypatch: pytest.MonkeyPatch) -> None:
    source_id = _registered(); calls = []
    class Collector:
        def collect(self, source): return [_payload("15796")]
    monkeypatch.setattr("src.modules.source_registry.runner.build_collector", lambda _: Collector())
    monkeypatch.setattr("src.modules.source_registry.runner.reveal_promko_code", lambda coupon_id, *, referer, route: calls.append((coupon_id, referer)) or "admitad16")
    first, second = collect_registered_source(source_id), collect_registered_source(source_id)
    with create_session() as session: offer = session.scalar(select(Offer))
    assert (first.errors, first.items_created, first.offers_created) == (0, 1, 1)
    assert (second.errors, second.items_created) == (0, 0)
    assert calls == [("15796", "https://promko.net/ru/shops/aravia")]
    assert offer.promo_code == "ADMITAD16"


def test_registry_does_not_retry_failed_promko_reveal(reveal_db, monkeypatch: pytest.MonkeyPatch) -> None:
    source_id = _registered(); calls = []
    class Collector:
        def collect(self, source): return [_payload("99999")]
    def fail(*args, **kwargs): calls.append(1); raise RuntimeError("temporary upstream failure")
    monkeypatch.setattr("src.modules.source_registry.runner.build_collector", lambda _: Collector())
    monkeypatch.setattr("src.modules.source_registry.runner.reveal_promko_code", fail)
    first, second = collect_registered_source(source_id), collect_registered_source(source_id)
    with create_session() as session:
        source = session.get(RegisteredSource, source_id); offer = session.scalar(select(Offer)); item = session.scalar(select(SourceItem))
    assert first.errors == second.errors == 1 and len(calls) == 1
    assert "automatic retry disabled" in (second.error or "")
    assert source.status == "degraded" and offer.promo_code is None
    assert json.loads(item.raw_payload_json)["promko_reveal_resolved"] is False
    assert "automatic retry disabled" in json.loads(item.raw_payload_json)["promko_reveal_error"]
