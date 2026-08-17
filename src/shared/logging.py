import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from datetime import UTC, datetime

from src.shared.runtime_paths import runtime_root


_STANDARD_LOG_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}

# DP-SEC-001: logging is a user-shareable boundary. Redaction intentionally
# covers both named settings and common protocol/header representations so a
# traceback or third-party exception cannot leak credentials into app.log.
_SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(bot[_-]?token|telegram[_-]?bot[_-]?token|api[_-]?(?:key|hash)|password|passwd|proxy[_-]?password|access[_-]?token|secret|session|authorization|proxy-authorization|vk[_-]?access[_-]?token|cookie|set-cookie|x-api-key|telegram[_-]?(?:channel_id|admin_ids)|admin[_-]?id|channel[_-]?id)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
    ),
    re.compile(r"(?i)(https?://)([^/@:\s]+):([^/@\s]+)@"),
    re.compile(r"\d{7,12}:[A-Za-z0-9_-]{34,46}"),
]


def redact_secrets(text: str) -> str:
    if not text:
        return text
    result = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            result = pattern.sub(r"\1=***REDACTED***", result)
        elif pattern.groups == 3:
            result = pattern.sub(r"\1***REDACTED***:***REDACTED***@", result)
        else:
            result = pattern.sub(r"***REDACTED_TOKEN***", result)
    return result


def redact_value(value):
    """Recursively redact strings in structured logging extras.

    JSON log extras frequently contain nested dict/list payloads. Converting an
    entire object to one string loses structure and can leave secrets in custom
    serializers; recursively redacting keeps the useful shape and the privacy
    boundary at the formatter.
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, set):
        return sorted(redact_value(item) for item in value)
    return value


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            record.args = redact_value(record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "pid": os.getpid(),
            "message": redact_secrets(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_KEYS and not key.startswith("_"):
                payload[key] = redact_value(value)
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class StandardFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_secrets(formatted)


def app_log_path() -> Path:
    log_dir = runtime_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "app.log"


def configure_logging(level: str = "INFO", log_format: str = "plain", *, component: str | None = None, enable_file: bool = True) -> None:
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()

    root.setLevel(level.upper())

    fmt_str = f"%(asctime)s [%(process)d] %(levelname)s [{component or '%(name)s'}]: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(SecretFilter())
    if log_format.lower() == "json":
        stream_handler.setFormatter(JsonFormatter())
    else:
        stream_handler.setFormatter(StandardFormatter(fmt_str, datefmt=date_fmt))
    root.addHandler(stream_handler)

    if enable_file:
        try:
            file_path = app_log_path()
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
                delay=False,
            )
            file_handler.setFormatter(StandardFormatter(fmt_str, datefmt=date_fmt))
            file_handler.addFilter(SecretFilter())
            root.addHandler(file_handler)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
