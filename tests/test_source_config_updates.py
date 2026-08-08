from __future__ import annotations

from pathlib import Path

from src.sources.config import load_source_configs, set_source_enabled


def test_set_source_enabled_persists_yaml(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - key: demo\n"
        "    name: Demo\n"
        "    adapter: demo\n"
        "    base_url: https://example.test/\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    changed = set_source_enabled("demo", False, path)
    assert changed.enabled is False
    assert load_source_configs(path)[0].enabled is False
