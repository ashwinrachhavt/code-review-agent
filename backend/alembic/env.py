from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv  # type: ignore
from sqlalchemy import engine_from_config, pool

# Load environment variables from .env files to make DATABASE_URL available
repo_root = Path(__file__).resolve().parents[2]
# Ensure `import backend...` works when running Alembic from backend/
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
load_dotenv(repo_root / "backend" / ".env")
load_dotenv(repo_root / ".env")

# Interpret the config file for Python logging.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Application imports: use app settings for DB URL and models metadata
from backend.app.core.config import get_settings
from backend.app.db.models import Base

target_metadata = Base.metadata

def get_url() -> str:
    try:
        settings = get_settings()
        return settings.DATABASE_URL
    except Exception:
        return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
