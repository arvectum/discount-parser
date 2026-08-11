from __future__ import annotations

import re
from datetime import UTC, datetime

_NUMERIC = re.compile(r"(?:до|по|действует\s+до|активн\w*\s+до|срок\s+действия\s+до)?\s*(\d{1,2})[./](\d{1,2})[./](\d{4})", re.I)
_MONTH = re.compile(r"(?:до|по|действует\s+до|активн\w*\s+до|срок\s+действия\s+до)\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?", re.I)
_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}


def extract_valid_until(text: str | None, *, now: datetime | None = None) -> datetime | None:
    if not text or re.search(r"бессрочн", text, re.I):
        return None
    current = now or datetime.now(UTC)
    match = _NUMERIC.search(text)
    if match:
        day, month, year = map(int, match.groups())
        try: return datetime(year, month, day, 23, 59, 59, tzinfo=UTC)
        except ValueError: return None
    match = _MONTH.search(text)
    if not match:
        return None
    day, month_name, year_value = match.groups()
    year = int(year_value) if year_value else current.year
    try:
        result = datetime(year, _MONTHS[month_name.casefold()], int(day), 23, 59, 59, tzinfo=UTC)
    except ValueError:
        return None
    if not year_value and result < current:
        result = result.replace(year=year + 1)
    return result
