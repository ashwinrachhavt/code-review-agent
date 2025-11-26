from __future__ import annotations

"""Lightweight per-thread conversation memory.

Prefers LangChain's ChatMessageHistory if available, and falls back to a
minimal in-process implementation. Also tracks the last full report hash per
thread to suppress duplicate responses.
"""

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:  # LangChain memory (optional)
    from langchain_community.chat_message_histories import (
        ChatMessageHistory as LCChatHistory,
    )  # type: ignore
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
    last_report_hash: Optional[str] = None
    last_report_text: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Either LangChain ChatMessageHistory or a simple list of dicts
    history: Any = field(default=None)
    # Track previously streamed paragraphs to suppress repeats across turns
    seen_paragraphs: set[str] = field(default_factory=set)
    # Last structured reports from analyze phase
    reports: Dict[str, Any] = field(default_factory=dict)


class ConversationMemory:
    def __init__(self) -> None:
        self._slots: Dict[str, _ThreadSlot] = {}
        self._lock = threading.Lock()

    # ---------- Slot management ----------
    def _get_slot(self, thread_id: str) -> _ThreadSlot:
        with self._lock:
            if thread_id not in self._slots:
                slot = _ThreadSlot()
                if _LC_AVAILABLE:
                    slot.history = LCChatHistory()
                else:
                    slot.history = []  # list of {role, content}
                self._slots[thread_id] = slot
            return self._slots[thread_id]

    # ---------- Last report hash ----------
    def get_last_report_hash(self, thread_id: str) -> Optional[str]:
        return self._get_slot(thread_id).last_report_hash

    def set_last_report_hash(self, thread_id: str, text: str) -> str:
        h = _hash_text(text)
        slot = self._get_slot(thread_id)
        with slot.lock:
            slot.last_report_hash = h
        return h

    # ---------- Conversation history ----------
    def _append(self, thread_id: str, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        slot = self._get_slot(thread_id)
        with slot.lock:
            if _LC_AVAILABLE and isinstance(slot.history, LCChatHistory):
                if role == "user":
                    slot.history.add_message(HumanMessage(content=content))  # type: ignore[arg-type]
                else:
                    slot.history.add_message(AIMessage(content=content))  # type: ignore[arg-type]
            else:
                slot.history.append({"role": role, "content": content})

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

    def last_message(self, thread_id: str) -> Optional[Tuple[str, str]]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            if _LC_AVAILABLE and isinstance(slot.history, LCChatHistory):
                msgs = slot.history.messages  # type: ignore[attr-defined]
                if not msgs:
                    return None
                m = msgs[-1]
                role = "assistant" if isinstance(m, AIMessage) else "user"
                content = getattr(m, "content", "")
                return role, str(content)
            else:
                if not slot.history:
                    return None
                m = slot.history[-1]
                return str(m.get("role", "")), str(m.get("content", ""))

    def last_assistant(self, thread_id: str) -> Optional[str]:
        """Return the most recent assistant message content, if any."""
        slot = self._get_slot(thread_id)
        with slot.lock:
            if _LC_AVAILABLE and isinstance(slot.history, LCChatHistory):
                for m in reversed(slot.history.messages):  # type: ignore[attr-defined]
                    if isinstance(m, AIMessage):
                        return str(getattr(m, "content", ""))
                return None
            else:
                for m in reversed(slot.history):
                    if (m.get("role") or "") == "assistant":
                        return str(m.get("content", ""))
                return None

    def get_history(self, thread_id: str, limit: int = 50) -> List[Dict[str, str]]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            if _LC_AVAILABLE and isinstance(slot.history, LCChatHistory):
                out: List[Dict[str, str]] = []
                for m in slot.history.messages[-limit:]:  # type: ignore[attr-defined]
                    if isinstance(m, AIMessage):
                        out.append({"role": "assistant", "content": str(getattr(m, "content", ""))})
                    else:
                        out.append({"role": "user", "content": str(getattr(m, "content", ""))})
                return out
            else:
                return list(slot.history[-limit:])

    # ---------- Seen paragraphs (for chat streaming dedupe across turns) ----------
    def get_seen_paragraphs(self, thread_id: str) -> List[str]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            return list(slot.seen_paragraphs)

    def add_seen_paragraphs(self, thread_id: str, paras: List[str]) -> None:
        if not paras:
            return
        slot = self._get_slot(thread_id)
        with slot.lock:
            for p in paras:
                s = (p or "").strip()
                if s:
                    slot.seen_paragraphs.add(s)

    # ---------- Analyze results (report + structured data) ----------
    def set_analysis(self, thread_id: str, text: str, reports: Dict[str, Any] | None = None) -> None:
        slot = self._get_slot(thread_id)
        with slot.lock:
            slot.last_report_text = (text or "").strip() or None
            if slot.last_report_text:
                slot.last_report_hash = _hash_text(slot.last_report_text)
            if reports is not None:
                slot.reports = reports

    def get_analysis(self, thread_id: str) -> Tuple[Optional[str], Dict[str, Any]]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            return slot.last_report_text, dict(slot.reports or {})


# Singleton
_MEMORY = ConversationMemory()


def get_memory() -> ConversationMemory:
    return _MEMORY
