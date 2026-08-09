from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.modules.offers.models import Offer


MAX_TITLE_CHARS = 110
MAX_MERCHANT_CHARS = 80
MAX_CATEGORY_CHARS = 100
MAX_CONDITIONS_CHARS = 180
TARGET_CAPTION_CHARS = 650


def _money(value: Decimal | None, currency: str | None) -> str | None:
    if value is None:
        return None
    amount = f"{value:,.2f}".replace(",", " ").replace(".00", "")
    code = (currency or "RUB").upper()
    symbol = "₽" if code == "RUB" else code
    return f"{amount} {symbol}".strip()


def _date(value: datetime | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def _clip(value: str | None, *, limit: int) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (clipped or text[: limit - 1].rstrip()) + "…"


def _conditions(offer: Offer) -> str | None:
    parts: list[str] = []
    if offer.max_discount_amount is not None:
        parts.append(f"скидка не более {_money(offer.max_discount_amount, offer.currency)}")
    if offer.min_order_amount is not None:
        parts.append(f"заказ от {_money(offer.min_order_amount, offer.currency)}")
    explicit = _clip(offer.conditions, limit=MAX_CONDITIONS_CHARS)
    if explicit:
        normalized = explicit.casefold()
        structured = [part for part in parts if part.casefold() not in normalized]
        text = explicit + ("; " + "; ".join(structured) if structured else "")
        return _clip(text, limit=MAX_CONDITIONS_CHARS)
    return _clip("; ".join(parts), limit=MAX_CONDITIONS_CHARS)


def _discount_label(offer: Offer) -> str | None:
    if offer.discount_percent is not None:
        return f"{offer.discount_percent:g}%"
    if offer.discount_amount is not None:
        return _money(offer.discount_amount, offer.currency)
    return None


def _cashback_label(offer: Offer) -> str | None:
    if offer.cashback_percent is not None:
        return f"{offer.cashback_percent:g}%"
    if offer.cashback_amount is not None:
        return _money(offer.cashback_amount, offer.currency)
    return None


def _headline(offer: Offer) -> str:
    merchant = _clip(offer.merchant, limit=MAX_MERCHANT_CHARS)
    discount = _discount_label(offer)
    cashback = _cashback_label(offer)
    if merchant and discount:
        return _clip(f"{merchant} — скидка {discount}", limit=MAX_TITLE_CHARS) or "Скидка"
    if merchant and cashback:
        return _clip(f"{merchant} — кэшбэк {cashback}", limit=MAX_TITLE_CHARS) or "Кэшбэк"
    if merchant and offer.promo_code:
        return _clip(f"{merchant} — промокод", limit=MAX_TITLE_CHARS) or "Промокод"
    return _clip(offer.display_title or offer.title, limit=MAX_TITLE_CHARS) or "Предложение"


def _geo_label(offer: Offer) -> str:
    if offer.geo_scope == "all_russia":
        return "Вся Россия"
    geo_parts = [value for value in (offer.city, offer.region) if value]
    if geo_parts:
        return ", ".join(dict.fromkeys(geo_parts))
    return "Не указано"


def render_offer_caption(offer: Offer) -> str:
    """Render a compact, source-independent Telegram publication.

    Raw source description is deliberately excluded from the publication. It
    stays available for review/extraction, while Telegram always gets the same
    concise structured fields regardless of source verbosity.
    """
    lines: list[str] = [f"<b>🔥 {escape(_headline(offer))}</b>", ""]

    merchant = _clip(offer.merchant, limit=MAX_MERCHANT_CHARS)
    if merchant:
        lines.append(f"🏪 Поставщик: {escape(merchant)}")

    if offer.old_price is not None and offer.new_price is not None:
        old_price = escape(_money(offer.old_price, offer.currency) or "")
        new_price = escape(_money(offer.new_price, offer.currency) or "")
        lines.append(f"💰 Цена: <s>{old_price}</s> → <b>{new_price}</b>")

    discount = _discount_label(offer)
    if discount:
        lines.append(f"💸 Скидка: <b>{escape(discount)}</b>")

    cashback = _cashback_label(offer)
    if cashback:
        lines.append(f"💳 Кэшбэк: <b>{escape(cashback)}</b>")

    if offer.delivery_price is not None:
        lines.append(f"🚚 Доставка: <b>{escape(_money(offer.delivery_price, offer.currency) or '')}</b>")

    if offer.category:
        category = _clip(offer.category, limit=MAX_CATEGORY_CHARS) or ""
        if offer.subcategory:
            subcategory = _clip(offer.subcategory, limit=MAX_CATEGORY_CHARS) or ""
            category = _clip(f"{category} → {subcategory}", limit=MAX_CATEGORY_CHARS) or category
        lines.append(f"📂 Категория: {escape(category)}")

    condition_text = _conditions(offer)
    if condition_text:
        lines.append(f"📌 Условия: {escape(condition_text)}")

    lines.append(f"📍 ГЕО: {escape(_geo_label(offer))}")

    if offer.valid_until:
        lines.append(f"⏳ До: {_date(offer.valid_until)}")

    if offer.promo_code:
        lines.append(f"🎁 Промокод: <code>{escape(_clip(offer.promo_code, limit=64) or '')}</code>")

    caption = "\n".join(lines)
    # The individual field limits above keep normal posts well below Telegram's
    # caption limits and, more importantly, below our compact UX target.
    return caption


def offer_keyboard(offer: Offer) -> InlineKeyboardMarkup | None:
    url = (offer.canonical_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 Перейти к предложению", url=url)]])
