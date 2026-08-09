from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.modules.offers.models import Offer


def _money(value: Decimal | None, currency: str | None) -> str | None:
    if value is None:
        return None
    amount = f"{value:,.2f}".replace(",", " ").replace(".00", "")
    code = (currency or "RUB").upper()
    symbol = "₽" if code == "RUB" else code
    return f"{amount} {symbol}".strip()


def _date(value: datetime | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def _summary(value: str | None, *, limit: int = 420) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return clipped + "…"


def _conditions(offer: Offer) -> str | None:
    parts: list[str] = []
    if offer.max_discount_amount is not None:
        parts.append(f"скидка не более {_money(offer.max_discount_amount, offer.currency)}")
    if offer.min_order_amount is not None:
        parts.append(f"заказ от {_money(offer.min_order_amount, offer.currency)}")
    explicit = _summary(offer.conditions, limit=320)
    if explicit:
        normalized = explicit.casefold()
        structured = [part for part in parts if part.casefold() not in normalized]
        if structured:
            return explicit + "; " + "; ".join(structured)
        return explicit
    return "; ".join(parts) or None


def render_offer_caption(offer: Offer) -> str:
    lines: list[str] = []
    title = escape(offer.display_title or offer.title)
    lines.append(f"<b>🔥 {title}</b>")

    summary = _summary(offer.description)
    if summary and summary.casefold() != (offer.display_title or offer.title).strip().casefold():
        lines.append(f"📝 {escape(summary)}")

    benefit_lines: list[str] = []
    if offer.old_price is not None and offer.new_price is not None:
        old_price = escape(_money(offer.old_price, offer.currency) or "")
        new_price = escape(_money(offer.new_price, offer.currency) or "")
        benefit_lines.append(f"💰 Цена: <s>{old_price}</s> → <b>{new_price}</b>")
    if offer.discount_percent is not None:
        benefit_lines.append(f"💸 Скидка: <b>{offer.discount_percent:g}%</b>")
    elif offer.discount_amount is not None:
        benefit_lines.append(f"💸 Скидка: <b>{escape(_money(offer.discount_amount, offer.currency) or '')}</b>")
    if offer.cashback_percent is not None:
        benefit_lines.append(f"💳 Кэшбэк: <b>{offer.cashback_percent:g}%</b>")
    elif offer.cashback_amount is not None:
        benefit_lines.append(f"💳 Кэшбэк: <b>{escape(_money(offer.cashback_amount, offer.currency) or '')}</b>")
    if offer.delivery_price is not None:
        benefit_lines.append(f"🚚 Доставка: <b>{escape(_money(offer.delivery_price, offer.currency) or '')}</b>")
    lines.extend(benefit_lines)

    if offer.promo_code:
        lines.append(f"🎁 Промокод: <code>{escape(offer.promo_code)}</code>")

    condition_text = _conditions(offer)
    if condition_text:
        lines.append(f"📌 Условия: {escape(condition_text)}")

    if offer.geo_scope == "all_russia":
        lines.append("📍 Вся Россия")
    else:
        geo_parts = [value for value in (offer.city, offer.region) if value]
        if geo_parts:
            lines.append(f"📍 {escape(', '.join(dict.fromkeys(geo_parts)))}")
        elif offer.geo_scope == "unknown":
            lines.append("📍 ГЕО не указано")

    if offer.merchant:
        lines.append(f"🏪 Магазин: {escape(offer.merchant)}")
    if offer.category:
        category = escape(offer.category)
        if offer.subcategory:
            category += f" → {escape(offer.subcategory)}"
        lines.append(f"📂 {category}")
    if offer.valid_until:
        lines.append(f"⏳ Действует до {_date(offer.valid_until)}")

    return "\n\n".join(lines)


def offer_keyboard(offer: Offer) -> InlineKeyboardMarkup | None:
    url = (offer.canonical_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 Перейти к предложению", url=url)]])
