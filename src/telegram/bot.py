from __future__ import annotations

import asyncio
from decimal import Decimal

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from src.jobs.status import get_source_run_statuses
from src.modules.offers.models import Offer
from src.modules.publishing.filters import get_or_create_default_filter, update_default_filter
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import create_session
from src.telegram.publisher import publish_offer
from src.telegram.render import render_offer_caption

router = Router(name="discount-parser-admin")


def _is_admin(user_id: int | None) -> bool:
    settings = get_settings()
    admins = settings.telegram_admin_id_set
    return user_id is not None and (not admins or user_id in admins)


async def _deny_if_needed(event: Message | CallbackQuery) -> bool:
    user_id = event.from_user.id if event.from_user else None
    if _is_admin(user_id):
        return False
    if isinstance(event, CallbackQuery):
        await event.answer("Нет доступа", show_alert=True)
    else:
        await event.answer("Нет доступа")
    return True


def _preview_keyboard(offer_id: int, url: str | None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish:{offer_id}"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip:{offer_id}"),
        ],
        [InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"reject:{offer_id}")],
    ]
    if url and url.startswith(("http://", "https://")):
        rows.append([InlineKeyboardButton(text="🔗 Открыть", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_preview(message: Message, offer: Offer) -> None:
    caption = render_offer_caption(offer)
    keyboard = _preview_keyboard(offer.id, offer.canonical_url)
    if offer.image_url:
        try:
            await message.answer_photo(
                photo=offer.image_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass
    await message.answer(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def _queue(limit: int | None = None) -> list[Offer]:
    settings = get_settings()
    if not settings.telegram_channel_id:
        return []
    row = get_or_create_default_filter(min_discount_percent=settings.telegram_default_min_discount)
    criteria = PublishCriteria.from_filter(row)
    if limit is not None:
        criteria = PublishCriteria(
            min_discount_percent=criteria.min_discount_percent,
            category=criteria.category,
            subcategory=criteria.subcategory,
            offer_type=criteria.offer_type,
            merchant=criteria.merchant,
            source_key=criteria.source_key,
            limit=limit,
        )
    with create_session() as session:
        return list_publish_candidates(session, channel_id=settings.telegram_channel_id, criteria=criteria)


@router.message(Command("start"))
async def start_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    await message.answer(
        "Discount Parser\n\n"
        "/status — состояние системы\n"
        "/sources — источники\n"
        "/new — новые предложения\n"
        "/queue — очередь по фильтру\n"
        "/filter — минимальная скидка\n"
        "/autopost — автопубликация"
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    with create_session() as session:
        total = int(session.scalar(select(func.count()).select_from(Offer)) or 0)
        ready = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "ready")) or 0)
        review = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "needs_review")) or 0)
        published = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "published")) or 0)
        expired = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == "expired")) or 0)
    failed_sources = sum(1 for item in get_source_run_statuses() if item.last_status == "failed")
    await message.answer(
        f"Всего: {total}\n"
        f"Готово: {ready}\n"
        f"На проверке: {review}\n"
        f"Опубликовано: {published}\n"
        f"Истекло: {expired}\n"
        f"Источников с ошибкой: {failed_sources}"
    )


@router.message(Command("sources"))
async def sources_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    statuses = get_source_run_statuses()
    if not statuses:
        await message.answer("Источники ещё не запускались.")
        return
    lines = []
    for item in statuses:
        icon = "✅" if item.last_status in {"success", "partial"} else "❌" if item.last_status == "failed" else "⚪️"
        lines.append(f"{icon} {item.source_name}: {item.last_status or 'never'} · fetched {item.fetched_count}")
    await message.answer("\n".join(lines))


@router.message(Command("new"))
async def new_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    settings = get_settings()
    if not settings.telegram_channel_id:
        await message.answer("DP_TELEGRAM_CHANNEL_ID не настроен.")
        return
    with create_session() as session:
        offers = list_publish_candidates(
            session,
            channel_id=settings.telegram_channel_id,
            criteria=PublishCriteria(limit=5),
        )
    if not offers:
        await message.answer("Новых готовых предложений нет.")
        return
    for offer in offers:
        await _send_preview(message, offer)


@router.message(Command("queue"))
async def queue_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    offers = _queue(limit=5)
    if not offers:
        await message.answer("Очередь пуста или Telegram-канал не настроен.")
        return
    for offer in offers:
        await _send_preview(message, offer)


@router.message(Command("filter"))
async def filter_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    settings = get_settings()
    row = get_or_create_default_filter(min_discount_percent=settings.telegram_default_min_discount)
    current = row.min_discount_percent
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10%", callback_data="filter_min:10"),
                InlineKeyboardButton(text="20%", callback_data="filter_min:20"),
                InlineKeyboardButton(text="30%", callback_data="filter_min:30"),
                InlineKeyboardButton(text="50%", callback_data="filter_min:50"),
            ]
        ]
    )
    await message.answer(f"Минимальная скидка: {current or 0}%", reply_markup=keyboard)


@router.callback_query(F.data.startswith("filter_min:"))
async def filter_min_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    value = Decimal(callback.data.split(":", 1)[1])
    update_default_filter(min_discount_percent=value)
    await callback.answer(f"Фильтр: от {value:g}%")
    if callback.message:
        await callback.message.edit_text(f"Минимальная скидка: {value:g}%")


@router.message(Command("autopost"))
async def autopost_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    settings = get_settings()
    row = get_or_create_default_filter(min_discount_percent=settings.telegram_default_min_discount)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Включить", callback_data="autopost:on"),
                InlineKeyboardButton(text="⏸ Выключить", callback_data="autopost:off"),
            ]
        ]
    )
    await message.answer(f"Автопостинг: {'включён' if row.enabled else 'выключен'}", reply_markup=keyboard)


@router.callback_query(F.data.startswith("autopost:"))
async def autopost_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    enabled = callback.data.endswith(":on")
    update_default_filter(enabled=enabled)
    await callback.answer("Автопостинг включён" if enabled else "Автопостинг выключен")
    if callback.message:
        await callback.message.edit_text(f"Автопостинг: {'включён' if enabled else 'выключен'}")


@router.callback_query(F.data.startswith("publish:"))
async def publish_callback(callback: CallbackQuery, bot: Bot) -> None:
    if await _deny_if_needed(callback):
        return
    settings = get_settings()
    if not settings.telegram_channel_id:
        await callback.answer("Канал не настроен", show_alert=True)
        return
    offer_id = int(callback.data.split(":", 1)[1])
    result = await publish_offer(bot, offer_id=offer_id, channel_id=settings.telegram_channel_id)
    await callback.answer(
        "Опубликовано" if result.status == "published" else f"Статус: {result.status}",
        show_alert=result.status not in {"published", "duplicate"},
    )
    if callback.message and result.status == "published":
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("skip:"))
async def skip_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    await callback.answer("Пропущено")
    if callback.message:
        await callback.message.delete()


@router.callback_query(F.data.startswith("reject:"))
async def reject_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    offer_id = int(callback.data.split(":", 1)[1])
    with create_session() as session:
        offer = session.get(Offer, offer_id)
        if offer is not None and offer.status in {"new", "ready", "needs_review"}:
            offer.status = "rejected"
            session.commit()
    await callback.answer("Отклонено")
    if callback.message:
        await callback.message.delete()


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_bot_async() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("DP_TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = build_dispatcher()
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def run_bot() -> None:
    asyncio.run(run_bot_async())
