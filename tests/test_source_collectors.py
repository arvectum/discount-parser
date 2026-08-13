from __future__ import annotations

import httpx
import pytest

from src.modules.source_registry.collectors import (
    DzenPublicCollector,
    GenericWebCollector,
    RutubePublicCollector,
    TelegramPublicCollector,
)
from src.modules.source_registry.models import RegisteredSource


def _response(url: str, html: str) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(200, text=html, request=request)


def _source(*, platform: str, url: str, collector_type: str, external_id: str | None = None) -> RegisteredSource:
    return RegisteredSource(
        key=f"test-{platform}",
        name=f"Test {platform}",
        platform=platform,
        source_type="test",
        url=url,
        external_id=external_id,
        collector_type=collector_type,
        network_policy="auto",
        enabled=True,
        status="unknown",
        trust_level="official",
        priority=50,
        check_interval_minutes=120,
    )


def _stub_get(html: str):
    return lambda url, **kwargs: _response(url, html)


def test_generic_web_collector_extracts_semantic_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector()
    html = """
    <html><body><main><section class="promo-card">
      <h2>Летняя распродажа</h2>
      <p>Скидка 30% только сегодня</p>
      <a href="/sale/1">Подробнее</a>
      <img src="/img/sale.jpg">
    </section></main></body></html>
    """
    monkeypatch.setattr(collector, "_get", _stub_get(html))
    items = collector.collect(_source(platform="website", url="https://shop.test/promotions", collector_type="generic_web"))
    assert len(items) == 1
    assert items[0].title == "Летняя распродажа"
    assert "Скидка 30%" in (items[0].text or "")
    assert items[0].url == "https://shop.test/sale/1"
    assert items[0].image_url == "https://shop.test/img/sale.jpg"


def test_generic_web_collector_handles_more_than_150_profiled_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = GenericWebCollector()
    html = ''.join(
        f'<article class="card"><h3>Скидка {index}%</h3><p>Промокод QA{index:03d}</p></article>'
        for index in range(180)
    )
    source = _source(platform="website", url="https://shop.test/qa", collector_type="generic_web")
    source.item_selector = '.card'
    source.title_selector = 'h3'
    monkeypatch.setattr(collector, '_get', _stub_get(html))
    assert len(collector.collect(source)) == 180


def test_telegram_public_collector_extracts_post(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = TelegramPublicCollector()
    html = """
    <div class="tgme_widget_message_wrap">
      <div class="tgme_widget_message" data-post="shop/42"></div>
      <div class="tgme_widget_message_text">Промокод SALE20 — скидка 20%</div>
      <a class="tgme_widget_message_date" href="https://t.me/shop/42"><time datetime="2026-08-08T10:00:00+00:00"></time></a>
    </div>
    """
    monkeypatch.setattr(collector, "_get", _stub_get(html))
    items = collector.collect(_source(platform="telegram", url="https://t.me/shop", external_id="shop", collector_type="telegram_public"))
    assert len(items) == 1
    assert items[0].external_id == "telegram:shop:42"
    assert "SALE20" in (items[0].text or "")
    assert items[0].url == "https://t.me/shop/42"


def test_rutube_public_collector_deduplicates_video_links(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = RutubePublicCollector()
    html = """
    <html><body>
      <a href="/video/abc/">Акции недели — скидка 40%</a>
      <a href="/video/abc/">Акции недели — скидка 40%</a>
    </body></html>
    """
    monkeypatch.setattr(collector, "_get", _stub_get(html))
    items = collector.collect(_source(platform="rutube", url="https://rutube.ru/channel/1/", collector_type="rutube_public"))
    assert len(items) == 1
    assert items[0].external_id == "abc"
    assert items[0].url == "https://rutube.ru/video/abc/"


def test_dzen_collector_uses_public_page_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = DzenPublicCollector()
    html = "<html><body><article><h2>Акция магазина</h2><p>Скидка 15% по выходным</p></article></body></html>"
    monkeypatch.setattr(collector, "_get", _stub_get(html))
    items = collector.collect(_source(platform="dzen", url="https://dzen.ru/shop", collector_type="dzen_public"))
    assert len(items) == 1
    assert items[0].title == "Акция магазина"
