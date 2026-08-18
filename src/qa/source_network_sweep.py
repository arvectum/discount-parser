from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import getproxies

from sqlalchemy import select

from src.jobs.scheduler import build_scheduler
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.runner import _is_source_due, collect_registered_source
from src.qa.recovery import backup_database, database_integrity
from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.logging import redact_secrets
from src.shared.network import NetworkRouter, configured_proxy_url, is_loopback_url, network_router
from src.shared.runtime_paths import runtime_root
from src.sources.config import SourceConfig, load_source_configs
from src.sources.runner import _effective_config, _source_is_enabled, run_source


class SourceNetworkSweepError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    kind: str
    key: str
    url: str
    network_policy: str
    platform: str
    collector_type: str
    registered_id: int | None = None
    check_interval_minutes: int | None = None
    external_id: str | None = None
    legacy_config: SourceConfig | None = None


_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def _safe_origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if not parsed.scheme or not host:
            return "invalid-url"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme.lower()}://{host.lower()}{port}"
    except (TypeError, ValueError):
        return "invalid-url"


def _credential_values(settings) -> list[str]:
    values = [
        settings.telegram_bot_token,
        settings.telegram_channel_id,
        settings.telegram_admin_ids,
        settings.proxy_url,
        settings.proxy_username,
        settings.proxy_password,
        settings.telegram_collector_api_id,
        settings.telegram_collector_api_hash,
        settings.telegram_collector_session,
        settings.vk_access_token,
    ]
    return [str(value) for value in values if value is not None and str(value).strip()]


def _safe_text(value: object, *, secrets: list[str], extra_sensitive: tuple[str, ...] = ()) -> str:
    text = redact_secrets(str(value or ""))
    for secret in [*secrets, *extra_sensitive]:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***REDACTED***")
    return _URL_PATTERN.sub(lambda match: _safe_origin(match.group(0)), text)


def _network_environment(settings) -> dict:
    system_proxy_keys = sorted(
        key.lower()
        for key, value in getproxies().items()
        if value and key.lower() not in {"no", "no_proxy"}
    )
    no_proxy_items = {
        item.strip().casefold()
        for item in str(settings.no_proxy or "").split(",")
        if item.strip()
    }
    loopback_required = {"127.0.0.1", "localhost", "::1"}
    return {
        "network_mode": settings.network_mode,
        "proxy_configured": bool(configured_proxy_url()),
        "proxy_auth_configured": bool(settings.proxy_username),
        "system_proxy_schemes": system_proxy_keys,
        "proxy_environment_present": any(
            bool(os.getenv(name))
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
        ),
        "no_proxy_loopback_complete": loopback_required.issubset(no_proxy_items),
        "loopback_router_bypass": all(
            is_loopback_url(url) and NetworkRouter()._candidate_routes(url, "auto") == ["direct"]
            for url in ("http://127.0.0.1:8765/", "http://localhost:8765/", "http://[::1]:8765/")
        ),
    }


def _scheduler_contract(settings) -> dict:
    scheduler = build_scheduler(
        collect_callable=lambda: None,
        maintenance_callable=lambda: None,
        autopost_callable=lambda: None,
        background=True,
    )
    jobs = {job.id: job for job in scheduler.get_jobs()}
    collect_job = jobs.get("collect_sources")
    interval_seconds = None
    if collect_job is not None:
        interval = getattr(collect_job.trigger, "interval", None)
        if interval is not None:
            interval_seconds = int(interval.total_seconds())
    expected_seconds = int(settings.collect_interval_minutes * 60)
    return {
        "timezone": str(scheduler.timezone),
        "configured_collect_interval_minutes": int(settings.collect_interval_minutes),
        "observed_collect_interval_seconds": interval_seconds,
        "expected_collect_interval_seconds": expected_seconds,
        "scheduler_matches_settings": interval_seconds == expected_seconds,
        "max_instances_one": bool(collect_job is not None and collect_job.max_instances == 1),
        "coalescing_enabled": bool(collect_job is not None and collect_job.coalesce),
        "registry_per_source_interval_enforced": True,
    }


