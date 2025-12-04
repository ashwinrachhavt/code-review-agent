from __future__ import annotations

"""Slim API routes: health and explain (streaming).

Keeps routes minimal and defers logic to the LangGraph and memory layer.
"""

import re
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Body, Request
from fastapi.responses import StreamingResponse

from backend.app.core.logging import get_logger
from backend.app.core.models import ExplainRequest, Message, ThreadCreate, ThreadUpdate
import json
from backend.app.db.repository import repo
from backend.app.services.cache import (
    cache_get_json,
    cache_set_json,
    cache_delete,
    cache_delete_prefix,
)
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


def sse(data: str) -> str:
    """Format a string payload as an SSE event.

    Ensures each line is prefixed with "data: " and terminated with a blank line,
    matching the SSE contract consumed by the frontend.
    """
    payload = "\n".join(f"data: {line}" for line in str(data).rstrip("\n").split("\n"))
    return payload + "\n\n"


def _safe_state_for_db(state: dict | None) -> dict:
    """Return a JSON-serializable subset of the graph state.

    Avoids persistence failures when nodes include non-serializable objects.
    Keep only keys the UI or follow-up chat might reasonably need.
    """
    if not isinstance(state, dict):
        return {}
    allowed = {
        "files",
        "context",
        "context_stats",
        "security_report",
        "quality_report",
        "bug_report",
        "ast_report",
        "final_report",
        "mode",
        "agents",
        "history",
        "tool_logs",
        "language",
        "source",
        "vectorstore_id",
        "progress",
        "thread_id",
    }
    out: dict = {}
    for k in allowed:
        if k in state:
            out[k] = state[k]
    # Final JSON check; coerce obviously non-serializable leaf values to string
    def _coerce(obj):
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, list):
            return [_coerce(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): _coerce(v) for k, v in obj.items()}
        return str(obj)

    safe = _coerce(out)
    try:
        json.dumps(safe)
    except Exception:
        # Fallback to minimal state if still not JSON-serializable
        safe = {"final_report": str(state.get("final_report") or "")}
    return safe


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/admin/db")
async def db_info() -> dict:
    """Return basic DB and migration info for debugging/hydration checks."""
    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from backend.app.db.db import engine
    from backend.app.core.config import get_settings

    settings = get_settings()
    url = str(settings.DATABASE_URL)
    # Redact password in URL
    if "@" in url and ":" in url.split("@", 1)[0]:
        try:
            left, right = url.split("@", 1)
            scheme_and_user = left.split("://", 1)[-1]
            scheme = url.split("://", 1)[0]
            user = scheme_and_user.split(":", 1)[0]
            url = f"{scheme}://{user}:***@{right}"
        except Exception:
            pass

    alembic_head = None
    try:
        with engine.connect() as conn:
            res = conn.execute(sa_text("SELECT version_num FROM alembic_version"))
            row = res.first()
            if row:
                alembic_head = row[0]
    except Exception:
        alembic_head = None

    try:
        insp = sa_inspect(engine)
        tables = sorted(insp.get_table_names())
    except Exception:
        tables = []

    return {
        "database_url": url,
        "alembic_head": alembic_head,
        "tables": tables,
    }


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
    body: ExplainRequest = Body(...),
) -> StreamingResponse:
    """Stream code review using the compiled graph with minimal routing logic."""
    graph_app = request.app.state.graph_app  # set in main.py

    code = _extract_code(body)
    if not code and (body.mode or "") != "chat" and not body.files and not body.entry:
        return StreamingResponse(
            iter(["Please provide code, files, or a folder path to analyze.\n"]),
            media_type="text/plain",
        )

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    # Ensure thread exists so messages persist even if chat is called first
    try:
        repo.create_thread(thread_id, title=f"Analysis {thread_id[:8]}")
    except Exception:
        pass

    # Create thread immediately
    try:
        repo.create_thread(thread_id, title=f"Analysis {thread_id[:8]}")
    except Exception:
        pass  # Might already exist

    logger.info(
        "Explain request: thread_id=%s mode=%s",
        thread_id,
        body.mode or "orchestrator",
    )

    history = _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]

    # Initial state setup
    state = initial_state(code=code, history=history, mode=mode, agents=agents)
    state["thread_id"] = thread_id

    # Determine source and inputs
    source = getattr(body, "source", None)
    if not source:
        if body.files or body.entry:
            source = "folder"
        else:
            source = "pasted"

    state["source"] = str(source)

    if body.files:
        state["files"] = [{"path": f.path, "content": f.content} for f in body.files]

    if body.entry:
        state["folder_path"] = body.entry

    async def event_stream() -> AsyncGenerator[str, None]:
        yield sse(":::progress: 5")

        streamed_chunks: list[str] = []
        final_text: str | None = None
        final_state: dict | None = None

        try:
            async for event in graph_app.astream_events(
                state,
                version="v2",
                config={"configurable": {"thread_id": thread_id}},
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})

                # Progress updates based on node completion
                if etype == "on_node_end":
                    if name == "router":
                        yield sse(":::progress: 10")
                        yield sse("🔎 Router: language detection done.")
                    elif name == "build_context":
                        yield sse(":::progress: 20")
                        yield sse("📚 Context ready.")
                        stats = data.get("output", {}).get("context_stats", {})
                        if stats:
                            yield sse(
                                f"📚 Context: {stats.get('disk_files', 0)} files ({stats.get('disk_bytes', 0)} bytes)"
                            )
                    elif name == "tools_parallel":
                        yield sse(":::progress: 40")
                        yield sse("🧪 Tools complete.")
                    elif name == "collector":
                        yield sse(":::progress: 60")
                        yield sse("🧠 Expert analysis collected.")
                    elif name == "synthesis":
                        yield sse(":::progress: 90")
                        out = data.get("output") or {}
                        # Some langgraph versions provide {"output": {...}} while others may use {"result": {...}}
                        if not out and isinstance(data, dict):
                            out = data.get("result") or {}
                        if isinstance(out, dict):
                            final_state = out
                            final_text = out.get("final_report")
                            # Stream the final report paragraphs immediately
                            if final_text:
                                for para in (final_text or "").split("\n\n"):
                                    p = para.strip()
                                    if p:
                                        yield sse(p)

                # Stream LLM tokens for synthesis (when node uses a streaming LLM)
                if etype == "on_chat_model_stream" and name == "synthesis":
                    chunk = data.get("chunk")
                    content = ""
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, dict):
                        content = chunk.get("content", "")

                    if content:
                        streamed_chunks.append(content)
                        yield sse(content)

                # Capture graph end outputs if provided
                if etype == "on_graph_end":
                    out = data.get("output") or data.get("result") or {}
                    if isinstance(out, dict):
                        final_state = out
                        final_text = final_text or out.get("final_report")

        except Exception as e:
            logger.error("Streaming failed; falling back to invoke: %s", e)

        # If we reached here without final text (either due to no streaming tokens
        # or because event payload did not include outputs), do a final ainvoke.
        if not final_text:
            try:
                final = await graph_app.ainvoke(
                    state, config={"configurable": {"thread_id": thread_id}}
                )
                final_text = (final or {}).get("final_report") or None
                if isinstance(final, dict):
                    final_state = final
                if final_text:
                    for para in final_text.split("\n\n"):
                        p = para.strip()
                        if p:
                            yield sse(p)
            except Exception as inv_err:
                logger.error("Fallback ainvoke failed: %s", inv_err)

        # If we streamed chunks but didn't get final_text from node output
        if not final_text and streamed_chunks:
            final_text = "".join(streamed_chunks)

        # Persist thread for sidebar/history
        if final_text:
            try:
                file_count = len(state.get("files", []))
                if isinstance(final_state, dict) and isinstance(final_state.get("files"), list):
                    file_count = len(final_state.get("files", []))

                repo.update_thread(
                    thread_id,
                    report_text=final_text,
                    state=_safe_state_for_db(final_state),
                    file_count=file_count,
                )
                # Invalidate caches on write
                cache_delete(f"threads:item:{thread_id}")
                cache_delete_prefix("threads:list:")
                logger.info("Persisted thread %s", thread_id)
            except Exception as e:
                logger.warning("Thread persistence failed: %s", e)
        else:
            logger.warning(f"No final text to persist for thread {thread_id}")

        yield sse("💬 Chat ready. Use the sidebar to ask follow-ups.")
        yield sse(":::progress: 100")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
        # Allow browsers to read custom thread id header across CORS
        "Access-Control-Expose-Headers": "x-thread-id",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/explain/upload")
