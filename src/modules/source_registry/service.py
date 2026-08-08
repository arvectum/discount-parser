from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.modules.source_registry.models import (
    CANDIDATE_STATUSES,
    KEYWORD_KINDS,
    PLATFORMS,
    TRUST_LEVELS,
    RegisteredSource,
    SourceCandidate,
    SourceItem,
    SourceKeyword,
)


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_keyword(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9а-яё]+", "-", value.casefold(), flags=re.IGNORECASE).strip("-")
    return normalized or "source"


def create_source(
    session: Session,
    *,
    name: str,
    platform: str,
    url: str,
    collector_type: str,
    key: str | None = None,
    source_type: str = "other",
    external_id: str | None = None,
    merchant: str | None = None,
    brand: str | None = None,
    auth_profile: str | None = None,
    priority: int = 50,
    trust_level: str = "unknown",
    check_interval_minutes: int = 120,
    enabled: bool = True,
) -> RegisteredSource:
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    if trust_level not in TRUST_LEVELS:
        raise ValueError(f"Unsupported trust level: {trust_level}")
    if not name.strip() or not url.strip() or not collector_type.strip():
        raise ValueError("name, url and collector_type are required")
    if not 1 <= check_interval_minutes <= 10080:
        raise ValueError("check_interval_minutes must be between 1 and 10080")
    if not 0 <= priority <= 100:
        raise ValueError("priority must be between 0 and 100")

    base_key = _slug(key or name)
    candidate_key = base_key
    suffix = 2
    while session.scalar(select(RegisteredSource.id).where(RegisteredSource.key == candidate_key)) is not None:
        candidate_key = f"{base_key}-{suffix}"
        suffix += 1

    source = RegisteredSource(
        key=candidate_key,
        name=name.strip(),
        platform=platform,
        source_type=source_type.strip() or "other",
        url=url.strip(),
        external_id=external_id.strip() if external_id else None,
        merchant=merchant.strip() if merchant else None,
        brand=brand.strip() if brand else None,
        collector_type=collector_type.strip(),
        auth_profile=auth_profile.strip() if auth_profile else None,
        priority=priority,
        trust_level=trust_level,
        check_interval_minutes=check_interval_minutes,
        enabled=enabled,
        status="unknown" if enabled else "disabled",
    )
    session.add(source)
    session.flush()
    return source


def set_source_enabled(session: Session, source_id: int, enabled: bool) -> RegisteredSource:
    source = session.get(RegisteredSource, source_id)
    if source is None:
        raise KeyError(source_id)
    source.enabled = enabled
    source.status = "unknown" if enabled else "disabled"
    source.updated_at = _now()
    session.flush()
    return source


