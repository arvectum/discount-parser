import pytest
from pathlib import Path
from sqlalchemy import text
from src.shared.db import check_and_recover_db, create_session, reset_db_runtime, get_engine
from src.shared.config import get_settings

def test_db_corruption_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # 1. Setup a clean DB in tmp_path
    db_file = tmp_path / "test_corrupt.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DP_DATABASE_URL", db_url)
    monkeypatch.setenv("DP_RUNTIME_ROOT", str(tmp_path))
    
    # Initialize DB (run migrations)
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    
    # Verify it works
    with create_session() as session:
        session.execute(text("SELECT 1"))
    
    # 2. Corrupt the DB file
    reset_db_runtime()
    with open(db_file, "wb") as f:
        f.write(b"NOT A SQLITE DATABASE")
    
    # 3. Trigger recovery
    # Clear lru cache to ensure fresh settings are picked up
    from src.shared.config import get_settings
    get_settings.cache_clear()
    
    recovered = check_and_recover_db()
    assert recovered is True
    
    # 4. Verify recovery results
    # Corrupt file should be backed up
    # Note: DB filename might be different in glob due to extension handling in check_and_recover_db
    backups = list(tmp_path.glob("test_corrupt.corrupt_*"))
    if not backups:
         backups = list(tmp_path.glob("test_corrupt.db.corrupt_*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"NOT A SQLITE DATABASE"
    
    # New DB should be valid
    with create_session() as session:
        # Tables should exist (from migrations)
        session.execute(text("SELECT * FROM offers"))
    
    # Repeat check - should return False (already healthy)
    assert check_and_recover_db() is False
