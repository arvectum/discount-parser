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


def set_source_enabled(key: str, enabled: bool, path: str | Path = "config/sources.yaml") -> SourceConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for item in data.get("sources", []):
        if str(item.get("key")) == key:
            item["enabled"] = bool(enabled)
            config_path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            return SourceConfig(
                key=str(item["key"]),
                name=str(item.get("name") or item["key"]),
                adapter=str(item["adapter"]),
                base_url=str(item["base_url"]),
                enabled=bool(item["enabled"]),
            )
    raise KeyError(f"Unknown source: {key}")
