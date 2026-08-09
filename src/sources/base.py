from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(slots=True)
class RawOffer:
    source_key: str
    external_id: str
    title: str
    source_url: str
    merchant: str | None = None
    brand: str | None = None
    description: str | None = None
    city: str | None = None
    region: str | None = None
    promo_code: str | None = None
    discount_percent: Decimal | None = None
    discount_amount: Decimal | None = None
    old_price: Decimal | None = None
    new_price: Decimal | None = None
    cashback_percent: Decimal | None = None
    cashback_amount: Decimal | None = None
    delivery_price: Decimal | None = None
    image_url: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    raw_payload: dict | None = None


class SourceAdapter(Protocol):
    key: str

    def collect(self) -> list[RawOffer]: ...
