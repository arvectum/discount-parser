from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.modules.offers.models import Offer


def _money(value: Decimal | None, currency: str) -> str | None:
    if value is None:
        return None
    amount = f"{value:,.2f}".replace(",", " ").replace(".00", "")
    symbol = "₽" if currency.upper() == "RUB" else currency.upper()
    return f"{amount} {symbol}".strip()


def _date(value: datetime | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def render_offer_caption(offer: Offer) -> str:
    lines: list[str] = []
    title = escape(offer.display_title or offer.title)
    lines.append(f"<b>🔥 {title}</b>")

    if offer.old_price is not None and offer.new_price is not None:
        lines.append(f"💰 <s>{escape(_money(offer.old_price, offer.currency) or '')}</s> → <b>{escape(_money(offer.new_price, offer.currency) or '')}</b>")
    elif offer.discount_percent is not None:
        lines.append(f"💸 Скидка: <b>{offer.discount_percent:g}%</b>")
    elif offer.discount_amount is not None:
        lines.append(f"💸 Скидка: <b>{escape(_money(offer.discount_amount, offer.currency) or '')}</b>")
    elif offer.cashback_percent is not None:
        lines.append(f"💳 Кэшбэк: <b>{offer.cashback_percent:g}%</b>")
    elif offer.cashback_amount is not None:
        lines.append(f"💳 Кэшбэк: <b>{escape(_money(offer.cashback_amount, offer.currency) or '')}</b>")
    elif offer.delivery_price is not None:
        lines.append(f"🚚 Доставка: <b>{escape(_money(offer.delivery_price, offer.currency) or '')}</b>")

    if offer.promo_code:
        lines.append(f"🎁 Промокод: <code>{escape(offer.promo_code)}</code>")
    if offer.merchant:
        lines.append(f"🏪 {escape(offer.merchant)}")
    if offer.category:
        category = escape(offer.category)
        if offer.subcategory:
            category += f" → {escape(offer.subcategory)}"
        lines.append(f"📂 {category}")
    if offer.valid_until:
        lines.append(f"⏳ До {_date(offer.valid_until)}")

    return "\n\n".join(lines)


def offer_keyboard(offer: Offer) -> InlineKeyboardMarkup | None:
    url = (offer.canonical_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👉 Перейти к предложению", url=url)]]
    )