def add_keyword(
    session: Session,
    keyword: str,
    *,
    kind: str = "positive",
    priority: int = 50,
    merchant: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    enabled: bool = True,
) -> SourceKeyword:
    if kind not in KEYWORD_KINDS:
        raise ValueError(f"Unsupported keyword kind: {kind}")
    normalized = normalize_keyword(keyword)
    if not normalized:
        raise ValueError("keyword is required")
    row = SourceKeyword(
        keyword=keyword.strip(),
        normalized_keyword=normalized,
        kind=kind,
        priority=max(0, min(priority, 100)),
        merchant=merchant.strip() if merchant else None,
        category=category.strip() if category else None,
        subcategory=subcategory.strip() if subcategory else None,
        enabled=enabled,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("keyword already exists in this scope") from exc
    return row


def upsert_candidate(
    session: Session,
    *,
    platform: str,
    url: str,
    name: str | None = None,
    external_id: str | None = None,
    merchant: str | None = None,
    discovered_by: str = "manual",
    discovery_query: str | None = None,
    confidence: float = 0.0,
    metadata: dict | None = None,
) -> SourceCandidate:
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    normalized_url = url.strip()
    if not normalized_url:
        raise ValueError("candidate url is required")
    row = session.scalar(
        select(SourceCandidate).where(SourceCandidate.platform == platform, SourceCandidate.url == normalized_url)
    )
    if row is None:
        row = SourceCandidate(platform=platform, url=normalized_url)
        session.add(row)
    row.name = name.strip() if name else row.name
    row.external_id = external_id.strip() if external_id else row.external_id
    row.merchant = merchant.strip() if merchant else row.merchant
    row.discovered_by = discovered_by
    row.discovery_query = discovery_query
    row.confidence = max(0.0, min(float(confidence), 1.0))
    row.last_seen_at = _now()
    if metadata is not None:
        row.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    session.flush()
    return row


def review_candidate(
    session: Session,
    candidate_id: int,
    status: str,
    *,
    collector_type: str | None = None,
    trust_level: str = "unknown",
) -> RegisteredSource | None:
    allowed = set(CANDIDATE_STATUSES) - {"new"}
    if status not in allowed:
        raise ValueError(f"Unsupported review status: {status}")
    candidate = session.get(SourceCandidate, candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)
    if candidate.status == "approved" and status == "approved":
        existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == candidate.url))
        return existing
    candidate.status = status
    now = _now()
    if status == "approved":
        candidate.approved_at = now
        default_collectors = {
            "website": "generic_web",
            "promo_aggregator": "legacy_adapter",
            "telegram": "telegram_public",
            "vk": "vk_api",
            "dzen": "public_page",
            "rutube": "rutube_public",
            "other": "public_page",
        }
        existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == candidate.url))
        if existing is not None:
            return existing
        return create_source(
            session,
            name=candidate.name or candidate.merchant or candidate.url,
            platform=candidate.platform,
            url=candidate.url,
            external_id=candidate.external_id,
            merchant=candidate.merchant,
            collector_type=collector_type or default_collectors[candidate.platform],
            trust_level=trust_level,
        )
    if status == "rejected":
        candidate.rejected_at = now
    session.flush()
    return None


@dataclass(frozen=True, slots=True)
class ItemPayload:
    external_id: str | None
    url: str | None
    title: str | None
    text: str | None
    published_at: datetime | None = None
    author: str | None = None
    image_url: str | None = None
    raw_payload: dict | None = None


