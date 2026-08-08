from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from src.core.classification import classify_offer
from src.core.dedup import find_existing_offer
from src.core.normalization import normalize_raw_offer
from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun, Source
from src.modules.offers.repository import OfferRepository
from src.shared.db import session_scope
from src.sources.base import RawOffer
from src.sources.config import SourceConfig, load_source_configs
from src.sources.registry import build_adapter


@dataclass(slots=True)
class RunResult:
    source_key: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0
    error: str | None = None


def _ensure_source(session, config: SourceConfig) -> Source:
    source = session.scalar(select(Source).where(Source.key == config.key))
    if source is None:
        source = Source(key=config.key, name=config.name, base_url=config.base_url, enabled=config.enabled)
        session.add(source)
        session.flush()
    else:
        source.name = config.name
        source.base_url = config.base_url
        source.enabled = config.enabled
    return source


def _non_empty(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None and value != ""}


def _persist_raw_offer(session, source: Source, raw: RawOffer) -> bool:
    observation = session.scalar(
        select(OfferSourceObservation).where(
            OfferSourceObservation.source_id == source.id,
            OfferSourceObservation.external_id == raw.external_id,
        )
    )
    now = datetime.now(UTC)
    if observation is not None:
        observation.observed_at = now
        observation.raw_title = raw.title
        observation.raw_payload_json = json.dumps(raw.raw_payload or {}, ensure_ascii=False)
        observation.offer.last_seen_at = now
        return False

    normalized = normalize_raw_offer(raw)
    match = find_existing_offer(session, normalized)
    repo = OfferRepository(session)

    common_values = _non_empty(
        {
            "title": normalized.title,
            "description": raw.description,
            "merchant": normalized.merchant,
            "brand": normalized.brand,
            "promo_code": normalized.promo_code,
            "discount_percent": normalized.discount_percent,
            "discount_amount": normalized.discount_amount,
            "old_price": normalized.old_price,
            "new_price": normalized.new_price,
            "cashback_percent": normalized.cashback_percent,
            "cashback_amount": normalized.cashback_amount,
            "delivery_price": normalized.delivery_price,
            "canonical_url": normalized.canonical_url,
            "image_url": raw.image_url,
            "valid_from": raw.valid_from,
            "valid_until": raw.valid_until,
            "offer_type": normalized.offer_type,
            "fingerprint": normalized.fingerprint,
            "last_seen_at": now,
        }
    )

    if match.offer is not None:
        offer = match.offer
        classification = classify_offer(
            session,
            title=normalized.title,
            merchant=normalized.merchant,
            brand=normalized.brand or offer.brand,
            offer=offer,
        )
        repo.update(
            offer,
            {
                **common_values,
                "category": classification.category,
                "subcategory": classification.subcategory,
            },
        )
    else:
        classification = classify_offer(
            session,
            title=normalized.title,
            merchant=normalized.merchant,
            brand=normalized.brand,
        )
        has_benefit = any(
            value is not None
            for value in (
                normalized.discount_percent,
                normalized.discount_amount,
                normalized.cashback_percent,
                normalized.cashback_amount,
                normalized.delivery_price,
            )
        ) or bool(normalized.promo_code) or "бесплат" in normalized.title.lower()
        status = "ready" if has_benefit and classification.reason != "fallback" else "needs_review"
        offer = repo.create(
            offer_type=normalized.offer_type,
            status=status,
            category=classification.category,
            subcategory=classification.subcategory,
            first_seen_at=now,
            **common_values,
        )

    session.add(
        OfferSourceObservation(
            offer_id=offer.id,
            source_id=source.id,
            external_id=raw.external_id,
            source_url=raw.source_url,
            raw_title=raw.title,
            raw_payload_json=json.dumps(
                {
                    **(raw.raw_payload or {}),
                    "dedup_reason": match.reason,
                    "dedup_score": match.score,
                },
                ensure_ascii=False,
            ),
            observed_at=now,
        )
    )
    session.flush()
    return match.offer is None


def _record_failed_collection(config: SourceConfig, error: Exception) -> RunResult:
    message = f"{type(error).__name__}: {error}"
    with session_scope() as session:
        source = _ensure_source(session, config)
        session.add(
            ParseRun(
                source_id=source.id,
                status="failed",
                finished_at=datetime.now(UTC),
                error_count=1,
                error=message,
            )
        )
    return RunResult(source_key=config.key, errors=1, error=message)


def run_source(config: SourceConfig) -> RunResult:
    try:
        raw_offers = build_adapter(config).collect()
    except Exception as exc:
        return _record_failed_collection(config, exc)

    result = RunResult(source_key=config.key, fetched=len(raw_offers))
    with session_scope() as session:
        source = _ensure_source(session, config)
        parse_run = ParseRun(source_id=source.id, status="running", fetched_count=result.fetched)
        session.add(parse_run)
        session.flush()

        errors: list[str] = []
        for raw in raw_offers:
            try:
                with session.begin_nested():
                    created = _persist_raw_offer(session, source, raw)
                if created:
                    result.created += 1
                else:
                    result.updated += 1
            except Exception as exc:
                result.errors += 1
                errors.append(f"{raw.external_id}: {type(exc).__name__}: {exc}")

        parse_run.new_count = result.created
        parse_run.updated_count = result.updated
        parse_run.duplicate_count = result.updated
        parse_run.review_count = int(
            session.scalar(
                select(func.count(func.distinct(Offer.id)))
                .join(OfferSourceObservation, OfferSourceObservation.offer_id == Offer.id)
                .where(
                    OfferSourceObservation.source_id == source.id,
                    OfferSourceObservation.observed_at >= parse_run.started_at,
                    Offer.status == "needs_review",
                )
            )
            or 0
        )
        parse_run.error_count = result.errors
        parse_run.error = "\n".join(errors)[:10000] if errors else None
        parse_run.status = "partial" if errors else "success"
        parse_run.finished_at = datetime.now(UTC)
        result.error = parse_run.error
    return result


def run_all(path: str = "config/sources.yaml", only: str | None = None) -> list[RunResult]:
    results: list[RunResult] = []
    for config in load_source_configs(path):
        if not config.enabled:
            continue
        if only and config.key != only:
            continue
        results.append(run_source(config))
    return results