async def explain_upload(
    request: Request,
) -> StreamingResponse:
    """Accept multipart file upload for analysis."""

    # Get form data
    form = await request.form()
    uploaded_files = form.getlist("files")
    mode = form.get("mode", "orchestrator")
    agents_str = form.get("agents", "quality,bug,security")
    agents = [a.strip() for a in str(agents_str).split(",") if a.strip()]

    if not uploaded_files:
        return StreamingResponse(iter(["No files uploaded.\n"]), media_type="text/plain")

    # Read uploaded files
    file_inputs = []
    for upload in uploaded_files:
        if hasattr(upload, "read"):
            content = await upload.read()
            try:
                text = content.decode("utf-8")
                file_inputs.append({"path": upload.filename or "uploaded_file", "content": text})
            except UnicodeDecodeError:
                continue

    if not file_inputs:
        return StreamingResponse(iter(["No valid text files found.\n"]), media_type="text/plain")

    graph_app = request.app.state.graph_app
    thread_id = str(uuid.uuid4())

    # Create thread
    try:
        repo.create_thread(thread_id, title=f"Upload Analysis {thread_id[:8]}")
    except Exception:
        pass

    state = initial_state(code="", history=[], mode=str(mode), agents=agents)
    state["thread_id"] = thread_id
    state["source"] = "folder"
    state["files"] = file_inputs

    logger.info(
        "Upload request: thread_id=%s files=%d mode=%s",
        thread_id,
        len(file_inputs),
        mode,
    )

    # Reuse the same streaming logic

    async def event_stream() -> AsyncGenerator[str, None]:
        yield sse(":::progress: 5")
        yield sse(f"📁 Uploaded {len(file_inputs)} files")

        streamed_chunks: list[str] = []
        final_text: str | None = None
        final_state: dict | None = None

        try:
            async for event in graph_app.astream_events(
                state,
                version="v2",
                config={"configurable": {"thread_id": thread_id}},
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})

                if etype == "on_node_end":
                    if name == "router":
                        yield sse(":::progress: 10")
                        yield sse("🔎 Router: language detection done.")
                    elif name == "build_context":
                        yield sse(":::progress: 20")
                        yield sse("📚 Context ready.")
                    elif name == "tools_parallel":
                        yield sse(":::progress: 40")
                        yield sse("🧪 Tools complete.")
                    elif name == "collector":
                        yield sse(":::progress: 60")
                        yield sse("🧠 Expert analysis collected.")
                    elif name == "synthesis":
                        yield sse(":::progress: 90")
                        out = data.get("output") or data.get("result") or {}
                        if isinstance(out, dict):
                            final_state = out
                            final_text = out.get("final_report")

                if etype == "on_chat_model_stream" and name == "synthesis":
                    chunk = data.get("chunk")
                    content = ""
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, dict):
                        content = chunk.get("content", "")

                    if content:
                        streamed_chunks.append(content)
                        yield sse(content)
        except Exception as e:
            logger.error("Upload streaming failed: %s", e)

        if not final_text:
            try:
                final = await graph_app.ainvoke(
                    state, config={"configurable": {"thread_id": thread_id}}
                )
                final_text = (final or {}).get("final_report") or None
                if isinstance(final, dict):
                    final_state = final
                if final_text:
                    for para in final_text.split("\n\n"):
                        p = para.strip()
                        if p:
                            yield sse(p)
            except Exception:
                pass

        if not final_text and streamed_chunks:
            final_text = "".join(streamed_chunks)

        if final_text:
            try:
                repo.update_thread(
                    thread_id,
                    report_text=final_text,
                    state=_safe_state_for_db(final_state),
                    file_count=len(file_inputs),
                )
                cache_delete(f"threads:item:{thread_id}")
                cache_delete_prefix("threads:list:")
            except Exception:
                pass

        yield sse("💬 Chat ready. Use the sidebar to ask follow-ups.")
        yield sse(":::progress: 100")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
        "Access-Control-Expose-Headers": "x-thread-id",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/analyze")
