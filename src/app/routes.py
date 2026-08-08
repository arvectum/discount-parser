from datetime import UTC, datetime

from fastapi import APIRouter, Request

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
