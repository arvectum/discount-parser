from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.modules.offers.models import Offer, OfferSourceObservation, Publication, PublishFilter, Source
from src.core.validity import extract_valid_until


@dataclass(frozen=True, slots=True)
class PublishCriteria:
    min_discount_percent: Decimal | None = None
    category: str | None = None
    subcategory: str | None = None
    offer_type: str | None = None
    merchant: str | None = None
    source_key: str | None = None
    city: str | None = None
    region: str | None = None
    limit: int = 20

    @classmethod
    def from_filter(cls, row: PublishFilter) -> "PublishCriteria":
        return cls(
            min_discount_percent=row.min_discount_percent,
            category=row.category,
            subcategory=row.subcategory,
            offer_type=row.offer_type,
            merchant=row.merchant,
            source_key=row.source_key,
            city=row.city,
            region=row.region,
            limit=row.max_posts_per_cycle,
        )


def list_publish_candidates(
    session: Session,
    *,
    channel_id: str,
    criteria: PublishCriteria | None = None,
) -> list[Offer]:
    criteria = criteria or PublishCriteria()
    query = select(Offer).where(
        Offer.status == "ready",
        ~exists().where(
            Publication.offer_id == Offer.id,
            Publication.channel_id == channel_id,
            Publication.status.in_(["pending", "published"]),
        ),
    )

    if criteria.min_discount_percent is not None:
        query = query.where(Offer.discount_percent >= criteria.min_discount_percent)
    if criteria.category:
        query = query.where(Offer.category == criteria.category)
    if criteria.subcategory:
        query = query.where(Offer.subcategory == criteria.subcategory)
    if criteria.offer_type:
        query = query.where(Offer.offer_type == criteria.offer_type)
    if criteria.merchant:
        query = query.where(Offer.merchant == criteria.merchant)
    if criteria.city:
        query = query.where(Offer.city == criteria.city)
    if criteria.region:
        query = query.where(Offer.region == criteria.region)
    if criteria.source_key:
        query = (
            query.join(OfferSourceObservation, OfferSourceObservation.offer_id == Offer.id)
            .join(Source, Source.id == OfferSourceObservation.source_id)
            .where(Source.key == criteria.source_key)
            .distinct()
        )

    query = query.order_by(Offer.discount_percent.desc().nullslast(), Offer.first_seen_at.desc()).limit(
        max(1, min(criteria.limit, 100))
    )
    now = datetime.now(UTC)
    result: list[Offer] = []
    for offer in session.scalars(query).all():
        expiry = offer.valid_until or extract_valid_until("\n".join(v for v in (offer.title, offer.description, offer.conditions) if v), now=now)
        if expiry:
            offer.valid_until = expiry
        if expiry and expiry < now:
            offer.status = "expired"
            continue
        result.append(offer)
    return result
