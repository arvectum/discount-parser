from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.modules.source_registry.auto_setup import AutoPreviewItem, _preview, normalize_source_url
from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.manual_profile import ManualProfile, normalize_manual_profile, preview_manual_profile_html


_DYNAMIC_CLASS_RE = re.compile(r"(?:^|[-_])[a-f0-9]{7,}(?:$|[-_])", re.I)
_PROMO_HINT_RE = re.compile(r"промокод|promo\s*code|coupon\s*code|скидк|%", re.I)
_DATE_HINT_RE = re.compile(r"до\s+\d|действует|срок|valid|expire", re.I)


@dataclass(frozen=True, slots=True)
class AssistedSourceProposal:
    url: str
    name: str
    crawl_mode: str
    strategy: str
    confidence: float
    explanation: str
    listing_item_selector: str | None = None
    detail_link_selector: str | None = None
    detail_url_contains: str | None = None
    sample_detail_url: str | None = None
    item_selector: str | None = None
    title_selector: str | None = None
    promo_code_selector: str | None = None
    promo_code_attribute: str | None = None
    conditions_selector: str | None = None
    valid_until_selector: str | None = None
    link_selector: str | None = None
    image_selector: str | None = None
    image_attribute: str | None = None
    previews: tuple[AutoPreviewItem, ...] = ()
    discovered_detail_pages: int = 0

    @property
    def can_confirm(self) -> bool:
        return bool(self.previews) and self.confidence >= 0.70


def _site_name(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    label = host.split(".")[0].replace("-", " ").replace("_", " ").strip()
    return label[:1].upper() + label[1:] if label else host or "Источник"


def _source_stub(url: str):
    return SimpleNamespace(
        id=None,
        url=url,
        network_policy="auto",
        item_selector=None,
        title_selector=None,
        promo_code_selector=None,
        promo_code_attribute=None,
        conditions_selector=None,
        valid_until_selector=None,
        link_selector=None,
        reveal_selector=None,
        reveal_code_attribute=None,
    )


def _clean_soup(html_text: str) -> BeautifulSoup:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup


def _stable_classes(tag: Tag) -> list[str]:
    result: list[str] = []
    for value in tag.get("class", []):
        text = str(value).strip()
        if not text or _DYNAMIC_CLASS_RE.search(text) or len(text) > 64:
            continue
        if any(char in text for char in ":/[]()"):
            continue
        result.append(text)
    return result[:3]


def _selector(tag: Tag) -> str:
    tag_name = tag.name or "div"
    if tag.get("id"):
        ident = str(tag.get("id")).strip()
        if ident and len(ident) <= 80 and not _DYNAMIC_CLASS_RE.search(ident):
            return f"#{ident}"
    classes = _stable_classes(tag)
    if classes:
        return tag_name + "".join(f".{value}" for value in classes)
    return tag_name


def _relative_selector(container: Tag, target: Tag | None) -> str | None:
    if target is None:
        return None
    if target is container:
        return ":scope"
    return _selector(target)


def _same_host_detail_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, Tag]]:
    host = (urlparse(page_url).hostname or "").casefold().removeprefix("www.")
    result: list[tuple[str, Tag]] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        absolute = urljoin(page_url, str(link.get("href") or ""))
        parsed = urlparse(absolute)
        target_host = (parsed.hostname or "").casefold().removeprefix("www.")
        if target_host != host or absolute in seen:
            continue
        seen.add(absolute)
        result.append((absolute, link))
    return result


def _common_path_marker(urls: list[str]) -> str | None:
    paths = [urlparse(url).path for url in urls]
    if not paths:
        return None
    first_segments = []
    for path in paths:
        parts = [part for part in path.split("/") if part]
        if parts:
            first_segments.append(parts[0])
    if first_segments and len(set(first_segments)) == 1:
        return f"/{first_segments[0]}/"
    return None


