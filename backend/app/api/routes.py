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
from backend.app.core.models import ExplainRequest, Message
from backend.app.db.repository import repo
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
                # If final_state is missing, try to reconstruct or fetch
                if not final_state:
                    # Fetch latest state from graph memory if possible, or just save text
                    pass

                file_count = len(state.get("files", []))
                if final_state:
                    file_count = len(final_state.get("files", []))

                repo.update_thread(
                    thread_id,
                    report_text=final_text,
                    state=final_state or {},
                    file_count=file_count,
                )
                logger.info(f"Persisted thread {thread_id}")
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
                    state=final_state or {},
                    file_count=len(file_inputs),
                )
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


@router.post("/chat")
async def chat(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Chat using the graph's conditional route (mode=chat)."""
    graph_app = request.app.state.graph_app

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    question = ""
    if body.messages and body.messages[-1].role == "user":
        question = body.messages[-1].content or ""
        # Persist user message
        try:
            repo.add_message(thread_id, "user", question)
        except Exception:
            pass

    # Prepare chat state; rely on checkpointer for persistent state
    chat_state = {"mode": "chat", "chat_query": question}

    async def stream_chat() -> AsyncGenerator[str, None]:
        acc: list[str] = []
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
                        acc.append(content)
                        yield content

                if etype == "on_node_end" and name == "chat_reply":
                    out = data.get("output") or data.get("result") or {}
                    if isinstance(out, dict):
                        text = out.get("chat_response") or out.get("final_report")
                        if text and not acc:
                            # If no token stream, emit full text in paragraphs
                            for para in str(text).split("\n\n"):
                                p = para.strip()
                                if p:
                                    yield p + "\n\n"
                            acc.append(str(text))
        except Exception as e:
            logger.error("Chat streaming failed: %s", e)
            yield sse("Sorry, I encountered an error generating a response.")

        # Persist assistant reply
        try:
            if acc:
                repo.add_message(thread_id, "assistant", "".join(acc))
        except Exception:
            pass

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "x-thread-id": thread_id,
    }
    return StreamingResponse(stream_chat(), media_type="text/plain", headers=headers)


@router.get("/threads")
async def list_threads(limit: int = 50) -> list[dict]:
    """Return recent threads for the sidebar."""
    try:
        threads = repo.list_threads(limit=limit)
        return [
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
    except Exception:
        return []


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> dict:
    """Return a single thread with state and messages."""
    th = repo.get_thread(thread_id)
    if not th:
        return {}

    msgs = repo.get_messages(thread_id)
    return {
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
