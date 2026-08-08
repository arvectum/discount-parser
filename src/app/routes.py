from datetime import UTC, datetime

from fastapi import APIRouter, Request

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
