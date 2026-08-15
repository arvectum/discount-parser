from __future__ import annotations

from datetime import UTC, datetime

from src.core.validity import extract_valid_until


def test_validity_parser_dates_months_and_undated() -> None:
    assert extract_valid_until("действует до 31.05.2026") == datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC)
    assert extract_valid_until("до 1 августа 2026") == datetime(2026, 8, 1, 23, 59, 59, tzinfo=UTC)
    assert extract_valid_until("бессрочный промокод") is None


def test_validity_parser_missing_year_uses_next_date() -> None:
    now = datetime(2026, 12, 31, 12, tzinfo=UTC)
    assert extract_valid_until("до 1 января", now=now) == datetime(2027, 1, 1, 23, 59, 59, tzinfo=UTC)
