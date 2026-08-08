from __future__ import annotations

from pathlib import Path

import pytest

from src.shared.config import get_settings
from src.web import setup as setup_utils


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / '.env'
    example_path = tmp_path / '.env.example'
    example_path.write_text(
        'DP_COLLECT_INTERVAL_MINUTES=120\n'
        'DP_AUTOPOST_INTERVAL_MINUTES=30\n'
        'DP_MAINTENANCE_HOUR=22\n'
        'DP_MAINTENANCE_MINUTE=0\n'
        'DP_STALE_AFTER_DAYS=7\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(setup_utils, 'ENV_PATH', env_path)
    monkeypatch.setattr(setup_utils, 'ENV_EXAMPLE_PATH', example_path)
    get_settings.cache_clear()
    yield env_path
    get_settings.cache_clear()


def test_operational_settings_are_written_to_env(isolated_env: Path) -> None:
    setup_utils.save_operational_settings(
        collect_interval_minutes=45,
        autopost_interval_minutes=15,
        maintenance_hour=3,
        maintenance_minute=30,
        stale_after_days=14,
    )

    text = isolated_env.read_text(encoding='utf-8')
    assert 'DP_COLLECT_INTERVAL_MINUTES=45' in text
    assert 'DP_AUTOPOST_INTERVAL_MINUTES=15' in text
    assert 'DP_MAINTENANCE_HOUR=3' in text
    assert 'DP_MAINTENANCE_MINUTE=30' in text
    assert 'DP_STALE_AFTER_DAYS=14' in text


def test_operational_settings_validate_ranges(isolated_env: Path) -> None:
    with pytest.raises(ValueError, match='Интервал сбора'):
        setup_utils.save_operational_settings(
            collect_interval_minutes=0,
            autopost_interval_minutes=15,
            maintenance_hour=3,
            maintenance_minute=30,
            stale_after_days=14,
        )
    assert not isolated_env.exists()
