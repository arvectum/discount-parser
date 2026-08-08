from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from src.sources.adapters.common import closest_card, compact_text, external_id, image_url, parse_amount, parse_percent, parse_valid_until
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_ACTION_RE = re.compile(r"показать\s+(?:промокод|акци)", re.IGNORECASE)
_BENEFIT_RE = re.compile(r"скид|бонус|кешб|кэшб|бесплат", re.IGNORECASE)


class PromokodikAdapter:
    key = "promokodik"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        for action in soup.find_all("a"):
            action_text = action.get_text(" ", strip=True)
            href = action.get("href")
            if not _ACTION_RE.search(action_text) and not (href and "offer_id=" in href):
                continue
            card = closest_card(action, marker="срок действия")
            text = compact_text(card)
            title = self._title(card, text, action_text)
            if not title or not _BENEFIT_RE.search(title):
                continue
            source_url = urljoin(self.base_url, href) if href else self.base_url
            offer_id = parse_qs(urlsplit(source_url).query).get("offer_id", [None])[0]
            ext_id = offer_id or external_id(source_url, title)
            if ext_id in seen:
                continue
            seen.add(ext_id)
            percent = parse_percent(title)
            amount = None if percent is not None else parse_amount(title)
            cashback_percent = percent if re.search(r"кешб|кэшб", title, re.IGNORECASE) else None
            if cashback_percent is not None:
                percent = None
            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=ext_id,
                    title=title,
                    source_url=source_url,
                    merchant=self._merchant(card),
                    description=text[:2000],
                    discount_percent=percent,
                    discount_amount=amount,
                    cashback_percent=cashback_percent,
                    image_url=image_url(card, self.base_url),
                    valid_until=parse_valid_until(text),
                    raw_payload={"text": text},
                )
            )
        return offers

    def _title(self, card: Tag, text: str, action_text: str) -> str | None:
        for heading in card.find_all(["h2", "h3", "h4", "strong"]):
            value = heading.get_text(" ", strip=True)
            if _BENEFIT_RE.search(value):
                return value[:300]
        cleaned = text.replace(action_text, " ")
        cleaned = re.split(r"Срок действия", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        candidates = [part.strip(" :-—") for part in re.split(r"[\n|]", cleaned) if part.strip()]
        for value in candidates:
            if _BENEFIT_RE.search(value):
                return re.sub(r"\s+", " ", value)[:300]
        match = re.search(r"([^.!?]{0,220}(?:скид\w*|бонус|кешб\w*|кэшб\w*|бесплат\w*)[^.!?]{0,120})", cleaned, re.IGNORECASE)
        return re.sub(r"\s+", " ", match.group(1)).strip()[:300] if match else None

    def _merchant(self, card: Tag) -> str | None:
        image = card.find("img", alt=True)
        if image:
            alt = image.get("alt", "").strip()
            if alt and len(alt) <= 120:
                return alt
        return None
