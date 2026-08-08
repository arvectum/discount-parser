from __future__ import annotations

from collections.abc import Callable

from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.config import SourceConfig

AdapterFactory = Callable[[SourceConfig], object]


def _promokood(config: SourceConfig) -> PromokoodAdapter:
    return PromokoodAdapter(config.base_url)


ADAPTER_REGISTRY: dict[str, AdapterFactory] = {
    "promokood": _promokood,
}


def build_adapter(config: SourceConfig):
    try:
        factory = ADAPTER_REGISTRY[config.adapter]
    except KeyError as exc:
        raise KeyError(f"unknown source adapter: {config.adapter}") from exc
    return factory(config)
