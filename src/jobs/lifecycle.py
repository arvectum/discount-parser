from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun
from src.shared.db import session_scope

_ACTIVE_STATUSES = {"new", "ready", "needs_review"}


def expire_offers(*, now: datetime | None = None) -> int:
    """Mark explicitly expired offers without deleting history."""
    current = now or datetime.now(UTC)
    changed = 0
    with session_scope() as session:
        offers = session.scalars(
            select(Offer).where(
                Offer.status.in_(_ACTIVE_STATUSES),
                Offer.valid_until.is_not(None),
                Offer.valid_until < current,
            )
        ).all()
        for offer in offers:
            offer.status = "expired"
            changed += 1
    return changed


def _source_has_newer_success(session: Session, observation: OfferSourceObservation) -> bool:
    newer_run = session.scalar(
        select(ParseRun.id)
        .where(
            ParseRun.source_id == observation.source_id,
            ParseRun.status.in_(("success", "partial")),
            ParseRun.finished_at.is_not(None),
            ParseRun.finished_at > observation.observed_at,
        )
        .order_by(ParseRun.finished_at.desc())
        .limit(1)
    )
    return newer_run is not None


def mark_stale_for_review(*, stale_after_days: int = 7, now: datetime | None = None) -> int:
    """Conservatively flag undated offers missing from later successful source runs.

    An offer is never marked stale merely because a source failed. Every known
    provenance source must have a successful/partial run newer than its last
    observation before the offer is moved to needs_review.
    """
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=max(1, stale_after_days))
    changed = 0

    with session_scope() as session:
        candidates = session.scalars(
            select(Offer).where(
                Offer.status.in_(("new", "ready")),
                Offer.valid_until.is_(None),
                Offer.last_seen_at < cutoff,
            )
        ).all()

        for offer in candidates:
            observations = list(offer.observations)
            if not observations:
                continue
            if all(_source_has_newer_success(session, observation) for observation in observations):
                offer.status = "needs_review"
                changed += 1

    return changed


def maintenance(*, stale_after_days: int = 7, now: datetime | None = None) -> dict[str, int]:
    current = now or datetime.now(UTC)
    return {
        "expired": expire_offers(now=current),
        "stale_for_review": mark_stale_for_review(stale_after_days=stale_after_days, now=current),
    }
