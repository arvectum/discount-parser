from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

from src.core.validity import extract_valid_until
from src.modules.source_registry.collectors import (
    CollectorError,
    GenericWebCollector,
    TelegramPublicCollector,
    normalize_telegram_channel,
)
from src.modules.source_registry.service import ItemPayload


class AutoSourceSetupError(RuntimeError):
    """A customer-readable source auto-setup failure."""


@dataclass(frozen=True, slots=True)
class AutoPreviewItem:
    title: str
    promo_code: str | None
    valid_until: str | None
    url: str | None
    excerpt: str


@dataclass(frozen=True, slots=True)
class AutoSourceAnalysis:
    url: str
    name: str
    platform: str
    source_type: str
    collector_type: str
    external_id: str | None
    items: tuple[AutoPreviewItem, ...]
    fetched: int
    confidence: float
    promo_codes_found: int
    dates_found: int
    strategy: str

    @property
    def can_add(self) -> bool:
        return self.fetched > 0


_PROMO_RE = re.compile(
    r"(?i:(?:промокод|promo\s*code|coupon\s*code|код\s+на\s+скидку|код))"
    r"\s*(?:[:=\-–—]|это)?\s*[«\"']?([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{2,31})"
)
_PROMO_STOPWORDS = {
    "действует", "действителен", "скидку", "получить", "показать", "ввести",
    "применить", "можно", "дает", "даёт", "для", "при", "на",
}


def normalize_source_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise AutoSourceSetupError("Вставьте ссылку на источник.")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AutoSourceSetupError("Нужна обычная ссылка на сайт или публичный Telegram-канал.")
    return raw


def _site_name(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    if not host:
        return "Новый источник"
    label = host.split(".")[0].replace("-", " ").replace("_", " ").strip()
    return label[:1].upper() + label[1:] if label else host


def _promo_code(item: ItemPayload) -> str | None:
    raw = item.raw_payload or {}
    stored = str(raw.get("promo_code") or "").strip()
    if stored:
        return stored[:64]
    text = " ".join(part for part in (item.title, item.text) if part)
    for match in _PROMO_RE.finditer(text):
        candidate = match.group(1).strip("«»\"'.,;:()[]{}")
        if candidate.casefold() in _PROMO_STOPWORDS:
            continue
        return candidate[:64]
    return None


def _valid_until(item: ItemPayload) -> str | None:
    raw = item.raw_payload or {}
    stored = str(raw.get("valid_until") or "").strip()
    if stored:
        return stored
    parsed = extract_valid_until(item.text or item.title or "")
    return parsed.date().isoformat() if parsed else None


def _preview(item: ItemPayload) -> AutoPreviewItem:
    text = " ".join((item.text or "").split())
    title = " ".join((item.title or "").split()) or text[:120] or "Предложение"
    return AutoPreviewItem(
        title=title[:180],
        promo_code=_promo_code(item),
        valid_until=_valid_until(item),
        url=item.url,
        excerpt=text[:260],
    )


def _confidence(items: list[ItemPayload], previews: tuple[AutoPreviewItem, ...]) -> float:
    if not items:
        return 0.0
    if any((item.raw_payload or {}).get("collector") == "known_site_adapter" for item in items):
        return 0.98
    with_promo = sum(1 for item in previews if item.promo_code)
    with_title = sum(1 for item in previews if item.title and item.title != "Предложение")
    if len(items) >= 3 and with_promo:
        return 0.9
    if len(items) >= 3 and with_title >= 2:
        return 0.82
    if len(items) >= 1 and with_title:
        return 0.68
    return 0.5


def _generic_stub(url: str):
    return SimpleNamespace(
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


def analyze_source_url(value: str) -> AutoSourceAnalysis:
    """Inspect a source from one pasted URL and produce a customer-facing preview.

    No CSS selectors, HTML attributes, collector names or platform details are
    required from the user. The existing collector engine remains the internal
    implementation detail.
    """
    url = normalize_source_url(value)
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")

    try:
        if host in {"t.me", "telegram.me"}:
            channel = normalize_telegram_channel(url)
            source = SimpleNamespace(url=url, external_id=channel, network_policy="auto")
            items = TelegramPublicCollector().collect(source)
            platform = "telegram"
            source_type = "social_channel"
            collector_type = "telegram_public"
            external_id = channel
            name = f"Telegram @{channel}"
            strategy = "telegram_public"
        else:
            items = GenericWebCollector().collect(_generic_stub(url))
            platform = "website"
            source_type = "promotion_page"
            collector_type = "generic_web"
            external_id = None
            name = _site_name(url)
            strategy = (
                "known_site_adapter"
                if any((item.raw_payload or {}).get("collector") == "known_site_adapter" for item in items)
                else "automatic_web"
            )
    except CollectorError as exc:
        raise AutoSourceSetupError(str(exc)) from exc
    except Exception as exc:
        raise AutoSourceSetupError(f"Не удалось проверить источник: {type(exc).__name__}: {exc}") from exc

    previews = tuple(_preview(item) for item in items[:5])
    promo_codes_found = sum(1 for item in previews if item.promo_code)
    dates_found = sum(1 for item in previews if item.valid_until)
    return AutoSourceAnalysis(
        url=url,
        name=name,
        platform=platform,
        source_type=source_type,
        collector_type=collector_type,
        external_id=external_id,
        items=previews,
        fetched=len(items),
        confidence=_confidence(items, previews),
        promo_codes_found=promo_codes_found,
        dates_found=dates_found,
        strategy=strategy,
    )
