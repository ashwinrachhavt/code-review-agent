from __future__ import annotations

"""SQLite persistence for threads and chat messages.

Provides a small SQLAlchemy ORM for Threads and Messages and a Session maker.
"""

from collections.abc import Generator
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from backend.app.core.config import get_settings

Base = declarative_base()


class Thread(Base):
    __tablename__ = "threads"

    id = Column(String, primary_key=True)
    input_mode = Column(String, default="paste")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    final_report = Column(Text, default="")
    last_report_hash = Column(String, default="")
    reports_json = Column(Text, default="")

    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String, ForeignKey("threads.id"))
    role = Column(String)  # 'user' | 'assistant'
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    thread = relationship("Thread", back_populates="messages")


def _engine_url() -> str:
    settings = get_settings()
    return settings.DATABASE_URL


engine = create_engine(_engine_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:  # pragma: no cover - used at runtime
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
