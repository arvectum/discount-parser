import json
import logging

from src.shared.config import Settings
from src.shared.logging import JsonFormatter, configure_logging


def test_settings_use_dp_environment_prefix(monkeypatch) -> None:
    monkeypatch.setenv("DP_APP_NAME", "Configured Parser")
    monkeypatch.setenv("DP_PORT", "9001")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Configured Parser"
    assert settings.port == 9001


def test_json_formatter_emits_structured_payload() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="discount_parser.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.source = "fixture"

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["source"] == "fixture"
    assert payload["timestamp"]


def test_configure_logging_supports_plain_and_json() -> None:
    configure_logging("DEBUG", "plain")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert root.handlers

    configure_logging("INFO", "json")
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
