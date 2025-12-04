from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
import os

from backend.app.core.config import get_settings
from pathlib import Path
from backend.app.db.models import Base

settings = get_settings()

def _ensure_sqlite_dir(db_url: str) -> None:
    if db_url.startswith("sqlite:///"):
        path = db_url.replace("sqlite:///", "", 1)
        dirpath = os.path.dirname(os.path.abspath(path))
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)

db_url = settings.DATABASE_URL
_ensure_sqlite_dir(db_url)
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _ensure_columns(table: str, required: dict[str, str]) -> None:
    """Ensure columns exist on a SQLite table by issuing ALTER TABLE ADD COLUMN.

    Parameters
    ----------
    table: str
        Table name.
    required: dict[str, str]
        Mapping of column name to SQLite column type (e.g., 'TEXT', 'INTEGER', 'DATETIME').
    """
    try:
        insp = inspect(engine)
        if table not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns(table)}
        with engine.begin() as conn:
            for col, col_type in required.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
    except Exception:
        # Best effort; avoid breaking startup due to migration issues
        pass


def _run_alembic_upgrade() -> None:
    """Run Alembic upgrade to the latest migration (head)."""
    try:
        from alembic import command
        from alembic.config import Config

        # Resolve paths relative to repo root
        repo_root = Path(__file__).resolve().parents[2]
        alembic_ini = repo_root / "backend" / "alembic.ini"
        alembic_dir = repo_root / "backend" / "alembic"

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(alembic_dir))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.upgrade(cfg, "head")
    except Exception:
        # Best effort; fall back to create_all below
        pass


def init_db():
    """Initialize database by running Alembic migrations or falling back to create_all.

    SQLite legacy helpers only run for SQLite URLs and are skipped for Postgres.
    """
    _run_alembic_upgrade()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass

    # Run lightweight SQLite-only helpers (no-ops for Postgres)
    if settings.DATABASE_URL.startswith("sqlite"):
        _migrate_threads_table_if_legacy()
        _ensure_columns(
            "threads",
            {
                "title": "TEXT",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
                "report_text": "TEXT",
                "state_json": "TEXT",
                "file_count": "INTEGER DEFAULT 0",
            },
        )
        _ensure_columns(
            "messages",
            {
                "thread_id": "TEXT",
                "role": "TEXT",
                "content": "TEXT",
                "created_at": "DATETIME",
            },
        )


def _migrate_threads_table_if_legacy() -> None:
    """Rebuild the threads table if an old NOT NULL 'state' column exists.

    Some earlier iterations created a 'state' column with a NOT NULL constraint.
    Our current model uses 'state_json' as a JSON/TEXT column. SQLite cannot drop
    NOT NULL easily; rebuild the table and migrate data if we detect the legacy column.
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(threads)")).fetchall()
            if not rows:
                return
            # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
            cols = {row[1]: {"type": row[2], "notnull": row[3]} for row in rows}
            has_state = "state" in cols
            state_notnull = bool(cols.get("state", {}).get("notnull", 0)) if has_state else False
            if not has_state or not state_notnull:
                return

            # Determine available source columns for migration
            has_state_json = "state_json" in cols
            has_file_count = "file_count" in cols

            # Build expressions for SELECT clause based on available columns
            state_expr = "state" if has_state else ("state_json" if has_state_json else "'{}'")
            file_count_expr = "file_count" if has_file_count else "0"

            # Create new table with desired schema
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS threads_new (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        created_at DATETIME,
                        updated_at DATETIME,
                        report_text TEXT,
                        state_json TEXT,
                        file_count INTEGER DEFAULT 0
                    )
                    """
                )
            )

            # Migrate data from old table
            conn.execute(
                text(
                    f"""
                    INSERT INTO threads_new (id, title, created_at, updated_at, report_text, state_json, file_count)
                    SELECT id, title, created_at, updated_at, report_text, COALESCE({state_expr}, '{{}}'), COALESCE({file_count_expr}, 0)
                    FROM threads
                    """
                )
            )

            # Replace old table
            conn.execute(text("DROP TABLE threads"))
            conn.execute(text("ALTER TABLE threads_new RENAME TO threads"))
    except Exception:
        # Best effort; don't break app startup
        pass


def get_db():
    """Dependency for getting DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