def _promokood_category_proposal(url: str, soup: BeautifulSoup, collector: GenericWebCollector) -> AssistedSourceProposal | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host != "promokood.ru" or parsed.path.casefold().startswith("/o/"):
        return None
    detail_urls = [
        href
        for href, _ in _same_host_detail_links(soup, url)
        if urlparse(href).path.casefold().startswith("/o/")
    ]
    detail_urls = list(dict.fromkeys(detail_urls))
    if not detail_urls:
        return None
    previews: list[AutoPreviewItem] = []
    for detail_url in detail_urls[:3]:
        try:
            for item in collector.collect(_source_stub(detail_url))[:3]:
                previews.append(_preview(item))
        except Exception:
            continue
    confidence = 0.99 if previews else 0.90
    return AssistedSourceProposal(
        url=url,
        name=_site_name(url),
        crawl_mode="follow_internal",
        strategy="preset:promokood-category",
        confidence=confidence,
        explanation=(
            "Определён каталог Promokood. Парсер сам найдёт внутренние ссылки /o/, "
            "откроет их и разберёт встроенным шаблоном. Внешние кнопки «Активировать» для обхода игнорируются."
        ),
        # Known-site preset deliberately avoids page-specific card classes.
        # A global same-host /o/ anchor selector is substantially more stable.
        listing_item_selector=None,
        detail_link_selector='a[href*="/o/"]',
        detail_url_contains="/o/",
        sample_detail_url=detail_urls[0],
        previews=tuple(previews[:5]),
        discovered_detail_pages=len(detail_urls),
    )


def _direct_known_site_proposal(url: str, collector: GenericWebCollector) -> AssistedSourceProposal | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    known = (host == "promokood.ru" and parsed.path.casefold().startswith("/o/")) or (host == "promko.net" and "/shops/" in parsed.path.casefold())
    if not known:
        return None
    items = collector.collect(_source_stub(url))
    previews = tuple(_preview(item) for item in items[:5])
    return AssistedSourceProposal(
        url=url,
        name=_site_name(url),
        crawl_mode="direct",
        strategy=f"preset:{host}",
        confidence=0.99 if previews else 0.80,
        explanation="Для этого сайта уже есть встроенный проверенный шаблон. Ручная разметка не требуется.",
        previews=previews,
    )


