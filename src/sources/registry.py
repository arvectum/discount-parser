from __future__ import annotations

from collections.abc import Callable

from src.sources.adapters.berikod import BerikodAdapter
from src.sources.adapters.promko import PromkoAdapter
from src.sources.adapters.promokodik import PromokodikAdapter
from src.sources.adapters.promokodi_net_ru import PromokodiNetRuAdapter
from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.config import SourceConfig
from src.sources.http import HttpClient

AdapterFactory = Callable[[SourceConfig], object]


def _factory(adapter_cls):
    return lambda config: adapter_cls(
        config.base_url,
        client=HttpClient(network_policy=config.network_policy),
    )


ADAPTER_REGISTRY: dict[str, AdapterFactory] = {
    "promokood": _factory(PromokoodAdapter),
    "promokodik": _factory(PromokodikAdapter),
    "berikod": _factory(BerikodAdapter),
    "promokodi_net_ru": _factory(PromokodiNetRuAdapter),
    "promko": _factory(PromkoAdapter),
}


def build_adapter(config: SourceConfig):
    try:
        factory = ADAPTER_REGISTRY[config.adapter]
    except KeyError as exc:
        raise KeyError(f"unknown source adapter: {config.adapter}") from exc
    return factory(config)
