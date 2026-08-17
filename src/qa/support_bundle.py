from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.qa.doctor import build_doctor_report
from src.qa.operational_status import build_operational_status
from src.qa.report import build_smoke_report
from src.shared.config import get_settings
from src.shared.logging import redact_secrets
from src.shared.runtime_paths import env_path, runtime_root


_MAX_LOG_BYTES = 2 * 1024 * 1024
_LOG_NAMES = ("app.log", "app.log.1", "app.log.2", "app.log.3", "app.log.4", "app.log.5")
_SECRET_SETTING_NAMES = {
    "telegram_bot_token",
    "telegram_channel_id",
    "telegram_admin_ids",
    "proxy_url",
    "proxy_username",
    "proxy_password",
    "telegram_collector_api_id",
    "telegram_collector_api_hash",
    "telegram_collector_session",
    "vk_access_token",
}
_SAFE_SETTING_NAMES = {
    "app_name",
    "env",
    "debug",
    "host",
    "port",
    "web_port",
    "log_level",
    "log_format",
    "timezone",
    "sources_config_path",
    "collect_interval_minutes",
    "maintenance_hour",
    "maintenance_minute",
    "stale_after_days",
    "telegram_bot_name",
    "telegram_default_min_discount",
    "autopost_interval_minutes",
    "network_mode",
    "no_proxy",
    "telegram_network_route",
    "telegram_collector_mode",
    "vk_api_version",
}

# Defense in depth beyond the normal logging redactor. The support bundle is a
# user-shareable artifact, so URL credentials and common header/cookie forms
# are removed even if they came from older logs created before redaction.
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)([^/@:\s]+):([^/@\s]+)@")
_HEADER_SECRET = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*([^\r\n]+)"
)
_GENERIC_SECRET = re.compile(
    r"(?i)\b(token|password|passwd|secret|api[_-]?key|api[_-]?hash|session)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
)
_ID_CREDENTIAL = re.compile(
    r"(?i)\b(telegram_(?:channel_id|admin_ids)|admin[_-]?id|channel[_-]?id)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
)


class SupportBundleError(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def sanitize_text(text: str) -> str:
    value = redact_secrets(text)
    value = _URL_CREDENTIALS.sub(r"\1***REDACTED***:***REDACTED***@", value)
    value = _HEADER_SECRET.sub(r"\1: ***REDACTED***", value)
    value = _GENERIC_SECRET.sub(r"\1=***REDACTED***", value)
    value = _ID_CREDENTIAL.sub(r"\1=***REDACTED***", value)
    return value


def _configuration_summary() -> dict[str, Any]:
    settings = get_settings()
    model = settings.model_dump()
    safe = {name: model.get(name) for name in sorted(_SAFE_SETTING_NAMES)}
    configured = {
        name: bool(model.get(name))
        for name in sorted(_SECRET_SETTING_NAMES)
    }
    safe["database_backend"] = "sqlite" if settings.database_url.startswith("sqlite:///") else "other"
    return {
        "safe_settings": safe,
        "secret_settings_configured": configured,
        "env_file_present": env_path().is_file(),
        "setup_complete": settings.setup_complete,
    }


def _runtime_metadata() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "runtime_root": str(runtime_root()),
        "cwd": str(Path.cwd().resolve()),
        "pid": os.getpid(),
    }


def _safe_doctor_report() -> dict[str, Any]:
    try:
        return build_doctor_report().to_dict()
    except Exception as exc:  # support bundle must still explain startup failures
        return {"ok": False, "error": sanitize_text(f"{type(exc).__name__}: {exc}")}


def _safe_smoke_report() -> dict[str, Any]:
    try:
        return build_smoke_report()
    except Exception as exc:
        return {"available": False, "error": sanitize_text(f"{type(exc).__name__}: {exc}")}


def _safe_operational_status() -> dict[str, Any]:
    try:
        return build_operational_status()
    except Exception as exc:
        return {"state": "error", "error": sanitize_text(f"{type(exc).__name__}: {exc}")}


def _read_log_tail(path: Path) -> bytes:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > _MAX_LOG_BYTES:
            handle.seek(size - _MAX_LOG_BYTES)
        raw = handle.read()
    text = raw.decode("utf-8", errors="replace")
    return sanitize_text(text).encode("utf-8")


def _collect_payload() -> dict[str, bytes]:
    payload: dict[str, bytes] = {
        "diagnostics/runtime.json": _json_bytes(_runtime_metadata()),
        "diagnostics/configuration.json": _json_bytes(_configuration_summary()),
        "diagnostics/operational-status.json": _json_bytes(_safe_operational_status()),
        "diagnostics/doctor.json": _json_bytes(_safe_doctor_report()),
        "diagnostics/smoke-report.json": _json_bytes(_safe_smoke_report()),
    }

    logs_dir = runtime_root() / "logs"
    for name in _LOG_NAMES:
        candidate = logs_dir / name
        if candidate.is_file():
            if candidate.resolve().parent != logs_dir.resolve():
                raise SupportBundleError(f"log path escaped runtime logs directory: {candidate}")
            payload[f"logs/{name}"] = _read_log_tail(candidate)
    return payload


def _manifest(payload: dict[str, bytes]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task": "DP-DIAG-001",
        "generated_at": datetime.now(UTC).isoformat(),
        "files": [
            {
                "path": name,
                "size_bytes": len(data),
                "sha256": _sha256_bytes(data),
            }
            for name, data in sorted(payload.items())
        ],
        "excluded_by_policy": [
            ".env",
            "discount_parser.db",
            "discount_parser.db-wal",
            "discount_parser.db-shm",
        ],
    }


def build_support_bundle(output: str | Path | None = None) -> Path:
    root = runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    destination = Path(output) if output else root / "support" / "discount-parser-support.zip"
    if not destination.is_absolute():
        destination = (root / destination).resolve()
    else:
        destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = _collect_payload()
    manifest = _manifest(payload)
    payload["manifest.json"] = _json_bytes(manifest)

    # Write atomically so a failed collection/zip operation never leaves a
    # half-valid archive that might be sent to support.
    with tempfile.NamedTemporaryFile(
        prefix=".discount-parser-support-",
        suffix=".zip",
        dir=destination.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payload.items()):
                archive.writestr(name, data)
        with zipfile.ZipFile(temp_path, "r") as archive:
            names = set(archive.namelist())
            if names != set(payload):
                raise SupportBundleError("archive payload differs from support-bundle allowlist")
            for forbidden in (".env", "discount_parser.db", "discount_parser.db-wal", "discount_parser.db-shm"):
                if any(Path(name).name == forbidden for name in names):
                    raise SupportBundleError(f"forbidden runtime file entered support bundle: {forbidden}")
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return destination
