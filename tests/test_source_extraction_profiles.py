from __future__ import annotations

import httpx
import pytest

from src.modules.source_registry.collectors import CollectorError, GenericWebCollector
from src.modules.source_registry.models import RegisteredSource


def _source(**values) -> RegisteredSource:
    defaults = dict(key="profile", name="Profile", platform="website", source_type="promo_page", url="https://shop.test/offers", collector_type="generic_web", network_policy="direct", enabled=True, status="unknown", trust_level="official", priority=50, check_interval_minutes=120)
    defaults.update(values)
    return RegisteredSource(**defaults)


def test_profile_extracts_multiple_offer_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    html = '''<article class="card"><h3>Скидка 10%</h3><b class="code" data-code="ONE10"></b><p class="conditions">на всё</p><time>до 31.05.2026</time><a class="go" href="/one"></a></article><article class="card"><h3>Скидка 20%</h3><b class="code" data-code="TWO20"></b><p class="conditions">на заказ</p><time>до 30.06.2026</time><a class="go" href="/two"></a></article>'''
    source = _source(item_selector=".card", title_selector="h3", promo_code_selector=".code", promo_code_attribute="data-code", conditions_selector=".conditions", valid_until_selector="time", link_selector="a.go")
    collector = GenericWebCollector()
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    items = collector.collect(source)
    assert [x.title for x in items] == ["Скидка 10%", "Скидка 20%"]
    assert [x.raw_payload["promo_code"] for x in items] == ["ONE10", "TWO20"]
    assert items[0].url == "https://shop.test/one"
    assert items[0].raw_payload["conditions"] == "на всё"


def test_profile_zero_matches_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(item_selector=".missing")
    collector = GenericWebCollector()
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text="<article><h3>Скидка 10% на весь заказ</h3></article>", request=httpx.Request("GET", url)))
    assert collector.collect(source)[0].raw_payload["collector"] == "generic_web"


def test_profile_invalid_selector_is_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector(); source = _source(item_selector="[")
    monkeypatch.setattr(collector, "_get", lambda url, **kw: httpx.Response(200, text="<body></body>", request=httpx.Request("GET", url)))
    with pytest.raises(CollectorError, match="invalid extraction"):
        collector.collect(source)
