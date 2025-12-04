from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.db import SessionLocal
from backend.app.db.models import Message, Thread


class ThreadRepository:
    """
    Repository for managing threads and messages using SQLAlchemy.
    """

    def __init__(self, db: Session | None = None):
        # Prefer short-lived sessions per operation; avoid holding a global session
        self.db = db

    def _get_session(self) -> Session:
        return self.db or SessionLocal()

    def create_thread(self, thread_id: str, title: str = "New Analysis") -> Thread:
        db = self._get_session()
        try:
            thread = Thread(id=thread_id, title=title)
            db.add(thread)
            db.commit()
            db.refresh(thread)
            return thread
        except Exception:
            db.rollback()
            # Try to load if it already exists
            th = db.query(Thread).filter(Thread.id == thread_id).first()
            if th:
                return th
            raise
        finally:
            if self.db is None:
                db.close()

    def get_thread(self, thread_id: str) -> Thread | None:
        db = self._get_session()
        try:
            return db.query(Thread).filter(Thread.id == thread_id).first()
        finally:
            if self.db is None:
                db.close()

    def update_thread(
        self,
        thread_id: str,
        report_text: str = None,
        state: dict[str, Any] = None,
        file_count: int = 0,
    ):
        db = self._get_session()
        try:
            thread = db.query(Thread).filter(Thread.id == thread_id).first()
            if not thread:
                thread = Thread(id=thread_id, title="New Analysis")
                db.add(thread)
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
            if self.db is None:
                db.close()

    def list_threads(self, limit: int = 50) -> list[Thread]:
        db = self._get_session()
        try:
            return db.query(Thread).order_by(Thread.updated_at.desc()).limit(limit).all()
        finally:
            if self.db is None:
                db.close()

    def add_message(self, thread_id: str, role: str, content: str) -> Message:
        db = self._get_session()
        try:
            message = Message(thread_id=thread_id, role=role, content=content)
            db.add(message)
            db.commit()
            db.refresh(message)
            return message
        except Exception:
            db.rollback()
            raise
        finally:
            if self.db is None:
                db.close()

    def get_messages(self, thread_id: str) -> list[Message]:
        db = self._get_session()
        try:
            return (
                db.query(Message)
                .filter(Message.thread_id == thread_id)
                .order_by(Message.created_at.asc())
                .all()
            )
        finally:
            if self.db is None:
                db.close()


# Global instance for backward compatibility if needed,
# though dependency injection is preferred in routes.
repo = ThreadRepository()
