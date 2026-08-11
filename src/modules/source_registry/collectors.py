from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import ItemPayload
from src.core.validity import extract_valid_until
from src.shared.config import get_settings
from src.shared.network import network_router
from src.sources.adapters.promko import PromkoAdapter
from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.base import RawOffer


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

    def _get(self, url: str, *, route: str = "auto", retry_statuses: set[int] | None = None):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise CollectorError("collector URL must be an absolute http(s) URL")
        response = network_router.get(
            url,
            route=route,
            retry_statuses=retry_statuses,
            follow_redirects=True,
            timeout=self.policy.timeout_seconds,
            headers={"User-Agent": self.policy.user_agent, "Accept-Language": "ru,en;q=0.8"},
        )
        response.raise_for_status()
        if len(response.content) > self.policy.max_response_bytes:
            raise CollectorError(f"response too large: {len(response.content)} bytes")
        return response


class GenericWebCollector(HttpCollectorBase):
    """Conservative collector for a known merchant/promotion page."""

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        response = self._get(source.url, route=source.network_policy)
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        profile_items = self._profile_items(source, soup, str(response.url))
        if profile_items:
            return profile_items
        known_items = self._known_site_items(source, str(response.url), str(soup))
        if known_items:
            return known_items

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
            result.append(ItemPayload(external_id=digest, url=item_url, title=title, text=text, image_url=image_url, raw_payload={"collector": "generic_web", "network_policy": source.network_policy}))
            if len(result) >= self.policy.max_items:
                break
        return result

    @staticmethod
    def _raw_offer_payload(raw: RawOffer, *, adapter: str) -> ItemPayload:
        metadata = dict(raw.raw_payload or {})
        metadata.update({"collector": "known_site_adapter", "adapter": adapter, "promo_code": raw.promo_code,
                         "conditions": raw.conditions, "valid_until": raw.valid_until.isoformat() if raw.valid_until else None})
        return ItemPayload(raw.external_id, raw.source_url, raw.title, raw.description or raw.title, image_url=raw.image_url, raw_payload=metadata)

    def _known_site_items(self, source: RegisteredSource, page_url: str, html: str) -> list[ItemPayload]:
        parsed = urlparse(source.url); host = (parsed.hostname or "").casefold().removeprefix("www.")
        if host == "promko.net" and "/shops/" in parsed.path.casefold():
            return [self._raw_offer_payload(raw, adapter="promko") for raw in PromkoAdapter(page_url).parse(html)]
        if host == "promokood.ru" and parsed.path.casefold().startswith("/o/"):
            return [self._raw_offer_payload(raw, adapter="promokood") for raw in PromokoodAdapter(page_url).parse(html)]
        return []

    @staticmethod
    def _value(node, selector: str | None, attribute: str | None = None) -> str | None:
        if not selector:
            return None
        target = node.select_one(selector)
        if target is None:
            return None
        value = target.get(attribute) if attribute else target.get_text(" ", strip=True)
        value = str(value or "").strip()
        return value or None

    def _profile_items(self, source: RegisteredSource, soup: BeautifulSoup, page_url: str) -> list[ItemPayload]:
        if not source.item_selector:
            return []
        try:
            containers = soup.select(source.item_selector)
        except Exception as exc:
            raise CollectorError(f"invalid extraction CSS selector: {exc}") from exc
        result: list[ItemPayload] = []
        for container in containers[:self.policy.max_items]:
            text = " ".join(container.stripped_strings)[:12000]
            if not text:
                continue
            title = self._value(container, source.title_selector) or text[:1000]
            promo = self._value(container, source.promo_code_selector, source.promo_code_attribute)
            conditions = self._value(container, source.conditions_selector)
            validity_text = self._value(container, source.valid_until_selector)
            reveal = self._value(container, source.reveal_selector, source.reveal_code_attribute)
            is_promko_coupon = ((urlparse(source.url).hostname or "").casefold().removeprefix("www.") == "promko.net" and source.reveal_code_attribute and source.reveal_code_attribute.casefold() == "data-coupon-id" and reveal and reveal.isdigit())
            if not promo and reveal and not is_promko_coupon:
                promo = reveal
            link = self._value(container, source.link_selector, "href")
            item_url = urljoin(page_url, link) if link else page_url
            digest = hashlib.sha256(f"{item_url}|{title}|{text}".encode()).hexdigest()
            result.append(ItemPayload(digest, item_url, title, text, raw_payload={
                "collector": "css_profile", "promo_code": promo, "conditions": conditions,
                "promko_coupon_id": reveal if is_promko_coupon else None, "needs_reveal": bool(is_promko_coupon and not promo),
                "valid_until": (extract_valid_until(validity_text or text).isoformat() if extract_valid_until(validity_text or text) else None),
            }))
        return result


class PublicPageCollector(GenericWebCollector):
    """Metadata/text fallback for a known public page."""


class DzenPublicCollector(PublicPageCollector):
    """Compatibility collector for a known Dzen page."""


class TelegramPublicCollector(HttpCollectorBase):
    """Collect public preview posts from a known t.me channel without user auth."""

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
        # Telegram public pages may be blocked by geography/network policy. In
        # auto mode, 403/451 are useful signals to try the next available route.
        retry = {403, 451} if source.network_policy == "auto" else set()
        response = self._get(url, route=source.network_policy, retry_statuses=retry)
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
            result.append(ItemPayload(external_id=post_id, url=item_url, title=None, text=text[:12000], published_at=published_at, author=channel, image_url=image_url, raw_payload={"collector": "telegram_public", "network_policy": source.network_policy}))
            if len(result) >= self.policy.max_items:
                break
        return result


class VkApiCollector(HttpCollectorBase):
    API_URL = "https://api.vk.com/method/wall.get"

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        settings = get_settings()
        token = settings.vk_access_token
        if not token:
            raise CredentialsRequired("VK collector requires DP_VK_ACCESS_TOKEN")
        owner_id = source.external_id
        if not owner_id:
            raise CollectorError("VK source requires external_id (owner_id/domain)")
        params = {"access_token": token, "v": settings.vk_api_version, "count": min(self.policy.max_items, 100)}
        if owner_id.lstrip("-").isdigit():
            params["owner_id"] = owner_id
        else:
            params["domain"] = owner_id.lstrip("@")
        response = network_router.get(self.API_URL, route=source.network_policy, timeout=self.policy.timeout_seconds, params=params)
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
            result.append(ItemPayload(external_id=post_id, url=f"https://vk.com/wall{owner}_{post_id}", title=None, text=text[:12000], published_at=published_at, author=owner, raw_payload={"collector": "vk_api", "post": item, "network_policy": source.network_policy}))
        return result


class RutubePublicCollector(HttpCollectorBase):
    """Collect public Rutube channel/video metadata from the registered page."""

    def collect(self, source: RegisteredSource) -> list[ItemPayload]:
        response = self._get(source.url, route=source.network_policy)
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
            result.append(ItemPayload(external_id=external_id, url=url, title=title[:1000], text=title[:12000], author=source.name, raw_payload={"collector": "rutube_public", "network_policy": source.network_policy}))
            if len(result) >= self.policy.max_items:
                break
        return result


COLLECTORS: dict[str, type[SourceCollector]] = {
    "generic_web": GenericWebCollector,
    "public_page": PublicPageCollector,
    "dzen_public": DzenPublicCollector,
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
