from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import Tag

_PERCENT_RE = re.compile(r"(?:до\s*)?[-−]?\s*(\d{1,3})\s*%", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"[-−]?\s*(\d[\d\s]{0,8})\s*(?:₽|руб(?:\.|лей)?)", re.IGNORECASE)
_DATE_RE = re.compile(r"(?:до\s*)?(\d{2})\.(\d{2})\.(\d{4})")


def compact_text(node: Tag) -> str:
    return re.sub(r"\s+", " ", " ".join(node.stripped_strings)).strip()


def closest_card(node: Tag, *, marker: str | None = None, max_chars: int = 1600) -> Tag:
    fallback = node
    for parent in node.parents:
        if not isinstance(parent, Tag):
            continue
        text = compact_text(parent)
        if len(text) > max_chars:
            continue
        fallback = parent
        if parent.name in {"article", "li"}:
            return parent
        if marker and marker.lower() in text.lower() and len(text) >= 20:
            return parent
    return fallback


def parse_percent(text: str) -> Decimal | None:
    match = _PERCENT_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    return Decimal(value) if 0 < value <= 100 else None


def parse_amount(text: str) -> Decimal | None:
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    return Decimal(match.group(1).replace(" ", ""))


def parse_valid_until(text: str) -> datetime | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=UTC)
    except ValueError:
        return None


def image_url(card: Tag, base_url: str) -> str | None:
    image = card.find("img")
    if not image:
        return None
    src = image.get("src") or image.get("data-src") or image.get("data-lazy-src")
    return urljoin(base_url, src) if src else None


def external_id(*parts: str | None) -> str:
    payload = "|".join(part or "" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
