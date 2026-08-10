from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.modules.source_registry.service import upsert_candidate
from sqlalchemy.orm import Session

PROMOTION_PATH_HINTS = (
    "promo",
    "promotions",
    "action",
    "actions",
    "sale",
    "sales",
    "discount",
    "discounts",
    "special",
    "offers",
    "акци",
    "скид",
    "распрод",
)


def discover_merchant_pages(
    session: Session,
    *,
    merchant: str,
    homepage_url: str,
    timeout_seconds: float = 15.0,
    max_candidates: int = 25,
) -> int:
    """Discover likely promotion pages from one known merchant homepage.

    This is deliberately depth-1 and same-domain only; it is not a general web crawler.
    """
    parsed_home = urlparse(homepage_url)
    if parsed_home.scheme not in {"http", "https"} or not parsed_home.netloc:
        raise ValueError("homepage_url must be an absolute http(s) URL")

    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": "DiscountParser/1.0 (+local source discovery)"},
    ) as client:
        response = client.get(homepage_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    seen: set[str] = set()
    created_or_seen = 0
    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(str(response.url), href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != urlparse(str(response.url)).netloc:
            continue
        canonical = parsed._replace(fragment="").geturl()
        haystack = f"{parsed.path} {' '.join(link.stripped_strings)}".casefold()
        if not any(hint in haystack for hint in PROMOTION_PATH_HINTS):
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        label = " ".join(link.stripped_strings).strip()[:255] or None
        upsert_candidate(
            session,
            platform="website",
            url=canonical,
            name=label,
            merchant=merchant,
            discovered_by="merchant_homepage",
            discovery_query=homepage_url,
            confidence=0.75,
            metadata={"homepage": homepage_url},
        )
        created_or_seen += 1
        if created_or_seen >= max_candidates:
            break
    return created_or_seen
