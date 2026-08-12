from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from src.jobs.status import get_source_run_statuses
from src.shared.db import check_db_connection

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.env,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/db")
def database_health() -> dict[str, str]:
    connected = check_db_connection()
    return {
        "status": "ok" if connected else "error",
        "database": "connected" if connected else "unavailable",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/sources")
def source_health() -> dict[str, object]:
    statuses = [asdict(item) for item in get_source_run_statuses()]
    failed = sum(1 for item in statuses if item["last_status"] == "failed")
    return {
        "status": "ok" if failed == 0 else "degraded",
        "failed_sources": failed,
        "sources": statuses,
        "timestamp": datetime.now(UTC).isoformat(),
    }
