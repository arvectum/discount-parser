from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.shared.config import get_settings
from src.web import setup as web_setup
from src.web.app import app


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / '.env'
    example_path = tmp_path / '.env.example'
    example_path.write_text('DP_DATABASE_URL=sqlite:///./discount_parser.db\n', encoding='utf-8')
    monkeypatch.setattr(web_setup, 'ENV_PATH', env_path)
    monkeypatch.setattr(web_setup, 'ENV_EXAMPLE_PATH', example_path)
    get_settings.cache_clear()
    yield env_path
    get_settings.cache_clear()


def test_first_run_redirects_to_setup(isolated_env: Path) -> None:
    client = TestClient(app)
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/setup'


def test_setup_writes_env_and_redirects(isolated_env: Path) -> None:
    client = TestClient(app)
    response = client.post(
        '/setup',
        data={
            'bot_token': '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'bot_name': 'Deals Bot',
            'channel_id': '@deals_channel',
            'admin_ids': '123456789',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers['location'].startswith('/?message=')
    text = isolated_env.read_text(encoding='utf-8')
    assert 'DP_TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ' in text
    assert 'DP_TELEGRAM_BOT_NAME=Deals Bot' in text
    assert 'DP_TELEGRAM_CHANNEL_ID=@deals_channel' in text
    assert 'DP_TELEGRAM_ADMIN_IDS=123456789' in text


def test_setup_rejects_non_numeric_admin_id(isolated_env: Path) -> None:
    client = TestClient(app)
    response = client.post(
        '/setup',
        data={
            'bot_token': '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'bot_name': 'Deals Bot',
            'channel_id': '@deals_channel',
            'admin_ids': 'not-a-number',
        },
    )
    assert response.status_code == 200
    assert 'Telegram user ID должен быть числом' in response.text
    assert not isolated_env.exists()


def test_setup_rejects_multiline_env_injection(isolated_env: Path) -> None:
    with pytest.raises(ValueError):
        web_setup.save_telegram_setup(
            bot_token='123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ\nDP_DEBUG=true',
            bot_name='Deals Bot',
            channel_id='@deals_channel',
            admin_ids='123456789',
        )
    assert not isolated_env.exists()


def test_atomic_write_preserves_existing_unrelated_settings(isolated_env: Path) -> None:
    isolated_env.write_text('DP_DATABASE_URL=sqlite:///./custom.db\nDP_DEBUG=true\n', encoding='utf-8')
    web_setup.save_telegram_setup(
        bot_token='123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        bot_name='Deals Bot',
        channel_id='@deals_channel',
        admin_ids='123456789',
    )
    text = isolated_env.read_text(encoding='utf-8')
    assert 'DP_DATABASE_URL=sqlite:///./custom.db' in text
    assert 'DP_DEBUG=true' in text
    assert 'DP_TELEGRAM_CHANNEL_ID=@deals_channel' in text
