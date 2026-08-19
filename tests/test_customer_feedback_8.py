from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from src.modules.publishing.service import list_publish_candidates


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, _query):
        return _ScalarResult(self._rows)


def test_publish_candidates_accept_sqlite_naive_valid_until() -> None:
    offer = SimpleNamespace(
        valid_until=datetime(2099, 1, 1, 12, 0, 0),
        title="Будущее предложение",
        description=None,
        conditions=None,
        status="ready",
    )

    result = list_publish_candidates(_Session([offer]), channel_id="-100123")

    assert result == [offer]
    assert offer.status == "ready"


def test_publish_candidates_expire_sqlite_naive_past_datetime() -> None:
    offer = SimpleNamespace(
        valid_until=datetime(2000, 1, 1, 12, 0, 0),
        title="Просроченное предложение",
        description=None,
        conditions=None,
        status="ready",
    )

    result = list_publish_candidates(_Session([offer]), channel_id="-100123")

    assert result == []
    assert offer.status == "expired"
