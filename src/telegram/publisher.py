from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from sqlalchemy.exc import IntegrityError

from src.modules.offers.models import Offer, Publication
from src.shared.db import create_session
from src.telegram.render import offer_keyboard, render_offer_caption


@dataclass(frozen=True, slots=True)
class PublishResult:
    offer_id: int
    channel_id: str
    status: str
    publication_id: int | None = None
    telegram_message_id: str | None = None
    error: str | None = None


def _reserve_publication(offer_id: int, channel_id: str) -> tuple[Offer | None, Publication | None, str | None]:
    with create_session() as session:
        offer = session.get(Offer, offer_id)
        if offer is None:
            return None, None, "offer_not_found"
        if offer.status != "ready":
            return offer, None, f"offer_not_publishable:{offer.status}"

        existing = (
            session.query(Publication)
            .filter(Publication.offer_id == offer_id, Publication.channel_id == channel_id)
            .one_or_none()
        )
        if existing is not None:
            return offer, existing, "already_reserved"

        # "pending" is the durable reservation state defined by the schema.
        # Creating the row before the Telegram network call preserves the
        # conservative at-most-once publication guarantee.
        publication = Publication(offer_id=offer_id, channel_id=channel_id, status="pending")
        session.add(publication)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = (
                session.query(Publication)
                .filter(Publication.offer_id == offer_id, Publication.channel_id == channel_id)
                .one_or_none()
            )
            return offer, existing, "already_reserved"
        return offer, publication, None


def _mark_failed(publication_id: int, error: str) -> None:
    with create_session() as session:
        publication = session.get(Publication, publication_id)
        if publication is None:
            return
        publication.status = "failed"
        publication.error = error[:10000]
        session.commit()


def _mark_published(publication_id: int, offer_id: int, message_id: int) -> None:
    with create_session() as session:
        publication = session.get(Publication, publication_id)
        offer = session.get(Offer, offer_id)
        if publication is None:
            return
        publication.status = "published"
        publication.telegram_message_id = str(message_id)
        publication.published_at = datetime.now(UTC)
        publication.error = None
        if offer is not None:
            offer.status = "published"
        session.commit()


async def publish_offer(bot: Bot, *, offer_id: int, channel_id: str) -> PublishResult:
    offer, publication, reservation_error = _reserve_publication(offer_id, channel_id)
    if offer is None:
        return PublishResult(offer_id=offer_id, channel_id=channel_id, status="not_found", error=reservation_error)
    if reservation_error and reservation_error.startswith("offer_not_publishable:"):
        return PublishResult(
            offer_id=offer_id,
            channel_id=channel_id,
            status="not_publishable",
            error=reservation_error,
        )
    if reservation_error is not None:
        return PublishResult(
            offer_id=offer_id,
            channel_id=channel_id,
            status="duplicate",
            publication_id=publication.id if publication else None,
            telegram_message_id=publication.telegram_message_id if publication else None,
            error=reservation_error,
        )
    assert publication is not None

    caption = render_offer_caption(offer)
    reply_markup = offer_keyboard(offer)

    try:
        if offer.image_url:
            try:
                message = await bot.send_photo(
                    chat_id=channel_id,
                    photo=offer.image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except Exception:
                message = await bot.send_message(
                    chat_id=channel_id,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=False,
                )
        else:
            message = await bot.send_message(
                chat_id=channel_id,
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=False,
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _mark_failed(publication.id, error)
        return PublishResult(
            offer_id=offer_id,
            channel_id=channel_id,
            status="failed",
            publication_id=publication.id,
            error=error,
        )

    _mark_published(publication.id, offer_id, message.message_id)
    return PublishResult(
        offer_id=offer_id,
        channel_id=channel_id,
        status="published",
        publication_id=publication.id,
        telegram_message_id=str(message.message_id),
    )
