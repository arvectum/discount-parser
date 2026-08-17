import logging
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.shared.config import get_settings
from src.shared.runtime_paths import runtime_root

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"pool_pre_ping": True, "echo": settings.debug}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(settings.database_url, **kwargs)
        if settings.database_url.startswith("sqlite"):
            _configure_sqlite(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def create_session() -> Session:
    return get_session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_connection() -> bool:
    try:
        with create_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_db_runtime() -> None:
    global _engine, _session_factory
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _session_factory = None


def check_and_recover_db() -> bool:
    """Check SQLite integrity and perform automatic recovery if malformed.

    Returns True if a recovery was performed, False otherwise.
    """
    from src.shared.config import get_settings
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        return False

    db_path = Path(settings.database_url.removeprefix("sqlite:///")).resolve()
    if not db_path.exists():
        return False

    # 1. Quick integrity check
    is_malformed = False
    temp_engine = create_engine(settings.database_url, connect_args={"timeout": 5})
    try:
        with temp_engine.connect() as conn:
            # Quick check first
            result = conn.execute(text("PRAGMA quick_check")).scalar()
            if result != "ok":
                is_malformed = True
            else:
                try:
                    conn.execute(text("SELECT name FROM sqlite_master LIMIT 1"))
                except Exception:
                    is_malformed = True
    except Exception:
        is_malformed = True
    finally:
        temp_engine.dispose()

    if not is_malformed:
        return False

    logger.error(f"Database {db_path} is malformed. Starting recovery...")

    # 2. Dispose existing runtime engine AND wait a bit for file locks to release
    reset_db_runtime()
    import time
    time.sleep(0.5)

    # 3. Backup malformed files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f".corrupt_{timestamp}")
    
    import gc
    gc.collect()
    reset_db_runtime()
    time.sleep(0.5)

    for attempt in range(3):
        success = True
        for suffix in ["", "-wal", "-shm"]:
            file = db_path.with_name(db_path.name + suffix)
            if file.exists():
                try:
                    dest = backup_path.with_name(backup_path.name + suffix)
                    # Try rename first, it's atomic and often works better on Windows
                    try:
                        os.rename(str(file), str(dest))
                    except Exception:
                        shutil.copy2(str(file), str(dest))
                        file.unlink()
                except Exception as exc:
                    logger.warning(f"Attempt {attempt+1}: Failed to handle {file}: {exc}")
                    success = False
        if success:
            break
        time.sleep(1.0)
    
    if not success:
        logger.error("Could not move malformed database files (locked). Attempting to overwrite directly...")
    
    # Ensure fresh state for SQLAlchemy
    reset_db_runtime()

    # 4. Re-initialize
    from alembic import command
    from alembic.config import Config
    from src.modules.source_registry.seed import seed_registry

    try:
        # Distribution entry uses alembic.ini from CWD
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        
        with session_scope() as session:
            seed_registry(session, sources_config_path=settings.sources_config_path)
        
        logger.info("Database recovered successfully.")
        return True
    except Exception as exc:
        logger.critical(f"Database recovery failed: {exc}")
        return False
