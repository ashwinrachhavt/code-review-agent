from __future__ import annotations

"""Lightweight per-thread conversation memory and analysis cache.

Provides an in-process memory store keyed by `thread_id`, with:
- message history (user/assistant)
- last analysis report hash/text
- structured reports (security/quality/bug)

Optional: if LangChain chat history is available, uses it; otherwise a simple
list of dicts is used. This module is intentionally dependency-light.
"""

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_community.chat_message_histories import (
    ChatMessageHistory as LCChatHistory,
)
from langchain_core.messages import AIMessage, HumanMessage  # type: ignore


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


@dataclass
class _ThreadSlot:
    last_report_hash: str | None = None
    last_report_text: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    history: Any = field(default=None)  # LCChatHistory
    reports: dict[str, Any] = field(default_factory=dict)


class ConversationMemory:
    def __init__(self) -> None:
        self._slots: dict[str, _ThreadSlot] = {}
        self._lock = threading.Lock()

    # ---- slot management ----
    def _get_slot(self, thread_id: str) -> _ThreadSlot:
        with self._lock:
            if thread_id not in self._slots:
                slot = _ThreadSlot()
                slot.history = LCChatHistory()  # type: ignore
                self._slots[thread_id] = slot
            return self._slots[thread_id]

    # ---- last report hash ----
    def get_last_report_hash(self, thread_id: str) -> str | None:
        return self._get_slot(thread_id).last_report_hash

    def set_last_report_hash(self, thread_id: str, text: str) -> str:
        h = _hash_text(text)
        slot = self._get_slot(thread_id)
        with slot.lock:
            slot.last_report_hash = h
        return h

    # ---- messages ----
    def _append(self, thread_id: str, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        slot = self._get_slot(thread_id)
        with slot.lock:
            if role == "user":
                slot.history.add_message(HumanMessage(content=content))  # type: ignore
            else:
                slot.history.add_message(AIMessage(content=content))  # type: ignore

    def append_user(self, thread_id: str, content: str) -> None:
        if not content:
            return
        last = self.last_message(thread_id)
        if last and last[0] == "user" and (last[1] or "").strip() == content.strip():
            return
        self._append(thread_id, "user", content)

    def append_assistant_if_new(self, thread_id: str, content: str) -> bool:
        if not content:
            return False
        last = self.last_message(thread_id)
        if last and last[0] == "assistant" and (last[1] or "").strip() == content.strip():
            return False
        self._append(thread_id, "assistant", content)
        return True

    def last_message(self, thread_id: str) -> tuple[str, str] | None:
        slot = self._get_slot(thread_id)
        with slot.lock:
            msgs = slot.history.messages  # type: ignore[attr-defined]
            if not msgs:
                return None
            m = msgs[-1]
            role = "assistant" if isinstance(m, AIMessage) else "user"
            return role, str(getattr(m, "content", ""))

    def last_assistant(self, thread_id: str) -> str | None:
        slot = self._get_slot(thread_id)
        with slot.lock:
            for m in reversed(slot.history.messages):  # type: ignore[attr-defined]
                if isinstance(m, AIMessage):
                    return str(getattr(m, "content", ""))
            return None

    def get_history(self, thread_id: str, limit: int = 50) -> list[dict[str, str]]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            out: list[dict[str, str]] = []
            for m in slot.history.messages[-limit:]:  # type: ignore[attr-defined]
                if isinstance(m, AIMessage):
                    out.append({"role": "assistant", "content": str(getattr(m, "content", ""))})
                else:
                    out.append({"role": "user", "content": str(getattr(m, "content", ""))})
            return out

    # ---- analysis persistence ----
    def set_analysis(
        self, thread_id: str, text: str, reports: dict[str, Any] | None = None
    ) -> None:
        slot = self._get_slot(thread_id)
        with slot.lock:
            s = (text or "").strip()
            slot.last_report_text = s or None
            slot.last_report_hash = _hash_text(s) if s else None
            if reports is not None:
                slot.reports = dict(reports or {})

    def get_analysis(self, thread_id: str) -> tuple[str | None, dict[str, Any]]:
        slot = self._get_slot(thread_id)
        with slot.lock:
            return slot.last_report_text, dict(slot.reports or {})


_MEMORY = ConversationMemory()


def get_memory() -> ConversationMemory:
    return _MEMORY
