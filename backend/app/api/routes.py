from __future__ import annotations

"""Slim API routes: health and explain (streaming).

Keeps routes minimal and defers logic to the LangGraph and memory layer.
"""

import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.app.core.memory import get_memory
from backend.app.core.models import ExplainRequest, Message
from backend.graph.state import initial_state

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


def _extract_code_from_messages(messages: list[Message] | None) -> str:
    """Extract a code block (``` ... ```) from messages; fallback to last user text."""
    fence = re.compile(r"```[a-zA-Z0-9_\-]*\n([\s\S]*?)```", re.MULTILINE)
    for msg in reversed(messages or []):
        for m in fence.finditer(msg.content or ""):
            block = m.group(1).strip()
            if block:
                return block
    return (messages[-1].content if messages else "").strip()


def _extract_code(req: ExplainRequest) -> str:
    code = req.code or _extract_code_from_messages(req.messages)
    return code or ""


def _history_from_messages(messages: list[Message] | None) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in (messages or [])][-20:]


@router.post("/explain")
async def explain(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Stream code review using the compiled graph with minimal routing logic."""
    graph_app = request.app.state.graph_app  # set in main.py

    code = _extract_code(body)
    if not code and (body.mode or "") != "chat":
        return StreamingResponse(
            iter(["Please provide code to analyze.\n"]), media_type="text/plain"
        )

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    mem = get_memory()

    # Merge incoming messages into memory so threads accumulate history
    if body.messages:
        for m in body.messages:
            with suppress(Exception):
                if (m.role or "").lower() == "user":
                    mem.append_user(thread_id, m.content or "")

    history = mem.get_history(thread_id, limit=20) or _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]
    state = initial_state(code=code, history=history, mode=mode, agents=agents)

    def sse(data: str) -> str:
        # Prefix each line with 'data: ' per SSE; preserves substring checks in tests
        payload = "\n".join(f"data: {line}" for line in str(data).rstrip("\n").split("\n"))
        return payload + "\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        yield sse(":::progress: 5")

        streamed_chunks: list[str] = []
        final_text: str | None = None
        try:
            async for event in graph_app.astream_events(
                state, config={"configurable": {"thread_id": thread_id}}
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})
                if etype == "on_node_end":
                    out = data.get("output") or {}
                    prog = out.get("progress")
                    if isinstance(prog, (int, float)):
                        yield sse(f":::progress: {int(prog)}")
                    if name == "router":
                        yield sse("🔎 Router: language detection done.")
                    elif name == "tools_parallel":
                        yield sse("🧪 Tools complete.")
                    elif name == "synthesis":
                        text = out.get("final_report")
                        if isinstance(text, str) and text:
                            final_text = text
                            for para in text.split("\n\n"):
                                p = para.strip()
                                if p:
                                    streamed_chunks.append(p)
                                    yield sse(p)
        except Exception:
            # Fallback to blocking invoke
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            final_text = (final or {}).get("final_report") or None
            if final_text:
                for para in final_text.split("\n\n"):
                    p = para.strip()
                    if p:
                        streamed_chunks.append(p)
                        yield sse(p)

        # Persist the latest analysis to memory for chat
        if final_text:
            reports = {
                "security_report": state.get("security_report"),
                "quality_report": state.get("quality_report"),
                "bug_report": state.get("bug_report"),
            }
            with suppress(Exception):
                mem.set_analysis(thread_id, final_text, reports)

        yield sse(":::progress: 100")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
