from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.modules.offers.models import Offer, Publication
from src.modules.publishing.filters import get_or_create_default_filter, update_default_filter
from src.shared.config import get_settings
from src.shared.db import create_session
from src.shared.logging import redact_secrets
from src.shared.runtime_paths import runtime_root
from src.telegram.autopost import run_autopost_cycle_async
from src.telegram.client import build_bot, resolve_telegram_route
from src.telegram.publisher import PublishResult, publish_offer


class TelegramE2EError(RuntimeError):
    pass


_FILTER_FIELDS = (
    "enabled",
    "min_discount_percent",
    "category",
    "subcategory",
    "offer_type",
    "merchant",
    "source_key",
    "city",
    "region",
    "max_posts_per_cycle",
)


class _ForcedFailureBot:
    """Duck-typed Bot that forces the publisher's real failed-ledger path."""

    async def send_photo(self, *args, **kwargs):
        raise RuntimeError("DP-WIN-002 forced publication failure")

    async def send_message(self, *args, **kwargs):
        raise RuntimeError("DP-WIN-002 forced publication failure")


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))


def _channel_fingerprint(channel_id: str) -> str:
    return hashlib.sha256(channel_id.encode("utf-8")).hexdigest()[:16]


def _snapshot_default_filter() -> dict:
    row = get_or_create_default_filter(min_discount_percent=get_settings().telegram_default_min_discount)
    return {field: getattr(row, field) for field in _FILTER_FIELDS}


def _restore_default_filter(snapshot: dict) -> None:
    update_default_filter(**snapshot)


def _create_probe_offer(*, label: str, merchant: str) -> int:
    marker = uuid4().hex
    with create_session() as session:
        offer = Offer(
            offer_type="discount",
            status="ready",
            title=f"DP-WIN-002 {label}",
            display_title=f"DP-WIN-002 · {label}",
            merchant=merchant,
            geo_scope="all_russia",
            conditions="Temporary Discount Parser acceptance probe.",
            discount_percent=Decimal("99"),
            currency="RUB",
            fingerprint=f"dp-win-002-{marker}",
        )
        session.add(offer)
        session.commit()
        session.refresh(offer)
        return int(offer.id)


def _publication_state(offer_id: int, channel_id: str) -> tuple[str | None, int | None]:
    with create_session() as session:
        publication = (
            session.query(Publication)
            .filter(Publication.offer_id == offer_id, Publication.channel_id == channel_id)
            .one_or_none()
        )
        if publication is None:
            return None, None
        return publication.status, int(publication.id)


def _delete_probe_offer(offer_id: int) -> None:
    with create_session() as session:
        offer = session.get(Offer, offer_id)
        if offer is not None:
            session.delete(offer)
            session.commit()


async def _delete_message_best_effort(bot, channel_id: str, message_id: str | None) -> bool:
    if not message_id:
        return False
    try:
        await bot.delete_message(chat_id=channel_id, message_id=int(message_id))
        return True
    except Exception:
        return False


def _require_published(result: PublishResult, scenario: str) -> None:
    if result.status != "published" or not result.telegram_message_id:
        raise TelegramE2EError(f"{scenario} did not publish: {result.status}: {result.error or ''}")


