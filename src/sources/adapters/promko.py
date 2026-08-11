from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.adapters.common import compact_text, external_id, image_url, parse_percent, parse_valid_until
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_SUMMARY_RE = re.compile(r"^(.+?)\s*до\s*(\d{1,3})\s*%$", re.IGNORECASE)

class PromkoAdapter:
    """Parser for PROMKO merchant cards.

    ``data-coupon-id`` is an opaque server-side identifier, never a promo code.
    """

    key = "promko"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    @staticmethod
    def _coupon_id(card: Tag) -> str | None:
        node = card.find(attrs={"data-coupon-id": True})
        if node is None:
            return None
        value = str(node.get("data-coupon-id") or "").strip()
        return value if value.isdigit() else None

    @staticmethod
    def _card(node: Tag) -> Tag:
        for parent in node.parents:
            if isinstance(parent, Tag) and parent.name in {"article", "li"}:
                return parent
        return node.parent if isinstance(node.parent, Tag) else node

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        for node in soup.find_all(attrs={"data-coupon-id": True}):
            card = self._card(node)
            text = compact_text(card)
            if not text:
                continue
            coupon_id = self._coupon_id(card)
            explicit = str(node.get("data-promocode") or node.get("data-promo-code") or "").strip() or None
            title_node = card.find(["h1", "h2", "h3", "h4"])
            title = compact_text(title_node) if title_node else text[:300]
            href_node = card.find("a", href=True)
            source_url = urljoin(self.base_url, str(href_node.get("href"))) if href_node else self.base_url
            ext_id = f"promko-coupon:{coupon_id}" if coupon_id else external_id(source_url, title, text)
            if ext_id in seen:
                continue
            seen.add(ext_id)
            offers.append(RawOffer(
                source_key=self.key,
                external_id=ext_id,
                title=title,
                source_url=source_url,
                description=text[:2000],
                promo_code=explicit,
                discount_percent=parse_percent(text),
                image_url=image_url(card, self.base_url),
                valid_until=parse_valid_until(text),
                raw_payload={
                    "text": text,
                    "promko_coupon_id": coupon_id,
                    "needs_reveal": bool(coupon_id and not explicit),
                },
            ))
        if offers:
            return offers
        # The legacy PROMKO index is still a useful source and intentionally
        # remains compatible with the prior summary-card parser.
        for anchor in soup.find_all("a", href=True):
            text = compact_text(anchor)
            match = _SUMMARY_RE.match(text)
            if not match:
                continue
            merchant = match.group(1).strip(" :-—")
            percent = parse_percent(text)
            if not merchant or percent is None:
                continue
            source_url = urljoin(self.base_url, str(anchor.get("href")))
            ext_id = external_id(source_url, merchant, str(percent))
            if ext_id in seen:
                continue
            seen.add(ext_id)
            offers.append(RawOffer(source_key=self.key, external_id=ext_id,
                                   title=f"Скидка до {int(percent)}% в {merchant}", source_url=source_url,
                                   merchant=merchant, description=text, discount_percent=percent,
                                   raw_payload={"text": text, "summary": True,
                                                "promko_coupon_id": None, "needs_reveal": False}))
        return offers