async def analyze(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Alias for /explain to match frontend proxy expectations.

    Some frontend routes send requests to /analyze; keep API thin by delegating.
    """
    return await explain(request, body)


@router.post("/chat")
async def chat(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Chat using the graph's conditional route (mode=chat)."""
    graph_app = request.app.state.graph_app

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    question = ""
    incoming_history = _history_from_messages(body.messages)
    if body.messages and body.messages[-1].role == "user":
        question = body.messages[-1].content or ""
        # Persist user message
        try:
            repo.add_message(thread_id, "user", question)
        except Exception:
            pass

    # Prepare chat state; merge any persisted analysis state so chat is grounded
    # even when the LangGraph checkpointer is disabled or not yet warmed.
    persisted_state: dict | None = None
    try:
        th = repo.get_thread(thread_id)
        if th and isinstance(th.state_json, dict):
            persisted_state = th.state_json
    except Exception:
        persisted_state = None

    chat_state: dict = {"mode": "chat", "chat_query": question}
    if isinstance(persisted_state, dict):
        # Shallow merge is sufficient; downstream nodes read keys like
        # final_report, security_report, quality_report, bug_report, vectorstore_id
        chat_state = {**persisted_state, **chat_state}

    # Include recent conversation history for better free-form chat
    try:
        _msgs = repo.get_messages(thread_id)
        persisted_history = [
            {"role": m.role, "content": m.content} for m in _msgs[-20:]
        ]
    except Exception:
        persisted_history = []

    merged_history: list[dict] = []
    if persisted_history:
        merged_history.extend(persisted_history)
    if incoming_history:
        tail = set((m.get("role"), m.get("content")) for m in merged_history[-20:])
        for m in incoming_history:
            key = (m.get("role"), m.get("content"))
            if key not in tail:
                merged_history.append(m)
    if merged_history:
        chat_state["history"] = merged_history[-20:]

    async def stream_chat() -> AsyncGenerator[str, None]:
        chunks: list[str] = []
        final_reply_text: str | None = None
        persisted = False

        def _append_chunk(text: str) -> None:
            nonlocal final_reply_text
            if not text:
                return
            chunks.append(text)
            final_reply_text = "".join(chunks)

        def _persist_assistant_reply() -> None:
            nonlocal persisted, final_reply_text
            if persisted:
                return
            try:
                reply_text = (final_reply_text or "".join(chunks)).strip()
                if reply_text:
                    repo.add_message(thread_id, "assistant", reply_text)
                    # Touch thread.updated_at without changing other fields
                    repo.update_thread(thread_id, title=None)
                persisted = True
            except Exception as persist_err:
                logger.warning("Chat persistence failed for %s: %s", thread_id, persist_err)

        # Emit initial progress to nudge clients to render
        yield sse(":::progress: 5")
        try:
            async for event in graph_app.astream_events(
                chat_state,
                version="v2",
                config={"configurable": {"thread_id": thread_id}},
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})

                if etype == "on_chat_model_stream" and name == "chat_reply":
                    chunk = data.get("chunk")
                    content = ""
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, dict):
                        content = chunk.get("content", "")
                    if content:
                        _append_chunk(content)
                        # Stream as SSE for consistency with frontend parsing
                        yield sse(content)

                if etype == "on_node_end" and name == "chat_reply":
                    out = data.get("output") or data.get("result") or data.get("state") or {}
                    if isinstance(out, dict):
                        text = out.get("chat_response")
                        if text and not chunks:
                            # If no token stream, emit full text in paragraphs
                            for para in str(text).split("\n\n"):
                                p = para.strip()
                                if p:
                                    yield sse(p)
                            _append_chunk(str(text))
                        # Persist promptly on node completion
                        _persist_assistant_reply()

                # Some langgraph versions only surface final output on graph end
                if etype == "on_graph_end" and not chunks:
                    out = data.get("output") or data.get("result") or {}
                    if isinstance(out, dict):
                        text = out.get("chat_response")
                        if text:
                            for para in str(text).split("\n\n"):
                                p = para.strip()
                                if p:
                                    yield sse(p)
                            _append_chunk(str(text))
                        _persist_assistant_reply()
        except Exception as e:
            logger.error("Chat streaming failed: %s", e)
            fallback = "Sorry, I encountered an error generating a response."
            yield sse(fallback)
            _append_chunk(fallback)

        # If nothing was emitted via events, fall back to a final invoke
        if not chunks:
            try:
                final = await graph_app.ainvoke(
                    chat_state, config={"configurable": {"thread_id": thread_id}}
                )
                text = (final or {}).get("chat_response")
                if text:
                    for para in str(text).split("\n\n"):
                        p = para.strip()
                        if p:
                            yield sse(p)
                    _append_chunk(str(text))
                _persist_assistant_reply()
            except Exception as inv_err:
                logger.error("Chat fallback ainvoke failed: %s", inv_err)

        # Absolute fallback so the UI always receives a response
        if not chunks:
            fallback_text = (
                "No response generated. If this thread has no prior analysis, run an analysis "
                "first, then ask a follow-up question."
            )
            yield sse(fallback_text)
            _append_chunk(fallback_text)
            _persist_assistant_reply()

        # Final done marker and 100% progress to signal completion
        yield sse(":::progress: 100")
        yield sse(":::done")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
        "Access-Control-Expose-Headers": "x-thread-id",
    }
    return StreamingResponse(stream_chat(), media_type="text/event-stream", headers=headers)


