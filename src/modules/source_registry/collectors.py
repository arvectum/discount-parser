from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import ItemPayload
from src.shared.config import get_settings


class CollectorError(RuntimeError):
    pass


class CredentialsRequired(CollectorError):
    pass


class SourceCollector(Protocol):
    def collect(self, source: RegisteredSource) -> list[ItemPayload]: ...


@dataclass(frozen=True, slots=True)
class HttpPolicy:
    timeout_seconds: float = 20.0
    max_items: int = 100
    max_response_bytes: int = 5_000_000
    user_agent: str = "DiscountParser/1.0 (+local source monitor)"


class HttpCollectorBase:
    policy = HttpPolicy()

    def _get(self, url: str) -> httpx.Response:
        with httpx.Client(
            follow_redirects=True,
            timeout=self.policy.timeout_seconds,
            headers={"User-Agent": self.policy.user_agent, "Accept-Language": "ru,en;q=0.8"},
        ) as client:
            response = client.get(url)
        response.raise_for_status()
        if len(response.content) > self.policy.max_response_bytes:
            raise CollectorError(f"response too large: {len(response.content)} bytes")
        return response


class GenericWebCollector(HttpCollectorBase):
    """Conservative collector for a known merchant/promotion page.

    It does not crawl the internet. It extracts bounded semantic blocks from the
    single registered URL. Same-domain promotion discovery is handled separately.
    """

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        response = self._get(source.url)
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        candidates = soup.select("article, main section, [class*=promo], [class*=sale], [class*=action], [class*=offer]")
        if not candidates:
            candidates = [soup.body or soup]

        seen: set[str] = set()
        result: list[ItemPayload] = []
        for element in candidates:
            text = " ".join(element.stripped_strings)
            if len(text) < 20:
                continue
            text = text[:12000]
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            link = element.find("a", href=True)
            item_url = urljoin(str(response.url), link["href"]) if link else str(response.url)
            heading = element.find(["h1", "h2", "h3", "h4"])
            title = " ".join(heading.stripped_strings)[:1000] if heading else None
            image = element.find("img", src=True)
            image_url = urljoin(str(response.url), image["src"]) if image else None
            result.append(
                ItemPayload(
                    external_id=digest,
                    url=item_url,
                    title=title,
                    text=text,
                    image_url=image_url,
                    raw_payload={"collector": "generic_web"},
                )
            )
            if len(result) >= self.policy.max_items:
                break
        return result


class PublicPageCollector(GenericWebCollector):
    """Metadata/text fallback for a known public Dzen/other page."""


