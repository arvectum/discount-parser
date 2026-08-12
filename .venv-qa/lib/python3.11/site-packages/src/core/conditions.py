from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re


@dataclass(frozen=True, slots=True)
class ConditionResult:
    conditions: str | None = None
    max_discount_amount: Decimal | None = None
    min_order_amount: Decimal | None = None


_MAX_DISCOUNT_PATTERNS = (
    re.compile(r"(?:но\s+)?не\s+более\s+(\d{1,3}(?:[\s\u00a0]\d{3})*|\d+)\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE),
    re.compile(r"максим(?:альная|альный)?\s+(?:скидка|размер\s+скидки)\s*[:—-]?\s*(\d{1,3}(?:[\s\u00a0]\d{3})*|\d+)\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE),
)
_MIN_ORDER_PATTERNS = (
    re.compile(r"(?:при\s+)?(?:заказе|покупке|сумме\s+заказа)\s+(?:от|не\s+менее)\s+(\d{1,3}(?:[\s\u00a0]\d{3})*|\d+)\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE),
    re.compile(r"минимальн(?:ая|ый)\s+(?:сумма\s+заказа|заказ)\s*[:—-]?\s*(\d{1,3}(?:[\s\u00a0]\d{3})*|\d+)\s*(?:₽|руб(?:\.|лей|ля)?)", re.IGNORECASE),
)
_CONDITION_HINTS = re.compile(
    r"(?:не\s+более|максимальн\w*\s+скидк\w*|заказ\w*\s+от|покупк\w*\s+от|min\.?\s*заказ|"
    r"только\s+при|при\s+оплате|не\s+действует|кроме|исключая|для\s+новых|для\s+первого|"
    r"один\s+раз|не\s+суммируется|суммируется|по\s+карте|в\s+приложении)",
    re.IGNORECASE,
)


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(" ", "").replace("\u00a0", ""))


def _first_decimal(text: str, patterns: tuple[re.Pattern[str], ...]) -> Decimal | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return _decimal(match.group(1))
    return None


def _condition_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?;])\s+|\n+", text)
    result: list[str] = []
    for chunk in chunks:
        cleaned = " ".join(chunk.split()).strip(" •—-\t")
        if cleaned and _CONDITION_HINTS.search(cleaned):
            result.append(cleaned)
    return result


def extract_conditions(*parts: str | None, explicit: str | None = None) -> ConditionResult:
    text = "\n".join(part for part in parts if part).strip()
    max_discount = _first_decimal(text, _MAX_DISCOUNT_PATTERNS) if text else None
    min_order = _first_decimal(text, _MIN_ORDER_PATTERNS) if text else None

    if explicit and explicit.strip():
        conditions = " ".join(explicit.split()).strip()
    elif text:
        selected = _condition_sentences(text)
        conditions = " ".join(dict.fromkeys(selected))[:2000] or None
    else:
        conditions = None

    return ConditionResult(
        conditions=conditions,
        max_discount_amount=max_discount,
        min_order_amount=min_order,
    )
