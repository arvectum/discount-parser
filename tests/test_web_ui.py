from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.modules.offers.models import Offer, PublishFilter
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.web.app import app
from src.web import setup as setup_utils


@pytest.fixture
def web_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'web.db'}")
    setup_utils.ENV_PATH = tmp_path / ".env"
    setup_utils.ENV_EXAMPLE_PATH = tmp_path / ".env.example"
    setup_utils.ENV_EXAMPLE_PATH.write_text(
        "DP_DATABASE_URL=sqlite:///./web.db\n"
        "DP_TELEGRAM_BOT_TOKEN=\n"
        "DP_TELEGRAM_BOT_NAME=\n"
        "DP_TELEGRAM_CHANNEL_ID=\n"
        "DP_TELEGRAM_ADMIN_IDS=\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield tmp_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_first_launch_redirects_to_setup_and_saves_configuration(web_env: Path) -> None:
    client = TestClient(app)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"

    response = client.post(
        "/setup",
        data={
            "bot_token": "123456789:AAabcdefghijklmnopqrstuvwxyz",
            "bot_name": "Deals Bot",
            "channel_id": "@deals_test",
            "admin_ids": "123456789",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert setup_utils.ENV_PATH.exists()
    env_text = setup_utils.ENV_PATH.read_text(encoding="utf-8")
    assert "DP_TELEGRAM_CHANNEL_ID=@deals_test" in env_text
    assert "DP_TELEGRAM_ADMIN_IDS=123456789" in env_text

    response = client.get("/")
    assert response.status_code == 200
    assert "Панель управления парсером" in response.text
    assert "Очередь публикации" in response.text
    assert "XLSX-коррекция" in response.text


def test_web_filter_updates_shared_publish_filter(web_env: Path) -> None:
    setup_utils.save_telegram_setup(
        bot_token="123456789:AAabcdefghijklmnopqrstuvwxyz",
        bot_name="Deals Bot",
        channel_id="@deals_test",
        admin_ids="123456789",
    )
    with create_session() as session:
        session.add(Offer(title="Deal", status="ready", category="Дом", merchant="Shop", discount_percent=35))
        session.commit()

    client = TestClient(app)
    response = client.post(
        "/filter",
        data={
            "min_discount_percent": "30",
            "category": "Дом",
            "subcategory": "",
            "offer_type": "",
            "merchant": "Shop",
            "max_posts_per_cycle": "7",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with create_session() as session:
        row = session.scalar(select(PublishFilter).where(PublishFilter.name == "telegram-default"))
        assert row is not None
        assert int(row.min_discount_percent) == 30
        assert row.category == "Дом"
        assert row.merchant == "Shop"
        assert row.max_posts_per_cycle == 7
        assert row.enabled is True
