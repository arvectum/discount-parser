from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun, Source
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

    has_benefit = raw.discount_percent is not None or raw.discount_amount is not None or bool(raw.promo_code)
    offer = Offer(
        offer_type="promo" if raw.promo_code else "discount",
        status="ready" if has_benefit else "needs_review",
        title=raw.title,
        description=raw.description,
        merchant=raw.merchant,
        promo_code=raw.promo_code,
        discount_percent=raw.discount_percent,
        discount_amount=raw.discount_amount,
        canonical_url=raw.source_url,
        image_url=raw.image_url,
        valid_until=raw.valid_until,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(offer)
    session.flush()
    session.add(
        OfferSourceObservation(
            offer_id=offer.id,
            source_id=source.id,
            external_id=raw.external_id,
            source_url=raw.source_url,
            raw_title=raw.title,
            raw_payload_json=json.dumps(raw.raw_payload or {}, ensure_ascii=False),
            observed_at=now,
        )
    )
    return True


def run_source(config: SourceConfig) -> RunResult:
    result = RunResult(source_key=config.key)
    with session_scope() as session:
        source = _ensure_source(session, config)
        parse_run = ParseRun(source_id=source.id, status="running")
        session.add(parse_run)
        session.flush()
        try:
            adapter = build_adapter(config)
            raw_offers = adapter.collect()
            result.fetched = len(raw_offers)
            parse_run.fetched_count = result.fetched
            for raw in raw_offers:
                if _persist_raw_offer(session, source, raw):
                    result.created += 1
                else:
                    result.updated += 1
            parse_run.new_count = result.created
            parse_run.updated_count = result.updated
            parse_run.status = "success"
        except Exception as exc:
            result.errors = 1
            result.error = f"{type(exc).__name__}: {exc}"
            parse_run.error_count = 1
            parse_run.error = result.error
            parse_run.status = "failed"
        finally:
            parse_run.finished_at = datetime.now(UTC)
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
