from __future__ import annotations

"""Pydantic request/response models for the API layer."""


from pydantic import BaseModel

try:
    from pydantic import ConfigDict  # pydantic v2
except Exception:  # pragma: no cover
    ConfigDict = dict  # type: ignore


class FileInput(BaseModel):
    path: str
    content: str


class Message(BaseModel):
    role: str
    content: str


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # accept unknown fields

    # Conversational inputs
    messages: list[Message] | None = None
    code: str | None = None
    # Optional batch of files (for folder/CLI inputs)
    files: list[FileInput] | None = None
    thread_id: str | None = None

    # Optional metadata/controls
    mode: str | None = None
    agents: list[str] | None = None
    entry: str | None = None

    # Optional source selector: "pasted" | "folder" | "cli"
    source: str | None = None


class ThreadCreate(BaseModel):
    title: str | None = None


class ThreadUpdate(BaseModel):
    title: str | None = None
