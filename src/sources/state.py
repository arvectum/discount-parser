from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from src.modules.offers.models import Source
from src.shared.db import create_session
from src.sources.config import SourceConfig, load_source_configs


@dataclass(frozen=True, slots=True)
class SourceState:
    key: str
    name: str
    base_url: str
    enabled: bool


def list_source_states(path: str = "config/sources.yaml") -> list[SourceState]:
    configs = load_source_configs(path)
    with create_session() as session:
        persisted = {
            row.key: row
            for row in session.scalars(select(Source).where(Source.key.in_([item.key for item in configs]))).all()
        }
    return [
        SourceState(
            key=config.key,
            name=config.name,
            base_url=config.base_url,
            enabled=bool(persisted[config.key].enabled) if config.key in persisted else config.enabled,
        )
        for config in configs
    ]


def set_persisted_source_enabled(key: str, enabled: bool, path: str = "config/sources.yaml") -> SourceState:
    configs = {item.key: item for item in load_source_configs(path)}
    config: SourceConfig | None = configs.get(key)
    if config is None:
        raise KeyError(f"Unknown source: {key}")

    with create_session() as session:
        source = session.scalar(select(Source).where(Source.key == key))
        if source is None:
            source = Source(key=config.key, name=config.name, base_url=config.base_url, enabled=bool(enabled))
            session.add(source)
        else:
            source.name = config.name
            source.base_url = config.base_url
            source.enabled = bool(enabled)
        session.commit()

    return SourceState(key=config.key, name=config.name, base_url=config.base_url, enabled=bool(enabled))