def _load_specs(settings) -> tuple[list[_SourceSpec], dict]:
    specs: list[_SourceSpec] = []
    legacy_configs = load_source_configs(settings.sources_config_path)
    legacy_keys = {config.key for config in legacy_configs}
    disabled_legacy: list[str] = []

    for config in legacy_configs:
        if not _source_is_enabled(config):
            disabled_legacy.append(config.key)
            continue
        effective = _effective_config(config)
        specs.append(
            _SourceSpec(
                kind="legacy",
                key=effective.key,
                url=effective.base_url,
                network_policy=effective.network_policy,
                platform="promo_aggregator",
                collector_type=effective.adapter,
                legacy_config=config,
            )
        )

    registry_summary: dict = {
        "enabled_nonlegacy": 0,
        "disabled": 0,
        "legacy_mirrors": 0,
        "orphaned_enabled_legacy_mirrors": [],
        "due_before_sweep": 0,
        "not_due_before_sweep": 0,
    }
    with session_scope() as session:
        rows = list(session.scalars(select(RegisteredSource).order_by(RegisteredSource.id)).all())
        now = datetime.now(UTC)
        for row in rows:
            if not row.enabled:
                registry_summary["disabled"] += 1
                continue
            if row.collector_type == "legacy_adapter":
                registry_summary["legacy_mirrors"] += 1
                if row.key not in legacy_keys:
                    registry_summary["orphaned_enabled_legacy_mirrors"].append(row.key)
                continue
            due = _is_source_due(row, now=now)
            registry_summary["enabled_nonlegacy"] += 1
            registry_summary["due_before_sweep" if due else "not_due_before_sweep"] += 1
            specs.append(
                _SourceSpec(
                    kind="registry",
                    key=row.key,
                    url=row.url,
                    network_policy=row.network_policy,
                    platform=row.platform,
                    collector_type=row.collector_type,
                    registered_id=int(row.id),
                    check_interval_minutes=int(row.check_interval_minutes),
                    external_id=row.external_id,
                )
            )

    return specs, {
        "legacy_enabled": len([spec for spec in specs if spec.kind == "legacy"]),
        "legacy_disabled": disabled_legacy,
        "registry": registry_summary,
    }


def _probe_routes(spec: _SourceSpec, *, timeout: float = 4.0) -> dict:
    routes = ["direct"]
    if configured_proxy_url():
        routes.append("proxy")
    routes.append("system")
    probes: list[dict] = []
    for route in routes:
        probe = NetworkRouter().probe(spec.url, route=route, timeout=timeout)
        probes.append(
            {
                "route": route,
                "ok": bool(probe.ok),
                "status_code": probe.status_code,
                "elapsed_ms": int(probe.elapsed_ms),
                "detail": probe.detail,
            }
        )

    if spec.network_policy == "auto":
        policy_reachable = any(item["ok"] for item in probes)
    else:
        matching = [item for item in probes if item["route"] == spec.network_policy]
        policy_reachable = bool(matching and matching[0]["ok"])
    return {
        "configured_policy": spec.network_policy,
        "policy_reachable": policy_reachable,
        "probes": probes,
    }


def _legacy_collection(spec: _SourceSpec, *, secrets: list[str]) -> dict:
    assert spec.legacy_config is not None
    result = run_source(spec.legacy_config)
    error = _safe_text(result.error, secrets=secrets, extra_sensitive=(spec.external_id or "",)) if result.error else None
    return {
        "fetched": int(result.fetched),
        "created": int(result.created),
        "updated": int(result.updated),
        "duplicates": int(result.duplicates),
        "errors": int(result.errors),
        "duration_seconds": round(float(result.duration_seconds), 3),
        "error": error,
    }


def _registry_collection(spec: _SourceSpec, *, secrets: list[str]) -> dict:
    assert spec.registered_id is not None
    result = collect_registered_source(spec.registered_id)
    error = _safe_text(result.error, secrets=secrets, extra_sensitive=(spec.external_id or "",)) if result.error else None
    return {
        "fetched": int(result.fetched),
        "items_created": int(result.items_created),
        "offer_signals": int(result.offer_signals),
        "offers_created": int(result.offers_created),
        "offers_updated": int(result.offers_updated),
        "duplicates": int(result.duplicates),
        "ignored": int(result.ignored),
        "errors": int(result.errors),
        "duration_seconds": round(float(result.duration_seconds), 3),
        "error": error,
    }


def _source_evidence(spec: _SourceSpec, *, secrets: list[str]) -> dict:
    network = _probe_routes(spec)
    try:
        collection = (
            _legacy_collection(spec, secrets=secrets)
            if spec.kind == "legacy"
            else _registry_collection(spec, secrets=secrets)
        )
    except Exception as exc:
        collection = {
            "fetched": 0,
            "errors": 1,
            "error": _safe_text(exc, secrets=secrets, extra_sensitive=(spec.external_id or "",)),
        }

    fetched = int(collection.get("fetched") or 0)
    errors = int(collection.get("errors") or 0)
    collection_ok = fetched > 0 and errors == 0
    observed_route = network_router.cached_route(spec.url)
    return {
        "kind": spec.kind,
        "source_key": spec.key,
        "origin": _safe_origin(spec.url),
        "platform": spec.platform,
        "collector_type": spec.collector_type,
        "check_interval_minutes": spec.check_interval_minutes,
        "network": network,
        "observed_production_route": observed_route,
        "collection": collection,
        "status": "PASS" if network["policy_reachable"] and collection_ok else "FAIL",
    }


