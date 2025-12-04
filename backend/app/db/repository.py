from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.db import SessionLocal
from backend.app.db.models import Message, Thread

# In-memory fallback when persistence is disabled (no DATABASE_URL)
_MEM_THREADS: dict[str, Thread] = {}
_MEM_MESSAGES: list[Message] = []


class ThreadRepository:
    """
    Repository for managing threads and messages using SQLAlchemy.
    """

    def __init__(self, db: Session | None = None):
        # Prefer short-lived sessions per operation; avoid holding a global session
        self.db = db

    def _get_session(self) -> Session | None:
        if self.db is not None:
            return self.db
        if SessionLocal is None:
            return None
        return SessionLocal()

    def create_thread(self, thread_id: str, title: str = "New Analysis") -> Thread:
        db = self._get_session()
        if db is None:
            # In-memory
            th = _MEM_THREADS.get(thread_id)
            if th is None:
                th = Thread(id=thread_id, title=title)
                _MEM_THREADS[thread_id] = th
            return th
        try:
            thread = Thread(id=thread_id, title=title)
            db.add(thread)
            db.commit()
            db.refresh(thread)
            return thread
        except Exception:
            db.rollback()
            th = db.query(Thread).filter(Thread.id == thread_id).first()
            if th:
                return th
            raise
        finally:
            if self.db is None and db is not None:
                db.close()

    def get_thread(self, thread_id: str) -> Thread | None:
        db = self._get_session()
        if db is None:
            return _MEM_THREADS.get(thread_id)
        try:
            return db.query(Thread).filter(Thread.id == thread_id).first()
        finally:
            if self.db is None and db is not None:
                db.close()

    def update_thread(
        self,
        thread_id: str,
        report_text: str | None = None,
        state: dict[str, Any] | None = None,
        file_count: int = 0,
        title: str | None = None,
    ):
        db = self._get_session()
        if db is None:
            # In-memory update
            th = _MEM_THREADS.get(thread_id) or Thread(id=thread_id, title="New Analysis")
            if title is not None:
                th.title = title
            if report_text is not None:
                th.report_text = report_text
            if state is not None:
                th.state_json = state
            if file_count > 0:
                th.file_count = file_count
            th.updated_at = datetime.utcnow()
            _MEM_THREADS[thread_id] = th
            return th
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if not thread:
                thread = Thread(id=thread_id, title="New Analysis")
                db.add(thread)
            if title is not None:
                thread.title = title
            if report_text is not None:
                thread.report_text = report_text
            if state is not None:
                thread.state_json = state
            if file_count > 0:
                thread.file_count = file_count
            thread.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(thread)
            return thread
        except Exception:
            db.rollback()
            raise
        finally:
            if self.db is None and db is not None:
                db.close()

    def list_threads(self, limit: int = 50) -> list[Thread]:
        db = self._get_session()
        if db is None:
            # Return latest by updated_at
            items = list(_MEM_THREADS.values())
            items.sort(key=lambda t: t.updated_at or datetime.utcnow(), reverse=True)
            return items[:limit]
        try:
            return db.query(Thread).order_by(Thread.updated_at.desc()).limit(limit).all()
        finally:
            if self.db is None and db is not None:
                db.close()

    def add_message(self, thread_id: str, role: str, content: str) -> Message:
        db = self._get_session()
        if db is None:
            msg = Message(thread_id=thread_id, role=role, content=content)
            _MEM_MESSAGES.append(msg)
            th = _MEM_THREADS.get(thread_id) or Thread(id=thread_id, title="New Analysis")
            th.updated_at = datetime.utcnow()
            _MEM_THREADS[thread_id] = th
            return msg
        try:
            message = Message(thread_id=thread_id, role=role, content=content)
            db.add(message)
            db.commit()
            db.refresh(message)
            # Touch parent thread's updated_at to keep it sorted by recent activity
            try:
                thread = db.query(Thread).filter(Thread.id == thread_id).first()
                if thread is not None:
                    thread.updated_at = datetime.utcnow()
                    db.commit()
            except Exception:
                db.rollback()
            return message
        except Exception:
            db.rollback()
            raise
        finally:
            if self.db is None and db is not None:
                db.close()

    def get_messages(self, thread_id: str) -> list[Message]:
        db = self._get_session()
        if db is None:
            return [m for m in _MEM_MESSAGES if m.thread_id == thread_id]
        try:
            return (
                db.query(Message)
                .filter(Message.thread_id == thread_id)
                .order_by(Message.created_at.asc())
                .all()
            )
        finally:
            if self.db is None and db is not None:
                db.close()

    def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread and all its messages.

        Returns True if a thread was deleted, False if it did not exist.
        """
        db = self._get_session()
        if db is None:
            # In-memory delete
            before = len(_MEM_MESSAGES)
            _MEM_MESSAGES[:] = [m for m in _MEM_MESSAGES if m.thread_id != thread_id]
            existed = thread_id in _MEM_THREADS
            _MEM_THREADS.pop(thread_id, None)
            return existed or (len(_MEM_MESSAGES) != before)
        try:
            db.query(Message).filter(Message.thread_id == thread_id).delete()
            count = db.query(Thread).filter(Thread.id == thread_id).delete()
            db.commit()
            return bool(count)
        except Exception:
            db.rollback()
            raise
        finally:
            if self.db is None and db is not None:
                db.close()


# Global instance for backward compatibility if needed,
# though dependency injection is preferred in routes.
repo = ThreadRepository()
