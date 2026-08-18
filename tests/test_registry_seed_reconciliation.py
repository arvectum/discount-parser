from __future__ import annotations

from types import SimpleNamespace

from src.modules.source_registry.seed import _retire_orphaned_legacy_mirrors


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, _statement):
        return _Scalars(self._rows)


def _row(*, key: str, collector_type: str = "legacy_adapter", enabled: bool = True, status: str = "unknown"):
    return SimpleNamespace(
        key=key,
        collector_type=collector_type,
        enabled=enabled,
        status=status,
    )


def test_retire_orphaned_enabled_legacy_mirror() -> None:
    active = _row(key="active")
    stale = _row(key="removed")
    session = _Session([active, stale])

    retired = _retire_orphaned_legacy_mirrors(session, configured_keys={"active"})

    assert retired == 1
    assert active.enabled is True
    assert stale.enabled is False
    assert stale.status == "disabled"


def test_preserve_user_owned_nonlegacy_collector() -> None:
    user_owned = _row(key="removed", collector_type="css_generic")
    session = _Session([user_owned])

    retired = _retire_orphaned_legacy_mirrors(session, configured_keys=set())

    assert retired == 0
    assert user_owned.enabled is True
    assert user_owned.status == "unknown"


def test_already_disabled_legacy_mirror_is_left_unchanged() -> None:
    stale = _row(key="removed", enabled=False, status="disabled")
    session = _Session([stale])

    retired = _retire_orphaned_legacy_mirrors(session, configured_keys=set())

    assert retired == 0
    assert stale.enabled is False
    assert stale.status == "disabled"
