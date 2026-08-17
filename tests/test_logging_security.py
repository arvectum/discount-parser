from __future__ import annotations

import json
import logging

from src.shared.logging import JsonFormatter, redact_secrets, redact_value


SECRETS = (
    '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi',
    'hunter2',
    'abc123',
    'cookie-secret',
    'alice',
    'letmein',
    '-1004453906792',
    '987654321',
)


def _assert_secret_free(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


def test_redact_secrets_covers_protocol_and_application_forms() -> None:
    raw = (
        'telegram_bot_token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi '
        'password=hunter2 token=abc123 '
        'Authorization: Bearer-supersecret '
        'Cookie=cookie-secret '
        'proxy=https://alice:letmein@proxy.example:8080 '
        'telegram_channel_id=-1004453906792 admin_id=987654321'
    )
    clean = redact_secrets(raw)
    _assert_secret_free(clean)
    assert 'REDACTED' in clean


def test_recursive_redaction_preserves_shape() -> None:
    value = {
        'outer': [
            {'password': 'password=hunter2'},
            'https://alice:letmein@proxy.example:8080',
        ],
        'channel': 'telegram_channel_id=-1004453906792',
    }
    clean = redact_value(value)
    assert isinstance(clean, dict)
    assert isinstance(clean['outer'], list)
    _assert_secret_free(json.dumps(clean, ensure_ascii=False))


def test_json_formatter_redacts_message_and_nested_extras() -> None:
    record = logging.LogRecord(
        name='security-test',
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg='password=hunter2 token=abc123',
        args=(),
        exc_info=None,
    )
    record.payload = {
        'proxy': 'https://alice:letmein@proxy.example:8080',
        'channel': 'telegram_channel_id=-1004453906792',
        'cookie': 'Cookie=cookie-secret',
    }
    rendered = JsonFormatter().format(record)
    _assert_secret_free(rendered)
    decoded = json.loads(rendered)
    assert isinstance(decoded['payload'], dict)
