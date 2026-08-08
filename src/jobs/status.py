from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from src.modules.offers.models import ParseRun, Source
from src.shared.db import create_session


@dataclass(frozen=True, slots=True)
class SourceRunStatus:
    source_key: str
    source_name: str
    enabled: bool
    last_status: str | None
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    fetched_count: int
    new_count: int
    updated_count: int


def get_source_run_statuses() -> list[SourceRunStatus]:
    statuses: list[SourceRunStatus] = []
    with create_session() as session:
        sources = session.scalars(select(Source).order_by(Source.key)).all()
        for source in sources:
            latest = session.scalar(
                select(ParseRun)
                .where(ParseRun.source_id == source.id)
                .order_by(ParseRun.started_at.desc(), ParseRun.id.desc())
                .limit(1)
            )
            last_success_at = session.scalar(
                select(ParseRun.finished_at)
                .where(
                    ParseRun.source_id == source.id,
                    ParseRun.status.in_(("success", "partial")),
                    ParseRun.finished_at.is_not(None),
                )
                .order_by(ParseRun.finished_at.desc())
                .limit(1)
            )
            statuses.append(
                SourceRunStatus(
                    source_key=source.key,
                    source_name=source.name,
                    enabled=source.enabled,
                    last_status=latest.status if latest else None,
                    last_started_at=latest.started_at if latest else None,
                    last_finished_at=latest.finished_at if latest else None,
                    last_success_at=last_success_at,
                    last_error=latest.error if latest and latest.error_count else None,
                    fetched_count=latest.fetched_count if latest else 0,
                    new_count=latest.new_count if latest else 0,
                    updated_count=latest.updated_count if latest else 0,
                )
            )
    return statuses
