from __future__ import annotations

from bs4 import BeautifulSoup
from fastapi import FastAPI

from src.modules.source_registry import image_profiles
from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.models import RegisteredSource
from src.web import customer_hotfixes


def _source() -> RegisteredSource:
    return RegisteredSource(
        id=77,
        key="shop",
        name="Shop",
        platform="website",
        source_type="promo",
        url="https://example.test/deals",
        collector_type="generic_web",
        network_policy="direct",
        priority=50,
        trust_level="unknown",
        check_interval_minutes=60,
        enabled=True,
        status="unknown",
        failure_count=0,
        item_selector=".offer",
        title_selector=".title",
    )


def test_precise_css_profile_extracts_configured_image(monkeypatch) -> None:
    image_profiles.install_profile_image_extraction()
    monkeypatch.setattr(image_profiles, "get_image_profile", lambda source_id: ("img.hero", "data-src"))
    soup = BeautifulSoup(
        '<div class="offer"><h2 class="title">Скидка 20%</h2><img class="hero" data-src="/img/deal.jpg"></div>',
        "html.parser",
    )

    items = GenericWebCollector()._profile_items(_source(), soup, "https://example.test/deals")

    assert len(items) == 1
    assert items[0].image_url == "https://example.test/img/deal.jpg"


def test_precise_css_profile_auto_detects_image_when_selector_empty(monkeypatch) -> None:
    image_profiles.install_profile_image_extraction()
    monkeypatch.setattr(image_profiles, "get_image_profile", lambda source_id: (None, None))
    soup = BeautifulSoup(
        '<div class="offer"><h2 class="title">Промокод SALE</h2><img src="/img/auto.jpg"></div>',
        "html.parser",
    )

    items = GenericWebCollector()._profile_items(_source(), soup, "https://example.test/deals")

    assert items[0].image_url == "https://example.test/img/auto.jpg"


def test_customer_hotfix_replaces_sources_route_and_adds_image_profile_route() -> None:
    app = FastAPI()

    @app.get("/sources-registry")
    def legacy_sources():
        return "legacy"

    customer_hotfixes.install_customer_hotfixes(app)

    source_matches = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) == "/sources-registry"
        and "GET" in set(getattr(route, "methods", set()) or set())
    ]
    image_matches = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) == "/sources-registry/{source_id}/image-profile"
        and "POST" in set(getattr(route, "methods", set()) or set())
    ]

    assert len(source_matches) == 1
    assert source_matches[0].endpoint is customer_hotfixes.sources_registry_hotfix
    assert len(image_matches) == 1
    assert image_matches[0].endpoint is customer_hotfixes.image_profile_save


def test_telegram_publisher_keeps_photo_with_text_fallback_contract() -> None:
    source = (customer_hotfixes.__file__ and __import__("inspect").getsource(__import__("src.telegram.publisher", fromlist=["publish_offer"])))
    assert "send_photo" in source
    assert "send_message" in source
    assert "if offer.image_url" in source
