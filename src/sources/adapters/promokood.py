from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.base import RawOffer
from src.sources.http import HttpClient

_PERCENT_RE = re.compile(r"(?:скидк\w*\s*)?(?:до\s*)?(\d{1,3})\s*%", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(?:скидк\w*\s*)?(\d[\d\s]{0,8})\s*(?:₽|руб(?:\.|лей)?)", re.IGNORECASE)
_OFFER_WORD_RE = re.compile(r"скидк|промокод|кэшб|кешб|бонус", re.IGNORECASE)


class PromokoodAdapter:
    key = "promokood"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()

        for action in soup.find_all(["a", "button"]):
            action_text = action.get_text(" ", strip=True)
            if not action_text or not _OFFER_WORD_RE.search(action_text):
                continue
            card = self._find_card(action)
            card_text = " ".join(card.stripped_strings)
            if len(card_text) < 8:
                continue

            href = action.get("href") if isinstance(action, Tag) else None
            source_url = urljoin(self.base_url, href) if href else self.base_url
            merchant = self._merchant(card, action_text)
            title = self._title(card_text, merchant)
            external_id = hashlib.sha256(f"{source_url}|{merchant}|{title}".encode("utf-8")).hexdigest()[:32]
            if external_id in seen:
                continue
            seen.add(external_id)

            discount_percent = self._discount_percent(card_text)
            discount_amount = self._discount_amount(card_text) if discount_percent is None else None
            image_url = self._image_url(card)

            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    merchant=merchant,
                    description=card_text[:2000],
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    image_url=image_url,
                    raw_payload={"text": card_text},
                )
            )
        return offers

    def _find_card(self, action: Tag) -> Tag:
        for parent in action.parents:
            if not isinstance(parent, Tag):
                continue
            if parent.name in {"article", "li"}:
                return parent
            if parent.name == "div" and len(" ".join(parent.stripped_strings)) <= 800:
                return parent
        return action

    def _merchant(self, card: Tag, action_text: str) -> str | None:
        for selector in ("h2", "h3", "h4", "strong", "b"):
            node = card.find(selector)
            if node:
                value = node.get_text(" ", strip=True)
                if value and value != action_text and len(value) <= 120:
                    return value
        parts = [x.strip() for x in card.stripped_strings if x.strip() and x.strip() != action_text]
        return parts[0][:120] if parts else None

    def _title(self, card_text: str, merchant: str | None) -> str:
        text = re.sub(r"\s+", " ", card_text).strip()
        if merchant and text.lower().startswith(merchant.lower()):
            text = text[len(merchant):].strip(" :-—")
        return text[:300] or merchant or "Предложение"

    def _discount_percent(self, text: str) -> Decimal | None:
        match = _PERCENT_RE.search(text)
        if not match:
            return None
        value = int(match.group(1))
        return Decimal(value) if 0 < value <= 100 else None

    def _discount_amount(self, text: str) -> Decimal | None:
        match = _AMOUNT_RE.search(text)
        if not match:
            return None
        return Decimal(match.group(1).replace(" ", ""))

    def _image_url(self, card: Tag) -> str | None:
        image = card.find("img")
        if not image:
            return None
        src = image.get("src") or image.get("data-src")
        return urljoin(self.base_url, src) if src else None
