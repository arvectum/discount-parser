from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.modules.source_registry import runner as registry_runner
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.runner import RegistryRunResult, _is_source_due
from src.qa import source_network_sweep
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.shared.network import NetworkRouter


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "worker_entry.py"
HARNESS = ROOT / "src" / "qa" / "source_network_sweep.py"


@pytest.fixture
def registry_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'dp-win-003.db'}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def _registered_source(*, key: str, last_checked_at: datetime | None, interval: int = 120) -> RegisteredSource:
    return RegisteredSource(
        key=key,
        name=key,
        platform="website",
        source_type="discount_page",
        url=f"https://{key}.example.test/promos?token=private",
        collector_type="generic_web",
        network_policy="auto",
        priority=50,
        trust_level="official",
        check_interval_minutes=interval,
        enabled=True,
        last_checked_at=last_checked_at,
    )


def test_safe_origin_strips_credentials_path_and_query() -> None:
    value = source_network_sweep._safe_origin("https://user:pass@example.test:8443/private/path?token=secret")
    assert value == "https://example.test:8443"
    assert "user" not in value
    assert "private" not in value
    assert "secret" not in value


def test_safe_text_redacts_credentials_and_url_details() -> None:
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    channel = "private_channel"
    rendered = source_network_sweep._safe_text(
        f"failed token={token} https://t.me/s/{channel}?auth=secret",
        secrets=[token],
        extra_sensitive=(channel,),
    )
    assert token not in rendered
    assert channel not in rendered
    assert "auth=secret" not in rendered
    assert "https://t.me" in rendered


def test_registry_due_contract_handles_aware_and_naive_timestamps() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    due = _registered_source(key="due", last_checked_at=now - timedelta(minutes=121))
    not_due = _registered_source(key="not-due", last_checked_at=(now - timedelta(minutes=30)).replace(tzinfo=None))
    never = _registered_source(key="never", last_checked_at=None)

    assert _is_source_due(due, now=now) is True
    assert _is_source_due(not_due, now=now) is False
    assert _is_source_due(never, now=now) is True


def test_scheduled_registry_batch_skips_not_due_but_targeted_run_is_immediate(
    registry_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    with create_session() as session:
        due = _registered_source(key="due", last_checked_at=now - timedelta(hours=3))
        not_due = _registered_source(key="not-due", last_checked_at=now - timedelta(minutes=5))
        session.add_all([due, not_due])
        session.commit()

    calls: list[int] = []

    def fake_collect(source_id: int) -> RegistryRunResult:
        calls.append(source_id)
        return RegistryRunResult(source_key=str(source_id), fetched=1)

    monkeypatch.setattr(registry_runner, "collect_registered_source", fake_collect)

    scheduled = registry_runner.collect_registered_sources()
    assert len(scheduled) == 1
    assert len(calls) == 1

    calls.clear()
    targeted = registry_runner.collect_registered_sources(only_key="not-due")
    assert len(targeted) == 1
    assert len(calls) == 1


def test_network_router_exposes_route_name_without_proxy_details() -> None:
    router = NetworkRouter()
    router.remember("https://example.test/private?token=secret", "direct", ttl_seconds=60)
    assert router.cached_route("https://example.test/other") == "direct"
    assert router.cached_route("http://127.0.0.1:8765/") == "direct"


def test_scheduler_contract_matches_configured_collection_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DP_COLLECT_INTERVAL_MINUTES", "37")
    monkeypatch.setenv("DP_TIMEZONE", "UTC")
    get_settings.cache_clear()
    try:
        contract = source_network_sweep._scheduler_contract(get_settings())
    finally:
        get_settings.cache_clear()
    assert contract["configured_collect_interval_minutes"] == 37
    assert contract["observed_collect_interval_seconds"] == 37 * 60
    assert contract["scheduler_matches_settings"] is True
    assert contract["max_instances_one"] is True
    assert contract["coalescing_enabled"] is True


def test_dp_win_003_contract_covers_real_collection_network_backup_cadence_and_privacy() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    required = (
        "backup_database()",
        "run_source(spec.legacy_config)",
        "collect_registered_source(spec.registered_id)",
        "NetworkRouter().probe",
        "observed_production_route",
        "scheduler_matches_settings",
        "registry_per_source_interval_enforced",
        "no_proxy_loopback_complete",
        "database_integrity()",
        "credentials_embedded",
        "dp-win-003-real-source-network-sweep.json",
    )
    for token in required:
        assert token in source


def test_worker_exposes_source_network_sweep_command() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert "if command_name == 'source-network-sweep':" in source
    assert "return source_network_sweep()" in source
    assert "run_real_source_network_sweep(output)" in source
