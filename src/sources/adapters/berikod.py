from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.adapters.common import closest_card, compact_text, external_id, image_url, parse_amount, parse_percent
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_TITLE_RE = re.compile(r"скид|промокод|дешевле|подар|бонус", re.IGNORECASE)
_CODE_RE = re.compile(r"\b(?=[A-ZА-Я0-9_-]{4,24}\b)(?=[A-ZА-Я0-9_-]*\d|[A-ZА-Я0-9_-]{5,})([A-ZА-Я0-9_-]+)\b")
_STOP_CODES = {"IMAGE", "КОД", "ПРОМОКОД", "ПРОМОКОДЫ"}


class BerikodAdapter:
    key = "berikod"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = heading.get_text(" ", strip=True)
            if not _TITLE_RE.search(title):
                continue
            card = closest_card(heading, max_chars=1800)
            text = compact_text(card)
            if len(text) < len(title):
                text = title
            promo_code = self._promo_code(text, title)
            anchor = heading.find_parent("a") or card.find("a", href=True)
            href = anchor.get("href") if isinstance(anchor, Tag) else None
            source_url = urljoin(self.base_url, href) if href else self.base_url
            ext_id = external_id(source_url, title, promo_code)
            if ext_id in seen:
                continue
            seen.add(ext_id)
            percent = parse_percent(title)
            amount = None if percent is not None else parse_amount(title)
            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=ext_id,
                    title=title[:300],
                    source_url=source_url,
                    merchant=self._merchant(title),
                    description=text[:2000],
                    promo_code=promo_code,
                    discount_percent=percent,
                    discount_amount=amount,
                    image_url=image_url(card, self.base_url),
                    raw_payload={"text": text},
                )
            )
        return offers

    def _promo_code(self, text: str, title: str) -> str | None:
        tail = text[len(title):]
        for match in _CODE_RE.finditer(tail):
            value = match.group(1)
            if value.upper() not in _STOP_CODES:
                return value
        return None

    def _merchant(self, title: str) -> str | None:
        patterns = [
            r"\b(?:от|для|в)\s+([A-Za-zА-Яа-я0-9. -]{2,40}?)(?:\s+на\s+|\s+по\s+|\s+-?\d|$)",
            r"^Промокод\s+([A-Za-zА-Яа-я0-9. -]{2,40}?)\s+(?:июл|август|сент|на)",
        ]
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip(" .-—")[:120]
        return None