def _candidate_containers(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[tuple[float, Tag]] = []
    for tag in soup.find_all(["article", "li", "div"]):
        text = " ".join(tag.stripped_strings).strip()
        if len(text) < 20 or len(text) > 1800:
            continue
        score = 0.0
        if tag.name in {"article", "li"}:
            score += 2.0
        if _PROMO_HINT_RE.search(text):
            score += 3.0
        if tag.find("a", href=True):
            score += 1.0
        if tag.find("img"):
            score += 0.5
        classes = " ".join(_stable_classes(tag)).casefold()
        if any(word in classes for word in ("offer", "promo", "coupon", "sale", "deal", "action")):
            score += 2.0
        if score >= 3.0:
            candidates.append((score, tag))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [tag for _, tag in candidates[:30]]


def _infer_direct_profile(url: str, html_text: str) -> tuple[ManualProfile | None, tuple[AutoPreviewItem, ...], float]:
    soup = _clean_soup(html_text)
    containers = _candidate_containers(soup)
    for sample in containers:
        item_selector = _selector(sample)
        try:
            matching = soup.select(item_selector)
        except Exception:
            continue
        if len(matching) < 2:
            continue
        heading = sample.find(["h1", "h2", "h3", "h4", "strong", "b"])
        promo_node = None
        for node in sample.find_all(["code", "span", "div", "button"]):
            node_text = node.get_text(" ", strip=True)
            if node_text and re.search(r"[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9_-]{3,24}", node_text) and _PROMO_HINT_RE.search(" ".join(sample.stripped_strings)):
                promo_node = node
                break
        conditions_node = sample.find(["p", "div"], string=lambda value: bool(value and _PROMO_HINT_RE.search(str(value))))
        date_node = sample.find(["time", "span", "div"], string=lambda value: bool(value and _DATE_HINT_RE.search(str(value))))
        link_node = sample.find("a", href=True)
        image_node = sample.find("img")
        promo_attr = None
        if promo_node is not None:
            for attr in ("data-code", "data-coupon", "value"):
                if promo_node.get(attr):
                    promo_attr = attr
                    break
        image_attr = None
        if image_node is not None:
            for attr in ("src", "data-src", "data-original"):
                if image_node.get(attr):
                    image_attr = None if attr == "src" else attr
                    break
        profile = normalize_manual_profile(
            item_selector=item_selector,
            title_selector=_relative_selector(sample, heading),
            promo_code_selector=_relative_selector(sample, promo_node),
            promo_code_attribute=promo_attr,
            conditions_selector=_relative_selector(sample, conditions_node),
            valid_until_selector=_relative_selector(sample, date_node),
            link_selector=_relative_selector(sample, link_node),
            image_selector=_relative_selector(sample, image_node),
            image_attribute=image_attr,
        )
        try:
            preview_items = preview_manual_profile_html(html_text, page_url=url, profile=profile, limit=5)
        except Exception:
            continue
        useful = [item for item in preview_items if item.title or item.promo_code or item.conditions]
        if len(useful) < 2:
            continue
        # Do not auto-confirm a generic profile that only found headings/links.
        # At least one benefit-bearing field must be structurally identified.
        if not (profile.promo_code_selector or profile.conditions_selector):
            continue
        previews = tuple(
            AutoPreviewItem(
                title=item.title or "Предложение",
                promo_code=item.promo_code,
                valid_until=item.valid_until,
                url=item.link,
                excerpt=(item.conditions or item.title or "")[:260],
            )
            for item in useful[:5]
        )
        filled = sum(bool(value) for value in (profile.title_selector, profile.promo_code_selector, profile.conditions_selector, profile.valid_until_selector, profile.link_selector, profile.image_selector))
        confidence = min(0.94, 0.68 + 0.04 * filled + min(len(useful), 5) * 0.02)
        return profile, previews, confidence
    return None, (), 0.0


def analyze_assisted_source(value: str) -> AssistedSourceProposal:
    url = normalize_source_url(value)
    collector = GenericWebCollector()
    known = _direct_known_site_proposal(url, collector)
    if known is not None:
        return known
    response = collector._get(url, route="auto")
    final_url = str(response.url)
    soup = _clean_soup(response.text)
    preset = _promokood_category_proposal(final_url, soup, collector)
    if preset is not None:
        return preset

    profile, previews, confidence = _infer_direct_profile(final_url, response.text)
    if profile is not None:
        return AssistedSourceProposal(
            url=final_url,
            name=_site_name(final_url),
            crawl_mode="direct",
            strategy="automatic-structural-profile",
            confidence=confidence,
            explanation="Структура повторяющихся карточек и поля предложений определены автоматически по странице.",
            item_selector=profile.item_selector,
            title_selector=profile.title_selector,
            promo_code_selector=profile.promo_code_selector,
            promo_code_attribute=profile.promo_code_attribute,
            conditions_selector=profile.conditions_selector,
            valid_until_selector=profile.valid_until_selector,
            link_selector=profile.link_selector,
            image_selector=profile.image_selector,
            image_attribute=profile.image_attribute,
            previews=previews,
        )

    pairs = _same_host_detail_links(soup, final_url)
    likely = [href for href, _ in pairs if _PROMO_HINT_RE.search(href)]
    marker = _common_path_marker(likely)
    return AssistedSourceProposal(
        url=final_url,
        name=_site_name(final_url),
        crawl_mode="direct",
        strategy="needs-developer-profile",
        confidence=0.35,
        explanation=(
            "Парсер не смог достаточно уверенно определить структуру автоматически. "
            "Источник не будет сохранён с сомнительной схемой; ручную техническую настройку можно выполнить в режиме специалиста."
        ),
        detail_url_contains=marker,
    )
