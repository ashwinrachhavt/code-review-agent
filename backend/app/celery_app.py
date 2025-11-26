from __future__ import annotations

"""Celery application configuration.

Creates a configured Celery app using Redis as broker and result backend.
The Celery app is intentionally lightweight and imported by worker modules
and the FastAPI process (only for task signature creation).
"""

from celery import Celery
from pathlib import Path

# Load environment from .env similar to FastAPI app
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()  # CWD
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:
    pass

from .core.config import get_settings


def _create() -> Celery:
    s = get_settings()

    broker_url = s.CELERY_BROKER_URL
    backend_url = s.CELERY_RESULT_BACKEND

    app = Celery(
        "code_review_agent",
        broker=broker_url,
        backend=backend_url,
    )

    # Sensible defaults for reliability and JSON-only payloads
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )
    # Ensure tasks are imported for registration regardless of import path
    # Import placed after app creation to avoid circular import issues
    try:
        from .workers import tasks as _tasks  # noqa: F401
    except Exception:
        # In web process, tasks may be imported elsewhere; safe to ignore
        pass
    return app


# Singleton Celery app
celery_app: Celery = _create()
