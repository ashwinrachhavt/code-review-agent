from __future__ import annotations

"""Thread/message persistence with optional SQLAlchemy, fallback to memory.

APIs used by routes:
- create_or_update_thread(initial_state, report_text, thread_id?) -> thread_id
- add_message(thread_id, role, content)
- get_thread(thread_id) -> dict | None
- list_threads(limit=50) -> list[dict]
"""

import threading
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any

from backend.app.core.config import get_settings

try:  # optional SQLAlchemy
    from sqlalchemy import select  # type: ignore

    _SA_AVAILABLE = True
except Exception:  # pragma: no cover
    _SA_AVAILABLE = False

from backend.app.db.db import get_engine, get_sessionmaker
from backend.app.db.models import Base, MessageModel, ThreadModel

# ------------------ Memory fallback ------------------


@dataclass
class _MemThread:
    id: str
    created_at: float
    title: str
    state: dict[str, Any] = field(default_factory=dict)
    report_text: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


class _MemoryRepo:
    def __init__(self) -> None:
        self._threads: dict[str, _MemThread] = {}
        self._lock = threading.Lock()

    def create_or_update_thread(
        self, initial_state: dict[str, Any], report_text: str | None, thread_id: str | None
    ) -> str:
        with self._lock:
            if thread_id and thread_id in self._threads:
                th = self._threads[thread_id]
                th.state = dict(initial_state or {})
                th.report_text = report_text
                return th.id
            tid = thread_id or str(_uuid.uuid4())
            title = "Code Review"
            self._threads[tid] = _MemThread(
                id=tid,
                created_at=time.time(),
                title=title,
                state=dict(initial_state or {}),
                report_text=report_text,
            )
            return tid

    def add_message(self, thread_id: str, role: str, content: str) -> None:
        with self._lock:
            th = self._threads.get(thread_id)
            if not th:
                return
            th.messages.append({"role": role, "content": content, "ts": time.time()})

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            th = self._threads.get(thread_id)
            if not th:
                return None
            return {
                "id": th.id,
                "created_at": th.created_at,
                "title": th.title,
                "state": dict(th.state or {}),
                "report_text": th.report_text,
                "messages": list(th.messages),
            }

    def list_threads(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._threads.values(), key=lambda t: t.created_at, reverse=True)[:limit]
            return [
                {
                    "id": t.id,
                    "created_at": t.created_at,
                    "title": t.title,
                    "message_count": len(t.messages),
                }
                for t in items
            ]


_MEM_REPO = _MemoryRepo()


class _SQLAlchemyRepo:
    def __init__(self) -> None:
        settings = get_settings()
        self._engine = get_engine(settings)
        self._Session = get_sessionmaker(self._engine)
        Base.metadata.create_all(self._engine)

    def create_or_update_thread(
        self, initial_state: dict[str, Any], report_text: str | None, thread_id: str | None
    ) -> str:
        tid = thread_id or str(_uuid.uuid4())
        with self._Session() as s:
            t = s.get(ThreadModel, tid)
            if t is None:
                t = ThreadModel(
                    id=tid,
                    title="Code Review",
                    state=dict(initial_state or {}),
                    report_text=report_text,
                )
                s.add(t)
            else:
                t.state = dict(initial_state or {})
                t.report_text = report_text
            s.commit()
        return tid

    def add_message(self, thread_id: str, role: str, content: str) -> None:
        mid = str(_uuid.uuid4())
        with self._Session() as s:
            if s.get(ThreadModel, thread_id) is None:
                s.add(ThreadModel(id=thread_id, title="Code Review", state={}, report_text=None))
                s.flush()
            s.add(MessageModel(id=mid, thread_id=thread_id, role=role, content=content))
            s.commit()

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._Session() as s:
            t = s.get(ThreadModel, thread_id)
            if t is None:
                return None
            s.refresh(t)  # ensure relationships
            return {
                "id": t.id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "title": t.title,
                "state": t.state,
                "report_text": t.report_text,
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in (t.messages or [])
                ],
            }

    def list_threads(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._Session() as s:
            rows = (
                s.execute(select(ThreadModel).order_by(ThreadModel.created_at.desc()).limit(limit))
                .scalars()
                .all()
            )
            return [
                {
                    "id": t.id,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "title": t.title,
                    "message_count": len(t.messages or []),
                }
                for t in rows
            ]


def _active_repo() -> Any:
    try:
        if _SA_AVAILABLE:
            return _SQLAlchemyRepo()
    except Exception:
        pass
    return _MEM_REPO


def create_or_update_thread(
    initial_state: dict[str, Any], report_text: str | None, thread_id: str | None
) -> str:
    return _active_repo().create_or_update_thread(initial_state, report_text, thread_id)


def add_message(thread_id: str, role: str, content: str) -> None:
    return _active_repo().add_message(thread_id, role, content)


def get_thread(thread_id: str) -> dict[str, Any] | None:
    return _active_repo().get_thread(thread_id)


def list_threads(limit: int = 50) -> list[dict[str, Any]]:
    return _active_repo().list_threads(limit)