def item_content_hash(payload: ItemPayload) -> str:
    content = "\n".join(
        value or "" for value in (payload.external_id, payload.url, payload.title, payload.text, payload.author)
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def upsert_source_item(session: Session, source: RegisteredSource, payload: ItemPayload) -> tuple[SourceItem, bool]:
    content_hash = item_content_hash(payload)
    row: SourceItem | None = None
    if payload.external_id:
        row = session.scalar(
            select(SourceItem).where(
                SourceItem.registered_source_id == source.id,
                SourceItem.external_id == payload.external_id,
            )
        )
    if row is None:
        row = session.scalar(
            select(SourceItem).where(
                SourceItem.registered_source_id == source.id,
                SourceItem.content_hash == content_hash,
            )
        )
    created = row is None
    if row is None:
        row = SourceItem(registered_source_id=source.id, content_hash=content_hash)
        session.add(row)
    row.external_id = payload.external_id
    row.url = payload.url
    row.title = payload.title
    row.text = payload.text
    row.published_at = payload.published_at
    row.author = payload.author
    row.image_url = payload.image_url
    row.raw_payload_json = json.dumps(payload.raw_payload, ensure_ascii=False, sort_keys=True) if payload.raw_payload else None
    row.content_hash = content_hash
    row.last_seen_at = _now()
    session.flush()
    return row, created


DEFAULT_KEYWORDS: tuple[tuple[str, str, int], ...] = (
    ("промокод", "strong_positive", 100),
    ("промокоды", "strong_positive", 100),
    ("скидка", "strong_positive", 90),
    ("скидки", "strong_positive", 90),
    ("распродажа", "strong_positive", 90),
    ("кэшбэк", "strong_positive", 90),
    ("cashback", "strong_positive", 90),
    ("бесплатная доставка", "strong_positive", 90),
    ("акция", "positive", 70),
    ("акции", "positive", 70),
    ("sale", "positive", 65),
    ("спецпредложение", "positive", 70),
    ("специальное предложение", "positive", 70),
    ("уценка", "positive", 70),
    ("ликвидация", "positive", 70),
    ("финальная цена", "positive", 65),
    ("2 по цене 1", "strong_positive", 90),
    ("3 по цене 2", "strong_positive", 90),
    ("обзор", "negative", 50),
    ("распаковка", "negative", 50),
    ("история", "negative", 30),
    ("отзыв", "negative", 40),
)


def seed_default_keywords(session: Session) -> int:
    created = 0
    for keyword, kind, priority in DEFAULT_KEYWORDS:
        normalized = normalize_keyword(keyword)
        exists = session.scalar(
            select(SourceKeyword.id).where(
                SourceKeyword.normalized_keyword == normalized,
                SourceKeyword.kind == kind,
                SourceKeyword.merchant.is_(None),
            )
        )
        if exists is None:
            session.add(
                SourceKeyword(
                    keyword=keyword,
                    normalized_keyword=normalized,
                    kind=kind,
                    priority=priority,
                    enabled=True,
                )
            )
            created += 1
    session.flush()
    return created


_PERCENT_RE = re.compile(r"(?:скидк\w*\s*)?(?:до\s*)?[−–-]?\s*(\d{1,2}(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_PROMO_RE = re.compile(r"(?:промокод|promo(?:\s*code)?|код)\s*[:\-–—]?\s*([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9_-]{3,24})", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{3,7})(?:[.,]\d{1,2})?\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class OfferSignal:
    is_offer: bool
    confidence: int
    offer_type: str
    matched_keywords: tuple[str, ...]
    promo_code: str | None = None
    discount_percent: Decimal | None = None
    old_price: Decimal | None = None
    new_price: Decimal | None = None


def detect_offer_signal(text: str, keywords: Iterable[SourceKeyword] = ()) -> OfferSignal:
    normalized_text = normalize_keyword(text)
    score = 0
    matched: list[str] = []
    negative = 0

    rows = list(keywords)
    if not rows:
        rows = [
            SourceKeyword(
                keyword=k,
                normalized_keyword=normalize_keyword(k),
                kind=kind,
                priority=priority,
                enabled=True,
            )
            for k, kind, priority in DEFAULT_KEYWORDS
        ]
    for row in rows:
        if not row.enabled or row.normalized_keyword not in normalized_text:
            continue
        matched.append(row.keyword)
        if row.kind == "strong_positive":
            score += 4
        elif row.kind in {"positive", "merchant", "custom"}:
            score += 2
        elif row.kind == "negative":
            negative += 2

    promo_match = _PROMO_RE.search(text)
    promo_code = promo_match.group(1).upper() if promo_match else None
    if promo_code:
        score += 4

    percent_match = _PERCENT_RE.search(text)
    discount_percent = None
    if percent_match:
        value = Decimal(percent_match.group(1).replace(",", "."))
        if 0 < value <= 100:
            discount_percent = value
            score += 3

    prices = [Decimal(value.replace(" ", "").replace("\u00a0", "")) for value in _PRICE_RE.findall(text)]
    old_price = new_price = None
    if len(prices) >= 2:
        old_price, new_price = prices[0], prices[1]
        if old_price > new_price:
            score += 3

    score = max(0, score - negative)
    offer_type = "promo" if promo_code else "discount"
    if "кэшбэк" in normalized_text or "cashback" in normalized_text:
        offer_type = "cashback"
    elif "достав" in normalized_text and ("бесплат" in normalized_text or "0 ₽" in text):
        offer_type = "delivery"

    return OfferSignal(
        is_offer=score >= 4,
        confidence=score,
        offer_type=offer_type,
        matched_keywords=tuple(dict.fromkeys(matched)),
        promo_code=promo_code,
        discount_percent=discount_percent,
        old_price=old_price,
        new_price=new_price,
    )
