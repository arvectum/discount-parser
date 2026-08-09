from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.shared.config import get_settings
from src.web import onboarding_routes, setup as web_setup
from src.web.application import app


@pytest.fixture
def isolated_onboarding_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / '.env'
    example_path = tmp_path / '.env.example'
    example_path.write_text('DP_DATABASE_URL=sqlite:///./discount_parser.db\n', encoding='utf-8')
    monkeypatch.setattr(web_setup, 'ENV_PATH', env_path)
    monkeypatch.setattr(web_setup, 'ENV_EXAMPLE_PATH', example_path)
    get_settings.cache_clear()
    yield env_path
    get_settings.cache_clear()


def test_legacy_setup_get_redirects_to_onboarding(isolated_onboarding_env: Path) -> None:
    client = TestClient(app)
    response = client.get('/setup', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/onboarding/1'


def test_onboarding_step_one_saves_required_telegram_settings(
    isolated_onboarding_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(onboarding_routes, '_test_telegram', lambda token, channel: (True, 'Telegram OK'))
    client = TestClient(app)
    response = client.post(
        '/onboarding/1',
        data={
            'bot_token': '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'bot_name': 'Deals Bot',
            'channel_id': '@deals_channel',
            'admin_ids': '123456789',
            'action': 'save',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers['location'] == '/onboarding/2'
    text = isolated_onboarding_env.read_text(encoding='utf-8')
    assert 'DP_TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ' in text
    assert 'DP_TELEGRAM_CHANNEL_ID=@deals_channel' in text
    assert 'DP_TELEGRAM_ADMIN_IDS=123456789' in text


def test_onboarding_step_one_does_not_save_when_live_validation_fails(
    isolated_onboarding_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(onboarding_routes, '_test_telegram', lambda token, channel: (False, 'Channel unavailable'))
    client = TestClient(app)
    response = client.post(
        '/onboarding/1',
        data={
            'bot_token': '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'bot_name': 'Deals Bot',
            'channel_id': '@deals_channel',
            'admin_ids': '123456789',
            'action': 'save',
        },
    )
    assert response.status_code == 200
    assert 'Channel unavailable' in response.text
    assert not isolated_onboarding_env.exists()


def test_telegram_test_reports_success_without_echoing_secret(
    isolated_onboarding_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(onboarding_routes, '_test_telegram', lambda token, channel: (True, 'Telegram OK'))
    client = TestClient(app)
    secret = '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    response = client.post(
        '/onboarding/1',
        data={
            'bot_token': secret,
            'bot_name': 'Deals Bot',
            'channel_id': '@deals_channel',
            'admin_ids': '123456789',
            'action': 'test',
        },
    )
    assert response.status_code == 200
    assert 'Telegram OK' in response.text
    assert secret not in response.text


def test_public_telegram_collector_requires_no_extra_credentials(isolated_onboarding_env: Path) -> None:
    client = TestClient(app)
    response = client.post(
        '/onboarding/2',
        data={'mode': 'public', 'api_id': '', 'api_hash': ''},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers['location'] == '/onboarding/3'
    text = isolated_onboarding_env.read_text(encoding='utf-8')
    assert 'DP_TELEGRAM_COLLECTOR_MODE=public' in text


def test_mtproto_requires_api_credentials(isolated_onboarding_env: Path) -> None:
    client = TestClient(app)
    response = client.post(
        '/onboarding/2',
        data={'mode': 'mtproto', 'api_id': '', 'api_hash': ''},
    )
    assert response.status_code == 200
    assert 'Telegram API ID' in response.text
    assert not isolated_onboarding_env.exists()


def test_vk_can_be_skipped_without_writing_token(isolated_onboarding_env: Path) -> None:
    client = TestClient(app)
    response = client.post(
        '/onboarding/3',
        data={'access_token': '', 'api_version': '5.199', 'action': 'skip'},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers['location'] == '/onboarding/4'
    assert not isolated_onboarding_env.exists()


def test_source_summary_explains_all_supported_platforms(isolated_onboarding_env: Path) -> None:
    client = TestClient(app)
    response = client.get('/onboarding/4')
    assert response.status_code == 200
    for label in ('Сайты промокодов', 'Сайты магазинов', 'Telegram', 'VK', 'Дзен', 'Rutube'):
        assert label in response.text
