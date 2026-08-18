from __future__ import annotations

from pathlib import Path

from src.qa import telegram_e2e


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "src" / "qa" / "telegram_e2e.py"
WORKER = ROOT / "src" / "worker_entry.py"


def test_channel_fingerprint_does_not_expose_channel_identifier() -> None:
    channel = "@private-acceptance-channel"
    fingerprint = telegram_e2e._channel_fingerprint(channel)
    assert fingerprint != channel
    assert len(fingerprint) == 16
    assert channel not in fingerprint


def test_safe_error_redacts_exact_runtime_token_and_channel() -> None:
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    channel = "@private-acceptance-channel"
    error = RuntimeError(f"Telegram failed for {channel} with token {token}")
    rendered = telegram_e2e._safe_error(error, token=token, channel_id=channel)
    assert token not in rendered
    assert channel not in rendered
    assert "REDACTED" in rendered


def test_real_e2e_contract_covers_identity_manual_retry_autopost_and_cleanup() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    required = (
        "await bot.get_me()",
        "await bot.get_chat(channel_id)",
        "await bot.get_chat_member(channel_id, me.id)",
        "can_post_messages",
        "manual publication",
        "_ForcedFailureBot()",
        "publication_id_reused",
        "run_autopost_cycle_async()",
        "selected_only_probe_offer",
        "_restore_default_filter(filter_snapshot)",
        "_delete_probe_offer(offer_id)",
        "delete_message",
        "credentials_embedded\": False",
        "_safe_error(exc, token=token, channel_id=channel_id)",
    )
    for token in required:
        assert token in source


def test_worker_exposes_telegram_e2e_command() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert "if command_name == 'telegram-e2e':" in source
    assert "return telegram_e2e()" in source
    assert "run_real_telegram_e2e(output)" in source
