from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import create_source, seed_default_keywords
from src.sources.config import load_source_configs


def seed_registry(session: Session, *, sources_config_path: str) -> dict[str, int]:
    keywords_created = seed_default_keywords(session)
    sources_created = 0
    sources_updated = 0

    for config in load_source_configs(sources_config_path):
        row = session.scalar(select(RegisteredSource).where(RegisteredSource.key == config.key))
        if row is None:
            create_source(
                session,
                key=config.key,
                name=config.name,
                platform="promo_aggregator",
                source_type="promo_aggregator",
                url=config.base_url,
                external_id=config.key,
                collector_type="legacy_adapter",
                priority=60,
                trust_level="aggregator",
                enabled=config.enabled,
            )
            sources_created += 1
        else:
            row.name = config.name
            row.url = config.base_url
            row.platform = "promo_aggregator"
            row.source_type = "promo_aggregator"
            row.collector_type = "legacy_adapter"
            sources_updated += 1

    session.flush()
    return {
        "sources_created": sources_created,
        "sources_updated": sources_updated,
        "keywords_created": keywords_created,
    }
