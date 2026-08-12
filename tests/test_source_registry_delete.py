from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import create_source
from src.shared import config as shared_config
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime
from src.web.application import app
from src.web import setup as web_setup


def test_temporary_source_can_be_deleted_from_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'registry.db'}")
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    monkeypatch.setattr(web_setup, "env_path", lambda: env_file)
    monkeypatch.setattr(web_setup, "env_example_path", lambda: example_file)
    monkeypatch.setattr(shared_config, "env_path", lambda: env_file)
    example_file.write_text("DP_TELEGRAM_BOT_TOKEN=\nDP_TELEGRAM_CHANNEL_ID=\nDP_TELEGRAM_ADMIN_IDS=\n", encoding="utf-8")
    get_settings.cache_clear(); reset_db_runtime(); Base.metadata.create_all(get_engine())
    try:
        web_setup.save_telegram_setup(bot_token="123456789:AAabcdefghijklmnopqrstuvwxyz", bot_name="Test", channel_id="@test", admin_ids="123456789")
        with create_session() as session:
            source = create_source(session, name="Temporary", platform="website", source_type="promo_page", url="https://example.test", collector_type="generic_web")
            session.commit(); source_id = source.id
        response = TestClient(app).post(f"/sources-registry/{source_id}/delete", follow_redirects=False)
        assert response.status_code == 303
        with create_session() as session:
            assert session.scalar(select(RegisteredSource).where(RegisteredSource.id == source_id)) is None
    finally:
        reset_db_runtime(); get_settings.cache_clear()
