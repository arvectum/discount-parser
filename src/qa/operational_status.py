from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from src.jobs.status import SourceRunStatus, get_source_run_statuses
from src.qa.doctor import DoctorReport, build_doctor_report
from src.qa.report import build_smoke_report
from src.shared.config import get_settings
from src.shared.logging import redact_secrets


STATUS_SCHEMA_VERSION = 1

_URL_CREDENTIALS = re.compile(r"(?i)(https?://)([^/@:\s]+):([^/@\s]+)@")
_HEADER_SECRET = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*([^\r\n]+)"
)
_GENERIC_SECRET = re.compile(
    r"(?i)\b(token|password|passwd|secret|api[_-]?key|api[_-]?hash|session)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
)
_ID_CREDENTIAL = re.compile(
    r"(?i)\b(telegram_(?:channel_id|admin_ids)|admin[_-]?id|channel[_-]?id)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _sanitize(value: str | None) -> str | None:
    if not value:
        return None
    clean = redact_secrets(value)
    clean = _URL_CREDENTIALS.sub(r"\1***REDACTED***:***REDACTED***@", clean)
    clean = _HEADER_SECRET.sub(r"\1: ***REDACTED***", clean)
    clean = _GENERIC_SECRET.sub(r"\1=***REDACTED***", clean)
    clean = _ID_CREDENTIAL.sub(r"\1=***REDACTED***", clean)
    return clean


def _source_snapshot(
    status: SourceRunStatus,
    *,
    now: datetime,
    stale_after: timedelta,
) -> dict[str, Any]:
    last_success = status.last_success_at
    if last_success is not None and last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=UTC)
    stale = bool(
        status.enabled
        and (
            last_success is None
            or now - last_success.astimezone(UTC) > stale_after
        )
    )
    return {
        "key": status.source_key,
        "name": status.source_name,
        "enabled": status.enabled,
        "latest_status": status.last_status,
        "last_started_at": _iso(status.last_started_at),
        "last_finished_at": _iso(status.last_finished_at),
        "last_success_at": _iso(status.last_success_at),
        "last_error": _sanitize(status.last_error),
        "fetched_count": status.fetched_count,
        "new_count": status.new_count,
        "updated_count": status.updated_count,
        "stale": stale,
    }


def _doctor_snapshot(report: DoctorReport) -> dict[str, Any]:
    required_failures = [check.name for check in report.checks if check.required and not check.ok]
    optional_failures = [check.name for check in report.checks if not check.required and not check.ok]
    return {
        "ok": report.ok,
        "required_failures": required_failures,
        "optional_failures": optional_failures,
    }


def classify_operational_state(
    *,
    doctor: dict[str, Any],
    setup_complete: bool,
    sources: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if doctor.get("required_failures"):
        reasons.append("required_doctor_check_failed")
        return "error", reasons

    failed_sources = [
        source["key"]
        for source in sources
        if source.get("enabled") and source.get("latest_status") in {"failed", "error"}
    ]
    stale_sources = [source["key"] for source in sources if source.get("enabled") and source.get("stale")]
    if not setup_complete:
        reasons.append("setup_incomplete")
    if doctor.get("optional_failures"):
        reasons.append("optional_doctor_check_failed")
    if failed_sources:
        reasons.append("source_run_failed")
    if stale_sources:
        reasons.append("source_stale")

    return ("warning", reasons) if reasons else ("ok", [])


def build_operational_status(
    *,
    now: datetime | None = None,
    doctor_report: DoctorReport | None = None,
    source_statuses: list[SourceRunStatus] | None = None,
    smoke_report: dict[str, Any] | None = None,
    process_states: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    settings = get_settings()
    stale_after = max(
        timedelta(minutes=max(1, settings.collect_interval_minutes) * 3),
        timedelta(hours=6),
    )

    doctor = _doctor_snapshot(doctor_report or build_doctor_report(check_web_port=False))
    sources = [
        _source_snapshot(item, now=current, stale_after=stale_after)
        for item in (source_statuses if source_statuses is not None else get_source_run_statuses())
    ]
    state, reasons = classify_operational_state(
        doctor=doctor,
        setup_complete=settings.setup_complete,
        sources=sources,
    )

    processes: dict[str, dict[str, Any]] = {}
    if process_states is not None:
        for name in ("bot", "scheduler"):
            item = process_states.get(name)
            if item is not None:
                processes[name] = {
                    "observed": True,
                    "running": bool(getattr(item, "running", False)),
                    "pid": getattr(item, "pid", None),
                }
    for name in ("bot", "scheduler"):
        processes.setdefault(name, {"observed": False, "running": None, "pid": None})

    aggregates = smoke_report if smoke_report is not None else build_smoke_report()
    aggregate_allowlist = (
        "sources",
        "offers_total",
        "offers_ready",
        "offers_needs_review",
        "offers_published",
        "offers_expired",
        "publications_total",
        "publications_published",
        "parse_runs",
    )

    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "generated_at": current.isoformat(),
        "state": state,
        "reasons": reasons,
        "setup_complete": settings.setup_complete,
        "doctor": doctor,
        "processes": processes,
        "freshness_policy": {"stale_after_seconds": int(stale_after.total_seconds())},
        "sources": sources,
        "aggregates": {key: aggregates.get(key, 0) for key in aggregate_allowlist},
    }
