from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.adapters.common import external_id, parse_percent
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_SUMMARY_RE = re.compile(r"^(.+?)\s*до\s*(\d{1,3})\s*%$", re.IGNORECASE)


class PromkoAdapter:
    key = "promko"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            text = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            match = _SUMMARY_RE.match(text)
            if not match:
                continue
            merchant = match.group(1).strip(" :-—")
            percent = parse_percent(text)
            if not merchant or percent is None:
                continue
            source_url = urljoin(self.base_url, anchor.get("href"))
            ext_id = external_id(source_url, merchant, str(percent))
            if ext_id in seen:
                continue
            seen.add(ext_id)
            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=ext_id,
                    title=f"Скидка до {int(percent)}% в {merchant}",
                    source_url=source_url,
                    merchant=merchant,
                    description=text,
                    discount_percent=percent,
                    raw_payload={"text": text, "summary": True},
                )
            )
        return offers
