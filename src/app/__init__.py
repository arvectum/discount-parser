import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.app.routes import router
from src.shared.config import Settings, get_settings
from src.shared.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("application_started", extra={"env": settings.env})
        yield
        logger.info("application_stopped", extra={"env": settings.env})

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(router)
    return app


__all__ = ["create_app"]
