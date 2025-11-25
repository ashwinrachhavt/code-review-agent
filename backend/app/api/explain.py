from __future__ import annotations

"""Explain/Review API endpoints with streaming.

This module contains thin request handlers that delegate the heavy lifting to
LangGraph nodes. Streaming is implemented via an async generator that listens
to graph events and forwards progress markers and final output.
"""

import asyncio
import json
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.models import ExplainRequest, Message
from graph.state import initial_state


router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}


def _extract_code_from_messages(messages: Optional[List[Message]]) -> str:
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


def _history_from_messages(messages: Optional[List[Message]]) -> List[Dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in (messages or [])][-20:]


@router.post("/explain")
async def explain(request: Request, body: ExplainRequest) -> StreamingResponse:
    graph_app = request.app.state.graph_app  # set in main.py

    code = _extract_code(body)
    if not code:
        return StreamingResponse(iter(["Please provide code to analyze.\n"]), media_type="text/plain")

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    history = _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]

    state = initial_state(code=code, history=history, mode=mode, agents=agents)

    async def event_stream() -> AsyncGenerator[str, None]:
        # Early router progress hint
        yield ":::progress: 5\n"

        # Stream graph events where possible for mid-flight updates
        try:
            async for event in graph_app.astream_events(
                state, config={"configurable": {"thread_id": thread_id}}
            ):
                try:
                    etype = event.get("event")
                    name = event.get("name")
                    data = event.get("data", {})
                    if etype == "on_node_start":
                        if name == "experts_model":
                            yield "🧠 Experts reasoning…\n"
                        elif name == "experts_tools":
                            yield "🧰 Running tools…\n"
                    if etype == "on_node_end":
                        out = data.get("output") or {}
                        # Emit latest progress marker if present
                        prog = out.get("progress")
                        if isinstance(prog, (int, float)):
                            yield f":::progress: {int(prog)}\n"
                        # Emit friendly step logs
                        if name == "router":
                            yield "🔎 Router: language detection done.\n"
                        elif name == "static_analysis":
                            yield "🧹 Static analysis complete.\n"
                        elif name == "security_analysis":
                            yield "🔐 Security heuristics complete.\n"
                        elif name == "experts_finalize":
                            yield "🤝 Experts merged tool findings.\n"
                        elif name == "synthesis":
                            text = out.get("final_report")
                            if isinstance(text, str) and text:
                                yield text
                                yield "\n"
                    elif etype == "on_end":
                        yield ":::progress: 100\n"
                except Exception:
                    # Robust streaming: ignore malformed events
                    continue
        except Exception:
            # Fallback: run synchronously and emit final report
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                yield text
                yield "\n"
            yield ":::progress: 100\n"

    return StreamingResponse(event_stream(), media_type="text/plain")
