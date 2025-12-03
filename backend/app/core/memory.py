from __future__ import annotations

"""Lightweight per-thread conversation memory.

Prefers LangChain's ChatMessageHistory if available, and falls back to a
minimal in-process implementation. Also tracks the last full report hash per
thread to suppress duplicate responses.
"""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any

from backend.app.db import Message as DBMessage
from backend.app.db import SessionLocal
from backend.app.db import Thread as DBThread

try:  # LangChain memory (optional)
    from langchain_community.chat_message_histories import (
        ChatMessageHistory as LCChatHistory,
    )

    # type: ignore
    from langchain_core.messages import AIMessage, HumanMessage  # type: ignore

    _LC_AVAILABLE = True
except Exception:  # pragma: no cover - depends on runtime
    LCChatHistory = None  # type: ignore
    AIMessage = HumanMessage = object  # type: ignore
    _LC_AVAILABLE = False


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


@dataclass
class _ThreadSlot:
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Track previously streamed paragraphs to suppress repeats across turns
    seen_paragraphs: set[str] = field(default_factory=set)


class ConversationMemory:
    def __init__(self) -> None:
        self._slots: dict[str, _ThreadSlot] = {}
        self._lock = threading.Lock()

    # ---------- Slot management ----------
    def _get_slot(self, thread_id: str) -> _ThreadSlot:
        with self._lock:
            if thread_id not in self._slots:
                slot = _ThreadSlot()
                # Ensure DB thread exists
                with SessionLocal() as db:
                    thr = db.get(DBThread, thread_id)
                    if thr is None:
                        thr = DBThread(id=thread_id)
                        db.add(thr)
                        db.commit()
                self._slots[thread_id] = slot
            return self._slots[thread_id]

    # ---------- Last report hash ----------
    def get_last_report_hash(self, thread_id: str) -> str | None:
        with SessionLocal() as db:
            thr = db.get(DBThread, thread_id)
            return (thr.last_report_hash or None) if thr else None

    def set_last_report_hash(self, thread_id: str, text: str) -> str:
        h = _hash_text(text)
        slot = self._get_slot(thread_id)
        with slot.lock, SessionLocal() as db:
            thr = db.get(DBThread, thread_id)
            if thr is None:
                thr = DBThread(id=thread_id)
                db.add(thr)
            thr.last_report_hash = h
            db.commit()
        return h

    # ---------- Conversation history ----------
    def _append(self, thread_id: str, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        slot = self._get_slot(thread_id)
        # Persist to SQLite with combined context managers
        with slot.lock, SessionLocal() as db:
            thr = db.get(DBThread, thread_id)
            if thr is None:
                thr = DBThread(id=thread_id)
                db.add(thr)
                db.flush()
            msg = DBMessage(thread_id=thr.id, role=role, content=content)
            db.add(msg)
            db.commit()

    def append_user(self, thread_id: str, content: str) -> None:
        if not content:
            return
        # Deduplicate identical consecutive user message
        last = self.last_message(thread_id)
        if last and last[0] == "user" and (last[1] or "").strip() == content.strip():
            return
        self._append(thread_id, "user", content)

    def append_assistant_if_new(self, thread_id: str, content: str) -> bool:
        """Append assistant message if different from the last assistant message.

        Returns True if appended, False if considered duplicate.
        """
        if not content:
            return False
        last = self.last_message(thread_id)
        if last and last[0] == "assistant" and (last[1] or "").strip() == content.strip():
            return False
        self._append(thread_id, "assistant", content)
        return True

    def last_message(self, thread_id: str) -> tuple[str, str] | None:
        # DB-backed latest message
        with SessionLocal() as db:
            row = (
                db.query(DBMessage)
                .filter(DBMessage.thread_id == thread_id)
                .order_by(DBMessage.id.desc())
                .first()
            )
            if not row:
                return None
            return str(row.role or ""), str(row.content or "")

    def last_assistant(self, thread_id: str) -> str | None:
        """Return the most recent assistant message content, if any."""
        with SessionLocal() as db:
            row = (
                db.query(DBMessage)
                .filter(DBMessage.thread_id == thread_id, DBMessage.role == "assistant")
                .order_by(DBMessage.id.desc())
                .first()
            )
            return str(row.content) if row and row.content else None

    def get_history(self, thread_id: str, limit: int = 50) -> list[dict[str, str]]:
        with SessionLocal() as db:
            rows = (
                db.query(DBMessage)
                .filter(DBMessage.thread_id == thread_id)
                .order_by(DBMessage.id.asc())
                .all()
            )
            if not rows:
                return []
            return [{"role": r.role, "content": r.content} for r in rows][-limit:]

    # ---------- Seen paragraphs (for chat streaming dedupe across turns) ----------
    def get_seen_paragraphs(self, thread_id: str) -> list[str]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            return list(slot.seen_paragraphs)

    def add_seen_paragraphs(self, thread_id: str, paras: list[str]) -> None:
        if not paras:
            return
        slot = self._get_slot(thread_id)
        with slot.lock:
            for p in paras:
                s = (p or "").strip()
                if s:
                    slot.seen_paragraphs.add(s)

    # ---------- Analyze results (report + structured data) ----------
    def set_analysis(
        self, thread_id: str, text: str, reports: dict[str, Any] | None = None
    ) -> None:
        slot = self._get_slot(thread_id)
        with slot.lock, SessionLocal() as db:
            thr = db.get(DBThread, thread_id)
            if thr is None:
                thr = DBThread(id=thread_id)
                db.add(thr)
            clean = (text or "").strip()
            thr.final_report = clean
            thr.last_report_hash = _hash_text(clean) if clean else ""
            if reports is not None:
                try:
                    thr.reports_json = json.dumps(reports)
                except Exception:
                    thr.reports_json = "{}"
            db.commit()

    def get_analysis(self, thread_id: str) -> tuple[str | None, dict[str, Any]]:
        with SessionLocal() as db:
            thr = db.get(DBThread, thread_id)
            if not thr:
                return None, {}
            try:
                reports = json.loads(thr.reports_json or "{}")
            except Exception:
                reports = {}
            return (thr.final_report or None), reports


# Singleton
_MEMORY = ConversationMemory()


def get_memory() -> ConversationMemory:
    return _MEMORY
