from __future__ import annotations

from pathlib import Path

import pytest

from src.shared.config import get_settings
from src.shared.db import Base, get_engine, reset_db_runtime
from src.sources.state import list_source_states, set_persisted_source_enabled


@pytest.fixture
def source_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - key: demo\n"
        "    name: Demo\n"
        "    adapter: demo\n"
        "    base_url: https://example.test/\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'sources.db'}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield config
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_persisted_disabled_state_overrides_yaml_default(source_db: Path) -> None:
    assert list_source_states(str(source_db))[0].enabled is True
    set_persisted_source_enabled("demo", False, str(source_db))
    assert list_source_states(str(source_db))[0].enabled is False
