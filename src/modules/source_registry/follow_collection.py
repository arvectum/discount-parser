from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.modules.source_registry.collectors import CollectorError, GenericWebCollector
from src.modules.source_registry.follow_profiles import extract_internal_detail_urls, get_follow_profile
from src.modules.source_registry.service import ItemPayload


_PATCH_MARKER = "_dp_cust_011_follow_profile_patch"


def _clean_soup(html_text: str) -> BeautifulSoup:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup


def _merchant_from_detail(soup: BeautifulSoup, selector: str | None, detail_url: str) -> str | None:
    if selector:
        try:
            node = soup.select_one(selector)
        except Exception as exc:
            raise CollectorError(f"invalid merchant CSS selector: {exc}") from exc
        if node is not None:
            value = node.get_text(" ", strip=True)
            if value:
                return value[:255]
    # Conservative fallback for aggregator detail pages: page heading first,
    # then the path slug. Explicit selector remains the preferred customer path.
    for candidate in soup.select("h1, h2"):
        value = candidate.get_text(" ", strip=True)
        if value and len(value) <= 255:
            return value
    slug = urlparse(detail_url).path.rstrip("/").split("/")[-1].strip()
    return slug[:255] or None


def _detail_payload(payload: ItemPayload, *, entry_url: str, detail_url: str, merchant: str | None) -> ItemPayload:
    metadata = dict(payload.raw_payload or {})
    metadata.update({
        "crawl_mode": "follow_internal",
        "entry_url": entry_url,
        "detail_url": detail_url,
        "merchant": merchant,
    })
    return replace(payload, raw_payload=metadata)


def install_follow_profile_collection() -> None:
    if getattr(GenericWebCollector, _PATCH_MARKER, False):
        return

    original_collect = GenericWebCollector.collect

    def collect_with_follow(self, source) -> list[ItemPayload]:
        profile = get_follow_profile(getattr(source, "id", None))
        if profile.crawl_mode != "follow_internal":
            return original_collect(self, source)
        if not source.item_selector:
            raise CollectorError("two-stage source requires a saved detail extraction profile")

        entry_response = self._get(source.url, route=source.network_policy)
        entry_url = str(entry_response.url)
        entry_soup = _clean_soup(entry_response.text)
        try:
            detail_urls = extract_internal_detail_urls(entry_soup, entry_url=entry_url, profile=profile)
        except ValueError as exc:
            raise CollectorError(str(exc)) from exc
        if not detail_urls:
            raise CollectorError(
                "По настройке каталога не найдено внутренних страниц предложений. "
                "Проверьте selector кнопки «Все промокоды» и фильтр адреса."
            )

        result: list[ItemPayload] = []
        for detail_url in detail_urls:
            detail_response = self._get(detail_url, route=source.network_policy)
            detail_page_url = str(detail_response.url)
            detail_soup = _clean_soup(detail_response.text)
            merchant = _merchant_from_detail(detail_soup, profile.merchant_selector, detail_page_url)
            items = self._profile_items(source, detail_soup, detail_page_url)
            if not items:
                items = self._known_site_items(source, detail_page_url, str(detail_soup))
            for item in items:
                result.append(_detail_payload(item, entry_url=entry_url, detail_url=detail_page_url, merchant=merchant))
                if len(result) >= self.policy.max_items:
                    return result
        return result

    GenericWebCollector.collect = collect_with_follow
    setattr(GenericWebCollector, _PATCH_MARKER, True)
