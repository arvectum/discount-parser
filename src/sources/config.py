from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class SourceConfig:
    key: str
    name: str
    adapter: str
    base_url: str
    enabled: bool = True


def load_source_configs(path: str | Path = "config/sources.yaml") -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    result: list[SourceConfig] = []
    for item in data.get("sources", []):
        result.append(
            SourceConfig(
                key=str(item["key"]),
                name=str(item.get("name") or item["key"]),
                adapter=str(item["adapter"]),
                base_url=str(item["base_url"]),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return result
