from typing import TYPE_CHECKING

from src.sources.base import RawOffer, SourceAdapter
from src.sources.config import SourceConfig, load_source_configs

if TYPE_CHECKING:
    from src.sources.runner import RunResult

__all__ = [
    "RawOffer",
    "RunResult",
    "SourceAdapter",
    "SourceConfig",
    "load_source_configs",
    "run_all",
    "run_source",
]


def __getattr__(name: str):
    """Load runner exports lazily to avoid a normalization/runner import cycle."""
    if name in {"RunResult", "run_all", "run_source"}:
        from src.sources import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
