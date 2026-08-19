from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


_PROMOKOOD_PATH_RE = re.compile(r"(?i)(?:https?://(?:www\.)?promokood\.ru)?(/o/[a-z0-9_-]+)")
_ESCAPED_PROMOKOOD_PATH_RE = re.compile(r"(?i)\\/o\\/[a-z0-9_-]+")


def discover_promokood_detail_urls(html_text: str, *, entry_url: str, limit: int = 500) -> list[str]:
    """Find internal Promokood /o/... detail pages without relying on one DOM shape.

    The live category UI may expose "Все промокоды" as a normal anchor, a
    button/data attribute, or a JS/JSON-backed navigation target. We therefore
    inspect both element attributes and the raw HTML while enforcing same-host
    /o/ destinations. External activation/advertiser URLs are never returned.
    """
    entry = urlparse(entry_url)
    host = (entry.hostname or "").casefold().removeprefix("www.")
    if host != "promokood.ru":
        return []

    candidates: list[str] = []
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(True):
        for raw_value in tag.attrs.values():
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                text = html_lib.unescape(str(value or "")).replace("\\/", "/")
                for match in _PROMOKOOD_PATH_RE.finditer(text):
                    candidates.append(urljoin(entry_url, match.group(1)))

    raw = html_lib.unescape(html_text).replace("\\/", "/")
    for match in _PROMOKOOD_PATH_RE.finditer(raw):
        candidates.append(urljoin(entry_url, match.group(1)))
    for escaped in _ESCAPED_PROMOKOOD_PATH_RE.findall(html_text):
        normalized = escaped.replace("\\/", "/")
        candidates.append(urljoin(entry_url, normalized))

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        parsed = urlparse(candidate)
        target_host = (parsed.hostname or "").casefold().removeprefix("www.")
        if target_host != host or not parsed.path.casefold().startswith("/o/"):
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= max(1, min(int(limit or 500), 500)):
            break
    return result
