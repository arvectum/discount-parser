from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import create_source, seed_default_keywords
from src.sources.config import load_source_configs


TELEGRAM_TEST_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("tg-aktsiya-telegram", "Скидки, акции и промокоды", "aktsiya_telegram"),
    ("tg-promohub", "PromoHub — скидки, акции и промокоды", "PromoHub"),
    ("tg-skidia", "Skidia — скидки, промокоды и акции", "skidia"),
    ("tg-super-promokod", "Супер промокод", "super_promokod_ru"),
    ("tg-promoskid", "Супер Скидки — Промокоды — Акции", "promoskid_en"),
)


def _seed_telegram_test_sources(session: Session) -> tuple[int, int]:
    created = 0
    updated = 0
    for key, name, channel in TELEGRAM_TEST_SOURCES:
        row = session.scalar(select(RegisteredSource).where(RegisteredSource.key == key))
        url = f"https://t.me/s/{channel}"
        if row is None:
            row = create_source(
                session,
                key=key,
                name=name,
                platform="telegram",
                source_type="discount_channel",
                url=url,
                external_id=channel,
                collector_type="telegram_public",
                priority=55,
                trust_level="community",
                check_interval_minutes=120,
                enabled=True,
            )
            row.network_policy = "auto"
            created += 1
        else:
            row.name = name
            row.url = url
            row.external_id = channel
            row.platform = "telegram"
            row.source_type = "discount_channel"
            row.collector_type = "telegram_public"
            if not row.network_policy:
                row.network_policy = "auto"
            updated += 1
    return created, updated


def _retire_orphaned_legacy_mirrors(session: Session, *, configured_keys: set[str]) -> int:
    """Disable obsolete registry mirrors that can no longer map to YAML adapters.

    A ``legacy_adapter`` row is managed by ``config/sources.yaml`` and cannot
    collect independently. Upgrade history may leave one behind after a source
    key is removed or renamed. Keeping such a row enabled makes the registry
    claim that a production source exists even though no matching adapter can
    run it.

    Only rows that are still ``legacy_adapter`` are reconciled here. If a user
    changed a registry source to an explicit collector (for example CSS or
    Telegram), that choice remains user-owned and is never retired by this
    migration-safe seed step.
    """
    rows = session.scalars(
        select(RegisteredSource).where(RegisteredSource.collector_type == "legacy_adapter")
    ).all()
    retired = 0
    for row in rows:
        if row.key in configured_keys or not row.enabled:
            continue
        row.enabled = False
        row.status = "disabled"
        retired += 1
    return retired


def seed_registry(session: Session, *, sources_config_path: str) -> dict[str, int]:
    keywords_created = seed_default_keywords(session)
    sources_created = 0
    sources_updated = 0

    legacy_configs = load_source_configs(sources_config_path)
    configured_legacy_keys = {config.key for config in legacy_configs}

    for config in legacy_configs:
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
            # The YAML file supplies the initial legacy adapter only. Once a
            # user configures CSS mappings in the UI, their explicit collector
            # choice must survive routine registry seeding.
            sources_updated += 1

    sources_retired = _retire_orphaned_legacy_mirrors(
        session,
        configured_keys=configured_legacy_keys,
    )

    telegram_created, telegram_updated = _seed_telegram_test_sources(session)
    sources_created += telegram_created
    sources_updated += telegram_updated

    session.flush()
    return {
        "sources_created": sources_created,
        "sources_updated": sources_updated,
        "sources_retired": sources_retired,
        "keywords_created": keywords_created,
    }
