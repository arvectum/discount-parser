from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.sources.base import RawOffer

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "yclid", "gclid", "fbclid", "ref", "referrer", "from",
}


def normalize_text(value: str | None) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9%+.-]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))


def decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def compute_discount_percent(old_price: Decimal | None, new_price: Decimal | None) -> Decimal | None:
    if old_price is None or new_price is None or old_price <= 0 or new_price < 0 or new_price >= old_price:
        return None
    return ((old_price - new_price) / old_price * Decimal("100")).quantize(Decimal("0.01"))


def resolve_offer_type(raw: RawOffer) -> str:
    text = normalize_text(f"{raw.title} {raw.description or ''}")
    if raw.promo_code:
        return "promo"
    if raw.cashback_percent is not None or raw.cashback_amount is not None or "кэшб" in text or "кешб" in text or "cashback" in text:
        return "cashback"
    if raw.delivery_price is not None or ("доставк" in text and "бесплат" in text):
        return "delivery"
    return "discount"


def build_fingerprint(
    *, merchant: str | None, title: str, promo_code: str | None,
    discount_percent: Decimal | None, discount_amount: Decimal | None,
    cashback_percent: Decimal | None, cashback_amount: Decimal | None,
    delivery_price: Decimal | None,
) -> str:
    payload = "|".join(
        [
            normalize_text(merchant), normalize_text(title), normalize_text(promo_code),
            str(discount_percent or ""), str(discount_amount or ""),
            str(cashback_percent or ""), str(cashback_amount or ""), str(delivery_price or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizedOffer:
    title: str
    merchant: str | None
    brand: str | None
    promo_code: str | None
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    old_price: Decimal | None
    new_price: Decimal | None
    cashback_percent: Decimal | None
    cashback_amount: Decimal | None
    delivery_price: Decimal | None
    canonical_url: str | None
    offer_type: str
    fingerprint: str


def normalize_raw_offer(raw: RawOffer) -> NormalizedOffer:
    old_price = decimal_or_none(raw.old_price)
    new_price = decimal_or_none(raw.new_price)
    discount_percent = decimal_or_none(raw.discount_percent) or compute_discount_percent(old_price, new_price)
    discount_amount = decimal_or_none(raw.discount_amount)
    cashback_percent = decimal_or_none(raw.cashback_percent)
    cashback_amount = decimal_or_none(raw.cashback_amount)
    delivery_price = decimal_or_none(raw.delivery_price)
    merchant = re.sub(r"\s+", " ", (raw.merchant or "").strip()) or None
    brand = re.sub(r"\s+", " ", (raw.brand or "").strip()) or None
    title = re.sub(r"\s+", " ", raw.title.strip())
    promo_code = raw.promo_code.strip().upper() if raw.promo_code else None
    return NormalizedOffer(
        title=title,
        merchant=merchant,
        brand=brand,
        promo_code=promo_code,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        old_price=old_price,
        new_price=new_price,
        cashback_percent=cashback_percent,
        cashback_amount=cashback_amount,
        delivery_price=delivery_price,
        canonical_url=canonicalize_url(raw.source_url),
        offer_type=resolve_offer_type(raw),
        fingerprint=build_fingerprint(
            merchant=merchant,
            title=title,
            promo_code=promo_code,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            cashback_percent=cashback_percent,
            cashback_amount=cashback_amount,
            delivery_price=delivery_price,
        ),
    )
