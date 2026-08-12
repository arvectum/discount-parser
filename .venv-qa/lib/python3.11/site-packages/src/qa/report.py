from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from src.jobs.status import get_source_run_statuses
from src.modules.offers.models import Offer, ParseRun, Publication, Source
from src.shared.db import create_session


def build_smoke_report() -> dict[str, object]:
    with create_session() as session:
        report: dict[str, object] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "sources": int(session.scalar(select(func.count()).select_from(Source)) or 0),
            "offers_total": int(session.scalar(select(func.count()).select_from(Offer)) or 0),
            "offers_ready": int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "ready")) or 0),
            "offers_needs_review": int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "needs_review")) or 0),
            "offers_published": int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "published")) or 0),
            "offers_expired": int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "expired")) or 0),
            "publications_total": int(session.scalar(select(func.count()).select_from(Publication)) or 0),
            "publications_published": int(
                session.scalar(select(func.count()).select_from(Publication).where(Publication.status == "published")) or 0
            ),
            "parse_runs": int(session.scalar(select(func.count()).select_from(ParseRun)) or 0),
        }
        latest_publication = session.scalar(
            select(Publication).where(Publication.status == "published").order_by(Publication.published_at.desc()).limit(1)
        )
        report["latest_telegram_message_id"] = latest_publication.telegram_message_id if latest_publication else None

    report["source_statuses"] = [asdict(item) for item in get_source_run_statuses()]
    return report


def write_smoke_report(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_smoke_report(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return destination
