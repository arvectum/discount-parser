from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.modules.offers.models import Offer
from src.telegram.publication_format import PublicationFormat, load_publication_format


MAX_TITLE_CHARS = 110
MAX_MERCHANT_CHARS = 80
MAX_CATEGORY_CHARS = 100
MAX_CONDITIONS_CHARS = 180


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
    explicit = _clip(offer.conditions, limit=MAX_CONDITIONS_CHARS)
    if explicit:
        return explicit
    parts: list[str] = []
    if offer.min_order_amount is not None:
        parts.append(f"заказ от {_money(offer.min_order_amount, offer.currency)}")
    if offer.max_discount_amount is not None:
        parts.append(f"скидка не более {_money(offer.max_discount_amount, offer.currency)}")
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
    return _clip(offer.display_title or offer.title, limit=MAX_TITLE_CHARS) or "Предложение"


def _geo_label(offer: Offer) -> str:
    if offer.geo_scope == "all_russia":
        return "Вся Россия"
    geo_parts = [value for value in (offer.city, offer.region) if value]
    if geo_parts:
        return _clip(", ".join(dict.fromkeys(geo_parts)), limit=100) or "Не указано"
    return "Не указано"


def _field_line(key: str, offer: Offer) -> str | None:
    if key == "merchant":
        merchant = _clip(offer.merchant, limit=MAX_MERCHANT_CHARS)
        return f"🏪 Поставщик: {escape(merchant)}" if merchant else None
    if key == "price" and offer.old_price is not None and offer.new_price is not None:
        old_price = escape(_money(offer.old_price, offer.currency) or "")
        new_price = escape(_money(offer.new_price, offer.currency) or "")
        return f"💰 Цена: <s>{old_price}</s> → <b>{new_price}</b>"
    if key == "discount":
        discount = _discount_label(offer)
        return f"💸 Скидка: <b>{escape(discount)}</b>" if discount else None
    if key == "cashback":
        cashback = _cashback_label(offer)
        return f"💳 Кэшбэк: <b>{escape(cashback)}</b>" if cashback else None
    if key == "delivery" and offer.delivery_price is not None:
        return f"🚚 Доставка: <b>{escape(_money(offer.delivery_price, offer.currency) or '')}</b>"
    if key == "category" and offer.category:
        category = _clip(offer.category, limit=MAX_CATEGORY_CHARS) or ""
        if offer.subcategory:
            subcategory = _clip(offer.subcategory, limit=MAX_CATEGORY_CHARS) or ""
            category = _clip(f"{category} → {subcategory}", limit=MAX_CATEGORY_CHARS) or category
        return f"📂 Категория: {escape(category)}"
    if key == "conditions":
        condition_text = _conditions(offer)
        return f"📌 Условия: {escape(condition_text)}" if condition_text else None
    if key == "geo":
        return f"📍 ГЕО: {escape(_geo_label(offer))}"
    if key == "valid_until" and offer.valid_until:
        return f"⏳ До: {_date(offer.valid_until)}"
    if key == "promo_code" and offer.promo_code:
        return f"🎁 Промокод: <code>{escape(_clip(offer.promo_code, limit=64) or '')}</code>"
    return None


def render_offer_caption(offer: Offer, publication_format: PublicationFormat | None = None) -> str:
    """Render a compact source-independent Telegram publication.

    Raw source description is deliberately excluded. The visible field set and
    its order come from customer-owned publication format settings; passing an
    explicit PublicationFormat is useful for previews and deterministic tests.
    """
    current_format = (publication_format or load_publication_format()).normalized()
    lines: list[str] = [f"<b>🔥 {escape(_headline(offer))}</b>", ""]
    for key in current_format.order:
        if key not in current_format.enabled:
            continue
        line = _field_line(key, offer)
        if line:
            lines.append(line)
    return "\n".join(lines)


def offer_keyboard(offer: Offer) -> InlineKeyboardMarkup | None:
    url = (offer.canonical_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 Перейти к предложению", url=url)]])
