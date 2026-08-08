from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.jobs.lifecycle import maintenance
from src.shared.config import get_settings
from src.sources.runner import run_all

logger = logging.getLogger(__name__)


def collect_sources_job() -> None:
    settings = get_settings()
    results = run_all(path=settings.sources_config_path)
    logger.info(
        "scheduled_collection_finished",
        extra={
            "sources": len(results),
            "fetched": sum(item.fetched for item in results),
            "created": sum(item.created for item in results),
            "updated": sum(item.updated for item in results),
            "errors": sum(item.errors for item in results),
        },
    )


def maintenance_job() -> None:
    settings = get_settings()
    result = maintenance(stale_after_days=settings.stale_after_days)
    logger.info("scheduled_maintenance_finished", extra=result)


def build_scheduler(
    *,
    collect_callable: Callable[[], None] = collect_sources_job,
    maintenance_callable: Callable[[], None] = maintenance_job,
    background: bool = False,
    collect_interval_seconds: float | None = None,
):
    settings = get_settings()
    scheduler_cls = BackgroundScheduler if background else BlockingScheduler
    scheduler = scheduler_cls(timezone=settings.timezone)

    if collect_interval_seconds is not None:
        collect_trigger = IntervalTrigger(seconds=collect_interval_seconds)
        misfire_grace_time = max(1, int(collect_interval_seconds * 3))
    else:
        collect_trigger = IntervalTrigger(minutes=settings.collect_interval_minutes)
        misfire_grace_time = max(60, settings.collect_interval_minutes * 60)

    scheduler.add_job(
        collect_callable,
        trigger=collect_trigger,
        id="collect_sources",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=misfire_grace_time,
    )
    scheduler.add_job(
        maintenance_callable,
        trigger=CronTrigger(hour=settings.maintenance_hour, minute=settings.maintenance_minute),
        id="maintenance",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


def run_scheduler() -> None:
    scheduler = build_scheduler()
    logger.info("scheduler_started", extra={"timezone": str(scheduler.timezone)})
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")
