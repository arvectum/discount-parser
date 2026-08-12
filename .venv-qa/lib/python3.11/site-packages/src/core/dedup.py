from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.core.normalization import NormalizedOffer, normalize_text
from src.modules.offers.models import Offer


@dataclass(frozen=True, slots=True)
class MatchResult:
    offer: Offer | None
    reason: str | None = None
    score: float | None = None


def find_existing_offer(session: Session, normalized: NormalizedOffer, fuzzy_threshold: float = 92.0) -> MatchResult:
    if normalized.canonical_url:
        offer = session.scalar(select(Offer).where(Offer.canonical_url == normalized.canonical_url).limit(1))
        if offer is not None:
            return MatchResult(offer, "canonical_url", 100.0)

    if normalized.promo_code and normalized.merchant:
        offer = session.scalar(
            select(Offer).where(
                Offer.promo_code == normalized.promo_code,
                Offer.merchant == normalized.merchant,
            ).limit(1)
        )
        if offer is not None:
            return MatchResult(offer, "merchant_promo_code", 100.0)

    offer = session.scalar(select(Offer).where(Offer.fingerprint == normalized.fingerprint).limit(1))
    if offer is not None:
        return MatchResult(offer, "fingerprint", 100.0)

    if not normalized.merchant:
        return MatchResult(None)

    candidates = session.scalars(
        select(Offer).where(
            or_(Offer.merchant == normalized.merchant, Offer.merchant.is_(None))
        ).order_by(Offer.updated_at.desc()).limit(100)
    ).all()
    target_title = normalize_text(normalized.title)
    best_offer: Offer | None = None
    best_score = 0.0
    for candidate in candidates:
        if normalize_text(candidate.merchant) != normalize_text(normalized.merchant):
            continue
        score = float(fuzz.token_set_ratio(target_title, normalize_text(candidate.title)))
        if normalized.discount_percent is not None and candidate.discount_percent is not None:
            if normalized.discount_percent != candidate.discount_percent:
                score -= 8.0
        if normalized.discount_amount is not None and candidate.discount_amount is not None:
            if normalized.discount_amount != candidate.discount_amount:
                score -= 8.0
        if score > best_score:
            best_offer = candidate
            best_score = score

    if best_offer is not None and best_score >= fuzzy_threshold:
        return MatchResult(best_offer, "fuzzy_title", best_score)
    return MatchResult(None, score=best_score if best_offer is not None else None)