async def run_real_telegram_e2e_async() -> dict:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    channel_id = (settings.telegram_channel_id or "").strip()
    if not token or not channel_id:
        raise TelegramE2EError("Telegram bot token/channel are not configured in the installed runtime")

    started_at = datetime.now(UTC)
    evidence: dict = {
        "schema_version": 1,
        "task": "DP-WIN-002",
        "scenario": "real_telegram_e2e",
        "status": "RUNNING",
        "started_at": started_at.isoformat(),
        "network_route": resolve_telegram_route(),
        "channel_fingerprint": _channel_fingerprint(channel_id),
        "credentials_embedded": False,
    }
    created_offer_ids: list[int] = []
    message_ids: list[str] = []
    filter_snapshot: dict | None = None
    bot = build_bot(token)

    try:
        me = await bot.get_me()
        chat = await bot.get_chat(channel_id)
        member = await bot.get_chat_member(channel_id, me.id)
        member_status = _enum_value(member.status)
        can_post = getattr(member, "can_post_messages", None)
        if member_status not in {"administrator", "creator"}:
            raise TelegramE2EError(f"bot is not channel administrator/creator: {member_status}")
        if can_post is False:
            raise TelegramE2EError("bot administrator lacks can_post_messages")

        evidence["telegram_identity"] = {
            "bot_username": me.username,
            "bot_id": int(me.id),
            "chat_type": _enum_value(chat.type),
            "member_status": member_status,
            "can_post_messages": can_post,
            "get_me": "PASS",
            "get_chat": "PASS",
            "get_chat_member": "PASS",
        }

        manual_id = _create_probe_offer(label="manual publication", merchant="DP-WIN-002")
        created_offer_ids.append(manual_id)
        manual = await publish_offer(bot, offer_id=manual_id, channel_id=channel_id)
        _require_published(manual, "manual publication")
        message_ids.append(str(manual.telegram_message_id))
        evidence["manual_publication"] = {
            "status": "PASS",
            "publication_id": manual.publication_id,
            "telegram_message_id": manual.telegram_message_id,
        }

        retry_id = _create_probe_offer(label="failed retry", merchant="DP-WIN-002")
        created_offer_ids.append(retry_id)
        forced_failure = await publish_offer(_ForcedFailureBot(), offer_id=retry_id, channel_id=channel_id)
        failed_state, failed_publication_id = _publication_state(retry_id, channel_id)
        if forced_failure.status != "failed" or failed_state != "failed" or not failed_publication_id:
            raise TelegramE2EError("forced failure did not persist failed publication state")

        retry = await publish_offer(bot, offer_id=retry_id, channel_id=channel_id)
        _require_published(retry, "failed retry")
        retry_state, retry_publication_id = _publication_state(retry_id, channel_id)
        if retry_state != "published" or retry_publication_id != failed_publication_id:
            raise TelegramE2EError("retry did not reuse and publish the failed ledger reservation")
        message_ids.append(str(retry.telegram_message_id))
        evidence["failed_retry"] = {
            "status": "PASS",
            "forced_failure": "failed",
            "final_state": retry_state,
            "publication_id_reused": True,
            "telegram_message_id": retry.telegram_message_id,
        }

        filter_snapshot = _snapshot_default_filter()
        unique_merchant = f"DP-WIN-002-{uuid4().hex}"
        update_default_filter(
            enabled=True,
            min_discount_percent=Decimal("0"),
            category=None,
            subcategory=None,
            offer_type=None,
            merchant=unique_merchant,
            source_key=None,
            city=None,
            region=None,
            max_posts_per_cycle=1,
        )
        autopost_id = _create_probe_offer(label="autopost", merchant=unique_merchant)
        created_offer_ids.append(autopost_id)
        autopost_results = await run_autopost_cycle_async()
        matching = [item for item in autopost_results if item.offer_id == autopost_id]
        if len(matching) != 1 or len(autopost_results) != 1:
            raise TelegramE2EError(
                f"isolated autopost selected unexpected offers: total={len(autopost_results)} matching={len(matching)}"
            )
        autopost = matching[0]
        _require_published(autopost, "autopost")
        message_ids.append(str(autopost.telegram_message_id))
        evidence["autopost"] = {
            "status": "PASS",
            "selected_only_probe_offer": True,
            "telegram_message_id": autopost.telegram_message_id,
        }

        evidence["status"] = "PASS"
        return evidence
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["error"] = redact_secrets(f"{type(exc).__name__}: {exc}")
        return evidence
    finally:
        if filter_snapshot is not None:
            try:
                _restore_default_filter(filter_snapshot)
                evidence["filter_restored"] = True
            except Exception as exc:
                evidence["filter_restored"] = False
                evidence["filter_restore_error"] = redact_secrets(f"{type(exc).__name__}: {exc}")
                evidence["status"] = "FAIL"

        cleanup: list[dict] = []
        for message_id in message_ids:
            cleanup.append(
                {
                    "telegram_message_id": message_id,
                    "deleted": await _delete_message_best_effort(bot, channel_id, message_id),
                }
            )
        evidence["telegram_cleanup"] = cleanup

        for offer_id in reversed(created_offer_ids):
            try:
                _delete_probe_offer(offer_id)
            except Exception as exc:
                evidence.setdefault("db_cleanup_errors", []).append(
                    redact_secrets(f"offer {offer_id}: {type(exc).__name__}: {exc}")
                )
                evidence["status"] = "FAIL"

        evidence["database_probe_cleanup"] = "PASS" if not evidence.get("db_cleanup_errors") else "FAIL"
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        evidence["duration_seconds"] = round((datetime.now(UTC) - started_at).total_seconds(), 3)
        await bot.session.close()


def run_real_telegram_e2e(output: str | Path | None = None) -> dict:
    evidence = asyncio.run(run_real_telegram_e2e_async())
    destination = Path(output) if output else runtime_root() / "acceptance" / "dp-win-002-real-telegram-e2e.json"
    if not destination.is_absolute():
        destination = (runtime_root() / destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    evidence["evidence_path"] = str(destination)
    return evidence
