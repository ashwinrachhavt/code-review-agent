from __future__ import annotations

"""Slim API routes: health and explain (streaming).

Keeps routes minimal and defers logic to the LangGraph and memory layer.
"""

import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress

from fastapi import APIRouter, Body, Request
from fastapi.responses import StreamingResponse

from backend.app.core.logging import get_logger
from backend.app.core.models import ExplainRequest, Message
from backend.app.db import repository as repo
from backend.graph.state import initial_state

logger = get_logger(__name__)

# Swagger UI examples for /explain
FIB_SNIPPET = '''
def fib(n: int) -> int:
    """Return the n-th Fibonacci number (iterative)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
'''.strip()

ADD_SNIPPET_MSG = """
Please review this function and suggest improvements:

```python
def add(a, b):
    # no type checks
    return a+b
```
""".strip()
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
async def explain(
    request: Request,
    body: ExplainRequest = Body(  # noqa: B008 - FastAPI pattern for OpenAPI examples
        example={
            "mode": "orchestrator",
            "agents": ["quality", "bug", "security"],
            "code": FIB_SNIPPET,
        },
        examples={
            "python_quality_review": {
                "summary": "Python snippet (orchestrator)",
                "description": "Quick review of a small Python function using quality, bug, and security agents.",
                "value": {
                    "mode": "orchestrator",
                    "agents": ["quality", "bug", "security"],
                    "code": FIB_SNIPPET,
                },
            },
            "chat_about_code": {
                "summary": "Chat about a pasted code block",
                "description": "Start a chat turn by pasting code and asking a question.",
                "value": {
                    "mode": "chat",
                    "messages": [
                        {
                            "role": "user",
                            "content": ADD_SNIPPET_MSG,
                        },
                        {"role": "user", "content": "Is this safe and typed properly?"},
                    ],
                },
            },
        },
    ),
) -> StreamingResponse:
    """Stream code review using the compiled graph with minimal routing logic."""
    graph_app = request.app.state.graph_app  # set in main.py

    code = _extract_code(body)
    if not code and (body.mode or "") != "chat":
        return StreamingResponse(
            iter(["Please provide code to analyze.\n"]), media_type="text/plain"
        )

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    logger.info(
        "Explain request: thread_id=%s mode=%s code_len=%d",
        thread_id,
        body.mode or "orchestrator",
        len(code or ""),
    )
    history = _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]
    state = initial_state(code=code, history=history, mode=mode, agents=agents)
    state["thread_id"] = thread_id
    # Seed source inputs for context engineering
    # Prefer explicit source; otherwise infer from inputs
    source = getattr(body, "source", None)
    if not source:
        source = "folder" if (body.files or []) else "pasted"
    state["source"] = str(source)
    # Pass files if provided
    if body.files:
        state["files"] = [{"path": f.path, "content": f.content} for f in body.files]
    # If user provided an entry path use it as folder hint
    if body.entry:
        state["folder_path"] = body.entry
    # Pass through multi-modal inputs
    if getattr(body, "files", None):
        state["files"] = [{"path": f.path, "content": f.content} for f in (body.files or [])]
    if getattr(body, "source", None):
        state["source"] = body.source

    def sse(data: str) -> str:
        # Prefix each line with 'data: ' per SSE; preserves substring checks in tests
        payload = "\n".join(f"data: {line}" for line in str(data).rstrip("\n").split("\n"))
        return payload + "\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        yield sse(":::progress: 5")

        streamed_chunks: list[str] = []
        final_text: str | None = None
        final_state: dict | None = None
        try:
            async for event in graph_app.astream_events(
                state,
                version="v1",
                config={"configurable": {"thread_id": thread_id}},
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})
                if etype == "on_node_end":
                    out = data.get("output") or {}
                    prog = out.get("progress")
                    if isinstance(prog, (int, float)):
                        yield sse(f":::progress: {int(prog)}")
                    else:
                        logger.debug("Event: %s node=%s", etype, name)
                    if name == "router":
                        yield sse("🔎 Router: language detection done.")
                    elif name == "build_context":
                        yield sse("📚 Context ready.")
                    elif name == "tools_parallel":
                        yield sse("🧪 Tools complete.")
                    elif name == "synthesis":
                        text = out.get("final_report")
                        if isinstance(text, str) and text:
                            final_text = text
                            if isinstance(out, dict):
                                final_state = out
                            for para in text.split("\n\n"):
                                p = para.strip()
                                if p:
                                    streamed_chunks.append(p)
                                    yield sse(p)
        except Exception as e:
            logger.error("Streaming failed; falling back to invoke: %s", e)
            # Fallback to blocking invoke
            final = await graph_app.ainvoke(
                state, config={"configurable": {"thread_id": thread_id}}
            )
            final_text = (final or {}).get("final_report") or None
            if final_text:
                for para in final_text.split("\n\n"):
                    p = para.strip()
                    if p:
                        streamed_chunks.append(p)
                        yield sse(p)
            if isinstance(final, dict):
                final_state = final

        # If no final text was captured during events, invoke once and stream it
        if final_text is None:
            try:
                final = await graph_app.ainvoke(
                    state, config={"configurable": {"thread_id": thread_id}}
                )
                text = (final or {}).get("final_report") or ""
                if text:
                    for para in text.split("\n\n"):
                        p = para.strip()
                        if p:
                            streamed_chunks.append(p)
                            yield sse(p)
                if isinstance(final, dict) and final_state is None:
                    final_state = final
            except Exception as ee:  # pragma: no cover
                logger.error("Final invoke failed: %s", ee)

        # Persist thread for sidebar/history
        if final_text and isinstance(final_state, dict):
            try:
                _ = repo.create_or_update_thread(final_state, final_text, thread_id)
            except Exception as e:
                logger.warning("Thread persistence failed: %s", e)

        yield sse(":::progress: 100")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/chat")
