from __future__ import annotations

"""Explain/Review API endpoints with streaming.

This module contains thin request handlers that delegate the heavy lifting to
LangGraph nodes. Streaming is implemented via an async generator that listens
to graph events and forwards progress markers and final output.
"""

import re
import uuid
from collections.abc import AsyncGenerator
import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.models import ExplainRequest, Message
from ..core.config import get_settings
from ..core.redis_pubsub import pubsub_messages
from ..celery_app import celery_app  # import to ensure tasks are registered
from ..workers.tasks import run_graph_stream
from graph.state import initial_state

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/health/celery")
async def health_celery() -> dict[str, Any]:
    """Check Celery connectivity.

    - If USE_CELERY=0, returns {status: disabled}
    - Otherwise, pings the worker via control.inspect and a tiny task.
    """

    settings = get_settings()
    if not settings.USE_CELERY:
        return {"status": "disabled"}

    # Default response to degraded; we lift to ok if both checks pass
    info: dict[str, Any] = {"status": "degraded"}

    try:
        # Control ping (doesn't execute a task)
        insp = celery_app.control.inspect(timeout=1.0)
        ctrl = insp.ping() if insp else None
        info["control"] = ctrl
        ctrl_ok = bool(ctrl)
    except Exception as e:  # pragma: no cover - depends on runtime
        info["control_error"] = str(e)
        ctrl_ok = False

    # Task ping (verifies queue/execute path)
    try:
        from ..workers.tasks import ping as ping_task

        async_result = ping_task.delay()
        pong = await asyncio.to_thread(async_result.get, timeout=3)
        info["pong"] = pong
        task_ok = pong == "pong"
    except Exception as e:  # pragma: no cover - depends on runtime
        info["task_error"] = str(e)
        task_ok = False

    info["status"] = "ok" if (ctrl_ok and task_ok) else ("degraded" if (ctrl_ok or task_ok) else "error")
    return info


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
    graph_app = request.app.state.graph_app  # set in main.py
    settings = get_settings()

    code = _extract_code(body)
    if not code:
        # Allow empty code for chat mode
        if (body.mode or "") != "chat":
            return StreamingResponse(
                iter(["Please provide code to analyze.\n"]), media_type="text/plain"
            )

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    history = _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]

    state = initial_state(code=code, history=history, mode=mode, agents=agents)
    # Optional chat query for concise responses in synthesis
    try:
        chat_q = getattr(body, 'chat_query', None) or request.headers.get('x-chat-query')
        if chat_q:
            state["chat_query"] = str(chat_q)
    except Exception:
        pass

    def sse(data: str) -> str:
        return f"data: {data.rstrip()}\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        # Celery-backed streaming via Redis pub/sub
        if settings.USE_CELERY:
            channel = f"sse:{settings.REDIS_NAMESPACE}:{thread_id}"
            # Dispatch background task
            try:
                run_graph_stream.delay(thread_id, state)
            except Exception:
                # Fallback to in-process streaming if Celery unavailable
                pass
            # Stream messages from Redis pub/sub
            try:
                async for msg in pubsub_messages(settings.REDIS_URL, channel):
                    yield sse(msg)
                return
            except Exception:
                # If pub/sub fails, fall through to direct streaming
                ...
        # Early router progress hint (forces immediate flush)
        yield sse(":::progress: 5")

        sent_report = False
        # Track paragraphs we have already emitted to avoid accidental duplicates
        seen_paras: set[str] = set()
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
                            yield sse("🧠 Experts reasoning…")
                        elif name == "experts_tools":
                            yield sse("🧰 Running tools…")
                    if etype == "on_node_end":
                        out = data.get("output") or {}
                        # Emit latest progress marker if present
                        prog = out.get("progress")
                        if isinstance(prog, (int, float)):
                            yield sse(f":::progress: {int(prog)}")
                        # Emit friendly step logs
                        if name == "router":
                            yield sse("🔎 Router: language detection done.")
                        elif name == "static_analysis":
                            yield sse("🧹 Static analysis complete.")
                        elif name == "security_analysis":
                            yield sse("🔐 Security heuristics complete.")
                        elif name == "experts_finalize":
                            yield sse("🤝 Experts merged tool findings.")
                        elif name == "synthesis":
                            # Guard: only emit final report once
                            if not sent_report:
                                text = out.get("final_report")
                                if isinstance(text, str) and text:
                                    for para in text.split("\n\n"):
                                        p = para.strip()
                                        if not p:
                                            continue
                                        if p in seen_paras:
                                            continue
                                        seen_paras.add(p)
                                        yield sse(p)
                                    sent_report = True
                    elif etype == "on_end":
                        yield sse(":::progress: 100")
                except Exception:
                    # Robust streaming: ignore malformed events
                    continue
        except Exception:
            # Fallback: run synchronously and emit final report
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                for para in text.split("\n\n"):
                    if para.strip():
                        yield sse(para)
            yield sse(":::progress: 100")
            return

        # If streaming completed without yielding the final report, emit it now
        if not sent_report:
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                for para in text.split("\n\n"):
                    p = para.strip()
                    if not p:
                        continue
                    if p in seen_paras:
                        continue
                    seen_paras.add(p)
                    yield sse(p)
            yield sse(":::progress: 100")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