@router.get("/threads")
async def list_threads(limit: int = 50) -> list[dict]:
    """Return recent threads for the sidebar."""
    try:
        # Try cache first
        cache_key = f"threads:list:{int(limit)}"
        cached = cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached

        threads = repo.list_threads(limit=limit)
        out = [
            {
                "thread_id": t.id,
                "title": t.title,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
                "file_count": t.file_count,
                "summary": t.title,  # Alias for frontend
            }
            for t in threads
        ]
        cache_set_json(cache_key, out, ttl_seconds=30)
        return out
    except Exception:
        return []


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> dict:
    """Return a single thread with state and messages."""
    # Cache first
    cache_key = f"threads:item:{thread_id}"
    cached = cache_get_json(cache_key)
    if isinstance(cached, dict) and cached.get("thread_id"):
        return cached

    th = repo.get_thread(thread_id)
    if not th:
        return {}

    msgs = repo.get_messages(thread_id)
    out = {
        "thread_id": th.id,
        "title": th.title,
        "report_text": th.report_text,
        "state": th.state_json,
        "created_at": th.created_at.isoformat(),
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in msgs
        ],
    }
    cache_set_json(cache_key, out, ttl_seconds=30)
    return out


# CRUD for threads
@router.post("/threads")
async def create_thread(body: ThreadCreate | None = None) -> dict:
    """Create an empty thread and return its metadata."""
    title = (body.title if body else None) or "New Analysis"
    thread_id = str(uuid.uuid4())
    try:
        th = repo.create_thread(thread_id, title=title)
        cache_delete_prefix("threads:list:")
        return {
            "thread_id": th.id,
            "title": th.title,
            "created_at": th.created_at.isoformat(),
            "updated_at": th.updated_at.isoformat(),
            "file_count": th.file_count,
        }
    except Exception:
        return {}


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: str, body: ThreadUpdate) -> dict:
    """Update thread metadata (e.g., title)."""
    try:
        th = repo.update_thread(thread_id, title=body.title)
        cache_delete(f"threads:item:{thread_id}")
        cache_delete_prefix("threads:list:")
        return {
            "thread_id": th.id,
            "title": th.title,
            "created_at": th.created_at.isoformat(),
            "updated_at": th.updated_at.isoformat(),
            "file_count": th.file_count,
        }
    except Exception:
        return {}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str) -> dict:
    """Delete a thread and its messages."""
    try:
        ok = repo.delete_thread(thread_id)
        cache_delete(f"threads:item:{thread_id}")
        cache_delete_prefix("threads:list:")
        return {"deleted": bool(ok)}
    except Exception:
        return {"deleted": False}
