from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.core.validity import extract_valid_until
from src.modules.source_registry.collectors import CollectorError


_NTH_RE = re.compile(r":nth-(?:child|of-type)\(\s*\d+\s*\)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(?:скидк\w*\s*)?(?:до\s*)?[−–-]?\s*(\d{1,2}(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{2,7})(?:[.,]\d{1,2})?\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ManualProfile:
    item_selector: str
    title_selector: str | None = None
    promo_code_selector: str | None = None
    promo_code_attribute: str | None = None
    conditions_selector: str | None = None
    valid_until_selector: str | None = None
    link_selector: str | None = None
    image_selector: str | None = None
    image_attribute: str | None = None


@dataclass(frozen=True, slots=True)
class ManualPreviewItem:
    title: str | None
    promo_code: str | None
    conditions: str | None
    valid_until: str | None
    link: str | None
    image_url: str | None
    discount_percent: str | None
    amount_hint: str | None


def generalize_container_selector(selector: str) -> str:
    """Turn Chrome's selector for one sample card into a reusable card selector.

    DevTools often adds ``:nth-child(N)`` to the final path segment. Removing
    only the positional suffixes from that final segment keeps the surrounding
    page context while allowing the selector to match sibling offer cards.
    """
    raw = (selector or "").strip()
    if not raw:
        raise ValueError("Укажите селектор карточки предложения.")
    parts = [part.strip() for part in raw.split(">")]
    if not parts:
        raise ValueError("Укажите селектор карточки предложения.")
    parts[-1] = _NTH_RE.sub("", parts[-1]).strip()
    normalized = " > ".join(part for part in parts if part)
    return normalized or raw


def relative_field_selector(sample_container_selector: str, field_selector: str | None) -> str | None:
    """Convert a copied full-page field selector to a selector inside the card."""
    field = (field_selector or "").strip()
    if not field:
        return None
    sample = (sample_container_selector or "").strip()
    generalized = generalize_container_selector(sample)
    for prefix in (sample, generalized):
        if field == prefix:
            return ":scope"
        if field.startswith(prefix + " >"):
            tail = field[len(prefix) :].lstrip().lstrip(">").strip()
            return tail or ":scope"
    return field


def normalize_manual_profile(
    *,
    item_selector: str,
    title_selector: str | None = None,
    promo_code_selector: str | None = None,
    promo_code_attribute: str | None = None,
    conditions_selector: str | None = None,
    valid_until_selector: str | None = None,
    link_selector: str | None = None,
    image_selector: str | None = None,
    image_attribute: str | None = None,
) -> ManualProfile:
    sample = (item_selector or "").strip()
    normalized_item = generalize_container_selector(sample)
    return ManualProfile(
        item_selector=normalized_item,
        title_selector=relative_field_selector(sample, title_selector),
        promo_code_selector=relative_field_selector(sample, promo_code_selector),
        promo_code_attribute=(promo_code_attribute or "").strip() or None,
        conditions_selector=relative_field_selector(sample, conditions_selector),
        valid_until_selector=relative_field_selector(sample, valid_until_selector),
        link_selector=relative_field_selector(sample, link_selector),
        image_selector=relative_field_selector(sample, image_selector),
        image_attribute=(image_attribute or "").strip() or None,
    )


def _node(container, selector: str | None):
    if not selector:
        return None
    if selector == ":scope":
        return container
    return container.select_one(selector)


def _text(container, selector: str | None, attribute: str | None = None) -> str | None:
    target = _node(container, selector)
    if target is None:
        return None
    value = target.get(attribute) if attribute else target.get_text(" ", strip=True)
    value = str(value or "").strip()
    return value or None


def _image(container, selector: str | None, attribute: str | None, page_url: str) -> str | None:
    target = _node(container, selector)
    if target is None:
        return None
    candidates = [attribute] if attribute else ["src", "data-src", "data-lazy-src", "data-original", "content"]
    for name in candidates:
        if not name:
            continue
        value = str(target.get(name) or "").strip()
        if value and not value.startswith(("data:", "blob:")):
            return urljoin(page_url, value)
    return None


def preview_manual_profile_html(
    html_text: str,
    *,
    page_url: str,
    profile: ManualProfile,
    limit: int = 5,
) -> list[ManualPreviewItem]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    try:
        containers = soup.select(profile.item_selector)
    except Exception as exc:
        raise CollectorError(f"Некорректный селектор карточки: {exc}") from exc
    if not containers:
        raise CollectorError("По селектору карточки не найдено ни одного предложения.")

    result: list[ManualPreviewItem] = []
    for container in containers[: max(1, limit)]:
        try:
            title = _text(container, profile.title_selector)
            promo = _text(container, profile.promo_code_selector, profile.promo_code_attribute)
            conditions = _text(container, profile.conditions_selector)
            validity_text = _text(container, profile.valid_until_selector)
            link_raw = _text(container, profile.link_selector, "href")
            link = urljoin(page_url, link_raw) if link_raw else None
            image_url = _image(container, profile.image_selector, profile.image_attribute, page_url)
        except Exception as exc:
            raise CollectorError(f"Не удалось применить селектор поля: {exc}") from exc

        fallback_text = " ".join(container.stripped_strings)
        combined = " ".join(part for part in (title, conditions, fallback_text) if part)
        percent_match = _PERCENT_RE.search(combined)
        amount_match = _AMOUNT_RE.search(combined)
        valid_until = extract_valid_until(validity_text or combined)
        result.append(
            ManualPreviewItem(
                title=title,
                promo_code=promo,
                conditions=conditions,
                valid_until=valid_until.date().isoformat() if valid_until else None,
                link=link,
                image_url=image_url,
                discount_percent=percent_match.group(1).replace(",", ".") if percent_match else None,
                amount_hint=amount_match.group(0) if amount_match else None,
            )
        )
    return result
