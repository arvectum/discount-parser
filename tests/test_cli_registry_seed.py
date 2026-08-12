from __future__ import annotations

from src import cli


def test_registry_seed_passes_config_path_by_keyword(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(cli, "session_scope", SessionContext)
    monkeypatch.setattr(
        cli,
        "seed_registry",
        lambda session, *, sources_config_path: captured.update(
            session=session, sources_config_path=sources_config_path
        ) or {"sources_created": 0},
    )

    assert cli.main(["registry-seed"]) == 0
    assert captured["sources_config_path"] == cli.get_settings().sources_config_path
