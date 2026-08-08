from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.shared.config import get_settings
from src.shared.db import Base, get_engine, reset_db_runtime
from src.sources.base import RawOffer
from src.sources.runner import run_all


class FailingAdapter:
    def collect(self):
        raise RuntimeError("source unavailable")


class GoodAdapter:
    def collect(self):
        return [
            RawOffer(
                source_key="good",
                external_id="good-1",
                title="Pampers скидка 20%",
                source_url="https://good.example/deal",
                merchant="Детский мир",
                discount_percent=Decimal("20"),
            )
        ]


def test_run_all_continues_after_one_source_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "all.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())

    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """sources:
  - key: broken
    name: Broken
    adapter: broken
    base_url: https://broken.example/
  - key: good
    name: Good
    adapter: good
    base_url: https://good.example/
""",
        encoding="utf-8",
    )
    adapters = {"broken": FailingAdapter(), "good": GoodAdapter()}
    monkeypatch.setattr("src.sources.runner.build_adapter", lambda config: adapters[config.key])

    results = run_all(str(config_path))
    assert [result.source_key for result in results] == ["broken", "good"]
    assert results[0].errors == 1
    assert results[1].created == 1
    assert results[1].errors == 0

    reset_db_runtime()
    get_settings.cache_clear()
