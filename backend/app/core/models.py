from __future__ import annotations

"""Pydantic request/response models for the API layer."""

from typing import List, Optional
from pydantic import BaseModel
try:
    from pydantic import ConfigDict  # pydantic v2
except Exception:  # pragma: no cover
    ConfigDict = dict  # type: ignore


class Message(BaseModel):
    role: str
    content: str


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # accept unknown fields

    # Conversational inputs
    messages: Optional[List[Message]] = None
    code: Optional[str] = None
    thread_id: Optional[str] = None

    # Optional metadata/controls
    mode: Optional[str] = None
    agents: Optional[List[str]] = None
    entry: Optional[str] = None