class TelegramPublicCollector(HttpCollectorBase):
    """Collect public preview posts from a known t.me channel without user auth.

    This is intentionally a public-preview collector, not an MTProto replacement.
    Private channels and channels unavailable through /s require a separate
    authenticated collector.
    """

    _MESSAGE_RE = re.compile(r"data-post=[\"']([^\"']+)[\"']")

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        parsed = urlparse(source.url)
        channel = source.external_id
        if not channel:
            path = parsed.path.strip("/")
            if path.startswith("s/"):
                path = path[2:]
            channel = path.split("/")[0]
        if not channel:
            raise CollectorError("Telegram source requires channel username/external_id")
        url = f"https://t.me/s/{channel.lstrip('@')}"
        response = self._get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        result: list[ItemPayload] = []
        for wrapper in soup.select(".tgme_widget_message_wrap"):
            message = wrapper.select_one(".tgme_widget_message")
            if message is None:
                continue
            post_id = message.get("data-post")
            text_node = wrapper.select_one(".tgme_widget_message_text")
            text = " ".join(text_node.stripped_strings) if text_node else ""
            if not text:
                continue
            date_link = wrapper.select_one("a.tgme_widget_message_date")
            item_url = date_link.get("href") if date_link else source.url
            time_node = wrapper.select_one("time")
            published_at = None
            if time_node and time_node.get("datetime"):
                try:
                    published_at = datetime.fromisoformat(time_node["datetime"].replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
            image_node = wrapper.select_one("a.tgme_widget_message_photo_wrap")
            image_url = None
            if image_node:
                style = image_node.get("style", "")
                match = re.search(r"background-image:url\(['\"]?([^'\")]+)", style)
                if match:
                    image_url = match.group(1)
            result.append(
                ItemPayload(
                    external_id=post_id,
                    url=item_url,
                    title=None,
                    text=text[:12000],
                    published_at=published_at,
                    author=channel,
                    image_url=image_url,
                    raw_payload={"collector": "telegram_public"},
                )
            )
            if len(result) >= self.policy.max_items:
                break
        return result


class VkApiCollector(HttpCollectorBase):
    API_URL = "https://api.vk.com/method/wall.get"

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        settings = get_settings()
        token = getattr(settings, "vk_access_token", None)
        if not token:
            raise CredentialsRequired("VK collector requires DP_VK_ACCESS_TOKEN")
        owner_id = source.external_id
        if not owner_id:
            raise CollectorError("VK source requires external_id (owner_id/domain)")
        params = {
            "access_token": token,
            "v": getattr(settings, "vk_api_version", "5.199"),
            "count": min(self.policy.max_items, 100),
        }
        if owner_id.lstrip("-").isdigit():
            params["owner_id"] = owner_id
        else:
            params["domain"] = owner_id.lstrip("@")
        with httpx.Client(timeout=self.policy.timeout_seconds) as client:
            response = client.get(self.API_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise CollectorError(f"VK API error {payload['error'].get('error_code')}: {payload['error'].get('error_msg')}")
        result: list[ItemPayload] = []
        for item in payload.get("response", {}).get("items", []):
            text = (item.get("text") or "").strip()
            if not text:
                continue
            post_id = str(item.get("id"))
            owner = str(item.get("owner_id", owner_id))
            published_at = datetime.fromtimestamp(item["date"], UTC) if item.get("date") else None
            result.append(
                ItemPayload(
                    external_id=post_id,
                    url=f"https://vk.com/wall{owner}_{post_id}",
                    title=None,
                    text=text[:12000],
                    published_at=published_at,
                    author=owner,
                    raw_payload={"collector": "vk_api", "post": item},
                )
            )
        return result


class RutubePublicCollector(HttpCollectorBase):
    """Collect public Rutube channel/video metadata from the registered page.

    Rutube's public page remains the compatibility fallback; live acceptance may
    replace this with a documented JSON endpoint when one is confirmed stable.
    """

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        response = self._get(source.url)
        soup = BeautifulSoup(response.text, "html.parser")
        result: list[ItemPayload] = []
        seen: set[str] = set()
        for link in soup.select("a[href*='/video/']"):
            href = link.get("href")
            if not href:
                continue
            url = urljoin(str(response.url), href)
            if url in seen:
                continue
            seen.add(url)
            title = " ".join(link.stripped_strings).strip() or link.get("title")
            if not title:
                continue
            external_id = url.rstrip("/").split("/")[-1]
            result.append(
                ItemPayload(
                    external_id=external_id,
                    url=url,
                    title=title[:1000],
                    text=title[:12000],
                    author=source.name,
                    raw_payload={"collector": "rutube_public"},
                )
            )
            if len(result) >= self.policy.max_items:
                break
        return result


COLLECTORS: dict[str, type[SourceCollector]] = {
    "generic_web": GenericWebCollector,
    "public_page": PublicPageCollector,
    "telegram_public": TelegramPublicCollector,
    "vk_api": VkApiCollector,
    "rutube_public": RutubePublicCollector,
}


def build_collector(collector_type: str) -> SourceCollector:
    try:
        collector_cls = COLLECTORS[collector_type]
    except KeyError as exc:
        raise KeyError(f"unknown source collector: {collector_type}") from exc
    return collector_cls()