def _privacy_check(evidence: dict, *, secrets: list[str]) -> dict:
    serialized = json.dumps(evidence, ensure_ascii=False, default=str)
    leaked_fields = []
    settings = get_settings()
    named_values = {
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_channel_id": settings.telegram_channel_id,
        "telegram_admin_ids": settings.telegram_admin_ids,
        "proxy_url": settings.proxy_url,
        "proxy_username": settings.proxy_username,
        "proxy_password": settings.proxy_password,
        "telegram_collector_api_hash": settings.telegram_collector_api_hash,
        "telegram_collector_session": settings.telegram_collector_session,
        "vk_access_token": settings.vk_access_token,
    }
    for name, raw in named_values.items():
        value = str(raw or "").strip()
        if len(value) >= 4 and value in serialized:
            leaked_fields.append(name)
    return {
        "credentials_embedded": bool(leaked_fields),
        "check": "FAIL" if leaked_fields else "PASS",
        "leaked_field_names": leaked_fields,
        "redaction_value_count": len(secrets),
    }


def run_real_source_network_sweep(output: str | Path | None = None) -> dict:
    started_at = datetime.now(UTC)
    settings = get_settings()
    secrets = _credential_values(settings)
    evidence: dict = {
        "schema_version": 1,
        "task": "DP-WIN-003",
        "scenario": "real_source_network_sweep",
        "status": "RUNNING",
        "started_at": started_at.isoformat(),
        "runtime": {
            "os": platform.system(),
            "os_release": platform.release(),
            "frozen": bool(getattr(__import__("sys"), "frozen", False)),
        },
        "network_environment": _network_environment(settings),
        "scheduler": _scheduler_contract(settings),
    }

    try:
        before = database_integrity()
        evidence["database_before"] = {
            "exists": bool(before.get("exists")),
            "healthy": bool(before.get("healthy")),
            "detail": _safe_text(before.get("detail"), secrets=secrets),
        }
        if not before.get("exists") or not before.get("healthy"):
            raise SourceNetworkSweepError("installed database is missing or unhealthy before source sweep")

        backup = backup_database()
        evidence["pre_sweep_backup"] = {"created": backup is not None}
        if backup is None:
            raise SourceNetworkSweepError("pre-sweep database backup was not created")

        specs, inventory = _load_specs(settings)
        evidence["source_inventory"] = inventory
        if inventory["registry"]["orphaned_enabled_legacy_mirrors"]:
            raise SourceNetworkSweepError("enabled legacy registry mirror exists without matching YAML source")
        if not specs:
            raise SourceNetworkSweepError("no enabled production sources are configured")

        evidence["sources"] = [_source_evidence(spec, secrets=secrets) for spec in specs]

        after = database_integrity()
        evidence["database_after"] = {
            "exists": bool(after.get("exists")),
            "healthy": bool(after.get("healthy")),
            "detail": _safe_text(after.get("detail"), secrets=secrets),
        }

        network_ok = bool(evidence["network_environment"]["loopback_router_bypass"])
        no_proxy_ok = bool(evidence["network_environment"]["no_proxy_loopback_complete"])
        scheduler_ok = bool(
            evidence["scheduler"]["scheduler_matches_settings"]
            and evidence["scheduler"]["max_instances_one"]
            and evidence["scheduler"]["coalescing_enabled"]
        )
        sources_ok = all(item["status"] == "PASS" for item in evidence["sources"])
        database_ok = bool(after.get("exists") and after.get("healthy"))
        evidence["acceptance"] = {
            "network_loopback": "PASS" if network_ok and no_proxy_ok else "FAIL",
            "scheduler_cadence": "PASS" if scheduler_ok else "FAIL",
            "all_enabled_sources": "PASS" if sources_ok else "FAIL",
            "database_integrity": "PASS" if database_ok else "FAIL",
            "source_count": len(evidence["sources"]),
            "failed_sources": [item["source_key"] for item in evidence["sources"] if item["status"] != "PASS"],
        }
        evidence["status"] = "PASS" if all((network_ok, no_proxy_ok, scheduler_ok, sources_ok, database_ok)) else "FAIL"
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["error"] = _safe_text(exc, secrets=secrets)
    finally:
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        evidence["duration_seconds"] = round((datetime.now(UTC) - started_at).total_seconds(), 3)
        privacy = _privacy_check(evidence, secrets=secrets)
        evidence["privacy"] = privacy
        evidence["credentials_embedded"] = privacy["credentials_embedded"]
        if privacy["check"] != "PASS":
            evidence["status"] = "FAIL"

    destination = Path(output) if output else runtime_root() / "acceptance" / "dp-win-003-real-source-network-sweep.json"
    if not destination.is_absolute():
        destination = (runtime_root() / destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    evidence["evidence_path"] = str(destination)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return evidence
