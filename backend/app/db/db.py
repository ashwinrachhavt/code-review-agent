import contextlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.db.models import Base

settings = get_settings()

# Postgres-only persistence. If DATABASE_URL is unset, disable persistence.
db_url = (settings.DATABASE_URL or "").strip()
if db_url:
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:  # persistence disabled for tests/local without DB
    engine = None  # type: ignore[assignment]
    SessionLocal = None  # type: ignore[assignment]


def _run_alembic_upgrade() -> None:
    """Run Alembic upgrade to the latest migration (head)."""
    if not db_url:
        return
    with contextlib.suppress(Exception):
        from alembic import command
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("script_location", "backend/alembic")
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")


def init_db() -> None:
    """Initialize database by running Alembic migrations (no-op if disabled)."""
    if not db_url:
        return
    _run_alembic_upgrade()
    with contextlib.suppress(Exception):
        Base.metadata.create_all(bind=engine)  # type: ignore[arg-type]


def get_db():
    """Dependency for getting DB session."""
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