async def chat(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Chat using the graph's conditional route (mode=chat).

    - Loads prior analysis state from the checkpointer
    - Seeds a minimal chat state with chat_query and saved reports
    - Executes only the `chat_reply` node and streams its output
    """
    graph_app = request.app.state.graph_app

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    question = ""
    if body.messages and body.messages[-1].role == "user":
        question = body.messages[-1].content or ""

    # Load saved analysis
    prev_state: dict | None = None
    try:
        prev_state = await graph_app.aget_state({"configurable": {"thread_id": thread_id}})  # type: ignore[attr-defined]
    except Exception:
        with suppress(Exception):
            prev_state = graph_app.get_state({"configurable": {"thread_id": thread_id}})  # type: ignore[attr-defined]

    final_report = (prev_state or {}).get("final_report") if isinstance(prev_state, dict) else None
    if not final_report:
        return StreamingResponse(
            iter(["No analysis found for this thread. Run /explain first."]),
            media_type="text/plain",
        )

    # Prepare chat state
    chat_state = initial_state(code="", history=[], mode="chat", agents=[])
    chat_state["chat_query"] = question
    chat_state["final_report"] = final_report
    for k in ("security_report", "quality_report", "bug_report"):
        if isinstance(prev_state, dict) and prev_state.get(k) is not None:
            chat_state[k] = prev_state.get(k)

    async def stream_chat() -> AsyncGenerator[str, None]:
        acc: list[str] = []
        try:
            async for event in graph_app.astream_events(
                chat_state,
                version="v1",
                config={"configurable": {"thread_id": thread_id}},
            ):
                if event.get("event") == "on_node_end" and event.get("name") == "chat_reply":
                    out = event.get("data", {}).get("output") or {}
                    text = out.get("chat_response")
                    if isinstance(text, str) and text:
                        acc.append(text)
                        yield text
        except Exception:
            # Fallback: blocking invoke
            try:
                res = await graph_app.ainvoke(
                    chat_state, config={"configurable": {"thread_id": thread_id}}
                )
                text = (res or {}).get("chat_response")
                if isinstance(text, str) and text:
                    acc.append(text)
                    yield text
            except Exception:
                fallback = "Unable to generate chat response."
                acc.append(fallback)
                yield fallback
        # Persist assistant reply
        try:
            if acc:
                repo.add_message(thread_id, "assistant", "".join(acc))
        except Exception:
            pass

    return StreamingResponse(stream_chat(), media_type="text/plain")


@router.get("/threads")
async def list_threads(limit: int = 50) -> list[dict]:
    """Return recent threads for the sidebar."""
    try:
        return repo.list_threads(limit=limit)
    except Exception:
        return []


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> dict:
    """Return a single thread with state and messages."""
    th = repo.get_thread(thread_id)
    return th or {}
