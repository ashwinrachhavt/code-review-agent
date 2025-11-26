from __future__ import annotations

"""Explain/Review API endpoints with streaming.

This module contains thin request handlers that delegate the heavy lifting to
LangGraph nodes. Streaming is implemented via an async generator that listens
to graph events and forwards progress markers and final output.
"""

import asyncio
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.app.core.memory import get_memory
from backend.app.core.models import ExplainRequest, Message
from backend.graph.state import initial_state

try:  # Optional, used to avoid double-adding the same user message
    from langchain_core.messages import HumanMessage  # type: ignore
except Exception:  # pragma: no cover
    HumanMessage = object  # type: ignore

from backend.app.celery_app import celery_app  # import to ensure tasks are registered
from backend.app.core.config import get_settings
from backend.app.core.redis_pubsub import pubsub_messages
from backend.app.workers.tasks import run_graph_stream

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
        from backend.app.workers.tasks import ping as ping_task

        async_result = ping_task.delay()
        pong = await asyncio.to_thread(async_result.get, timeout=3)
        info["pong"] = pong
        task_ok = pong == "pong"
    except Exception as e:  # pragma: no cover - depends on runtime
        info["task_error"] = str(e)
        task_ok = False

    info["status"] = (
        "ok" if (ctrl_ok and task_ok) else ("degraded" if (ctrl_ok or task_ok) else "error")
    )
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
    if not code and (body.mode or "") != "chat":
        return StreamingResponse(
            iter(["Please provide code to analyze.\n"]), media_type="text/plain"
        )

    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())

    mem = get_memory()
    # Merge incoming messages (if provided) into memory to keep thread context
    if body.messages:
        for m in body.messages:
            try:
                if (m.role or "").lower() == "user":
                    mem.append_user(thread_id, m.content or "")
            except Exception:
                continue

    # Build conversation history for the graph state from memory (fallback to request)
    history = mem.get_history(thread_id, limit=20) or _history_from_messages(body.messages)
    mode = body.mode or "orchestrator"
    agents = body.agents or ["quality", "bug", "security"]

    state = initial_state(code=code, history=history, mode=mode, agents=agents)
    # Optional chat query for concise responses in synthesis
    try:
        # Prefer header; then body extra fields
        chat_q = request.headers.get("x-chat-query")
        if not chat_q:
            # Pydantic v2 extra fields live under model_extra
            chat_q = getattr(body, "chat_query", None)
            if chat_q is None:
                with suppress(Exception):  # type: ignore[reportGeneralTypeIssues]
                    extra = getattr(body, "model_extra", None) or getattr(
                        body, "__pydantic_extra__", None
                    )
                    if isinstance(extra, dict):
                        chat_q = extra.get("chat_query")
        if chat_q:
            state["chat_query"] = str(chat_q)
            # Append chat query as a user message for conversational context
            try:
                mem.append_user(thread_id, str(chat_q))
            except Exception:
                ...
    except Exception:
        pass
    # Set chat_mode flag for downstream nodes
    if mode == "chat":
        state["chat_mode"] = True

    def sse(data: str) -> str:
        """Format a Server-Sent Event payload.

        Per the SSE spec, each line of the event data must be prefixed with
        "data: ". This ensures multi-line messages are delivered as a single
        logical event and prevents clients from misinterpreting embedded newlines
        as separate events.
        """
        payload = "\n".join(f"data: {line}" for line in str(data).rstrip("\n").split("\n"))
        return payload + "\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        # Celery-backed streaming via Redis pub/sub
        if settings.USE_CELERY:
            channel = f"sse:{settings.REDIS_NAMESPACE}:{thread_id}"
            # Dispatch background task
            with suppress(Exception):
                run_graph_stream.delay(thread_id, state)
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
        # Accumulate streamed paragraphs; track paragraphs we have already
        # emitted during this response to avoid accidental duplicates.
        streamed_chunks: list[str] = []
        try:
            seen_seed = mem.get_seen_paragraphs(thread_id) if mode == "chat" else []
        except Exception:
            seen_seed = []
        seen_paras: set[str] = set(seen_seed)

        # Stream graph events where possible for mid-flight updates
        # Lightweight semantic dedupe across paragraphs within this response
        def _too_similar(a: str, b: str) -> bool:
            import re

            ta = set(re.findall(r"[a-z0-9]+", a.lower()))
            tb = set(re.findall(r"[a-z0-9]+", b.lower()))
            if not ta or not tb:
                return False
            inter = len(ta & tb)
            union = len(ta | tb)
            sim = inter / union if union else 0.0
            return sim >= 0.85

        prior_paras: list[str] = []
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
                        elif name == "synthesis" and not sent_report:
                            text = out.get("final_report")
                            if isinstance(text, str) and text:
                                if mode == "chat":
                                    # Avoid repeating identical assistant message in chat
                                    last_ai = mem.last_assistant(thread_id)
                                    if last_ai and last_ai.strip() == text.strip():
                                        msg = "(no new insights; ask a new question or modify code)"
                                        yield sse(msg)
                                        streamed_chunks.append(msg)
                                        sent_report = True
                                    else:
                                        for para in text.split("\n\n"):
                                            p = para.strip()
                                            if not p:
                                                continue
                                            # De-duplicate repeated lines within a paragraph
                                            lines = [ln.rstrip() for ln in p.split("\n")]
                                            unique_lines: list[str] = []
                                            seen_l: set[str] = set()
                                            for ln in lines:
                                                key = ln.strip()
                                                if not key:
                                                    unique_lines.append(ln)
                                                    continue
                                                if key in seen_l:
                                                    continue
                                                seen_l.add(key)
                                                unique_lines.append(ln)
                                            p_out = "\n".join(unique_lines).strip()
                                            if not p_out or p_out in seen_paras:
                                                continue
                                            # Drop paragraphs that are near-duplicates of earlier ones
                                            if any(_too_similar(p_out, q) for q in prior_paras):
                                                continue
                                            seen_paras.add(p_out)
                                            yield sse(p_out)
                                            streamed_chunks.append(p_out)
                                            prior_paras.append(p_out)
                                        mem.append_assistant_if_new(thread_id, text)
                                        sent_report = True
                                else:
                                    # Non-chat: avoid repeating identical full review
                                    try:
                                        last_h = mem.get_last_report_hash(thread_id)
                                        cur_h = mem.set_last_report_hash(thread_id, text)
                                    except Exception:
                                        last_h = cur_h = None
                                    if last_h and cur_h and last_h == cur_h:
                                        msg = "(no changes since last review)"
                                        yield sse(msg)
                                        streamed_chunks.append(msg)
                                        sent_report = True
                                    else:
                                        for para in text.split("\n\n"):
                                            p = para.strip()
                                            if not p:
                                                continue
                                            lines = [ln.rstrip() for ln in p.split("\n")]
                                            unique_lines: list[str] = []
                                            seen_l: set[str] = set()
                                            for ln in lines:
                                                key = ln.strip()
                                                if not key:
                                                    unique_lines.append(ln)
                                                    continue
                                                if key in seen_l:
                                                    continue
                                                seen_l.add(key)
                                                unique_lines.append(ln)
                                            p_out = "\n".join(unique_lines).strip()
                                            if not p_out or p_out in seen_paras:
                                                continue
                                            if any(_too_similar(p_out, q) for q in prior_paras):
                                                continue
                                            seen_paras.add(p_out)
                                            yield sse(p_out)
                                            streamed_chunks.append(p_out)
                                            prior_paras.append(p_out)
                                        sent_report = True
                    elif etype == "on_end":
                        yield sse(":::progress: 100")
                except Exception:
                    # Robust streaming: ignore malformed events
                    continue
        except Exception:
            # Fallback: run synchronously and emit final report with dedupe
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                # Chat-mode: avoid repeating identical assistant reply
                if mode == "chat":
                    last_ai = mem.last_assistant(thread_id)
                    if last_ai and last_ai.strip() == text.strip():
                        msg = "(no new insights; try a different question)"
                        yield sse(msg)
                        streamed_chunks.append(msg)
                    else:
                        for para in text.split("\n\n"):
                            p = para.strip()
                            if not p:
                                continue
                            lines = [ln.rstrip() for ln in p.split("\n")]
                            unique_lines: list[str] = []
                            seen_l: set[str] = set()
                            for ln in lines:
                                key = ln.strip()
                                if not key:
                                    unique_lines.append(ln)
                                    continue
                                if key in seen_l:
                                    continue
                                seen_l.add(key)
                                unique_lines.append(ln)
                            p_out = "\n".join(unique_lines).strip()
                            if not p_out or p_out in seen_paras:
                                continue
                            if any(_too_similar(p_out, q) for q in prior_paras):
                                continue
                            seen_paras.add(p_out)
                            yield sse(p_out)
                            streamed_chunks.append(p_out)
                            prior_paras.append(p_out)
                        mem.append_assistant_if_new(thread_id, text)
                else:
                    # Non-chat: if same report as last time, indicate no changes
                    try:
                        last_h = mem.get_last_report_hash(thread_id)
                        cur_h = mem.set_last_report_hash(thread_id, text)
                    except Exception:
                        last_h = cur_h = None
                    if last_h and cur_h and last_h == cur_h:
                        msg = "(no changes since last review)"
                        yield sse(msg)
                        streamed_chunks.append(msg)
                    else:
                        for para in text.split("\n\n"):
                            p = para.strip()
                            if not p:
                                continue
                            lines = [ln.rstrip() for ln in p.split("\n")]
                            unique_lines: list[str] = []
                            seen_l: set[str] = set()
                            for ln in lines:
                                key = ln.strip()
                                if not key:
                                    unique_lines.append(ln)
                                    continue
                                if key in seen_l:
                                    continue
                                seen_l.add(key)
                                unique_lines.append(ln)
                            p_out = "\n".join(unique_lines).strip()
                            if not p_out or p_out in seen_paras:
                                continue
                            seen_paras.add(p_out)
                            yield sse(p_out)
                            streamed_chunks.append(p_out)
            yield sse(":::progress: 100")
            return

        # If streaming completed without yielding the final report, emit it now
        if not sent_report:
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                if mode == "chat":
                    last_msg = mem.last_message(thread_id)
                    if (
                        last_msg
                        and last_msg[0] == "assistant"
                        and (last_msg[1] or "").strip() == text.strip()
                    ):
                        msg = "(no new insights; try a different question)"
                        yield sse(msg)
                        streamed_chunks.append(msg)
                    else:
                        for para in text.split("\n\n"):
                            p = para.strip()
                            if not p:
                                continue
                            lines = [ln.rstrip() for ln in p.split("\n")]
                            unique_lines: list[str] = []
                            seen_l: set[str] = set()
                            for ln in lines:
                                key = ln.strip()
                                if not key:
                                    unique_lines.append(ln)
                                    continue
                                if key in seen_l:
                                    continue
                                seen_l.add(key)
                                unique_lines.append(ln)
                            p_out = "\n".join(unique_lines).strip()
                            if not p_out or p_out in seen_paras:
                                continue
                            seen_paras.add(p_out)
                            yield sse(p_out)
                            streamed_chunks.append(p_out)
                        mem.append_assistant_if_new(thread_id, text)
                else:
                    try:
                        last_h = mem.get_last_report_hash(thread_id)
                        cur_h = mem.set_last_report_hash(thread_id, text)
                    except Exception:
                        last_h = cur_h = None
                    if last_h and cur_h and last_h == cur_h:
                        msg = "(no changes since last review)"
                        yield sse(msg)
                        streamed_chunks.append(msg)
                    else:
                        for para in text.split("\n\n"):
                            p = para.strip()
                            if not p or p in seen_paras:
                                continue
                            seen_paras.add(p)
                            yield sse(p)
                            streamed_chunks.append(p)
            yield sse(":::progress: 100")

        # Persist assistant message and update seen paragraphs
        try:
            if streamed_chunks:
                mem.append_assistant_if_new(thread_id, "\n\n".join(streamed_chunks))
                if mode == "chat":
                    mem.add_seen_paragraphs(thread_id, streamed_chunks)
        except Exception:
            ...

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


# ---------- New: Split Analyze & Chat Endpoints ----------


@router.post("/analyze")
async def analyze(request: Request, body: ExplainRequest) -> StreamingResponse:
    """Run full analysis and persist latest report/state to thread memory.

    Input: { code, thread_id?, agents? }
    Streams progress/messages via SSE and stores final report + structured reports.
    """
    settings = get_settings()
    mem = get_memory()
    code = _extract_code(body)
    if not code:
        return StreamingResponse(
            iter(["Please provide code to analyze.\n"]), media_type="text/plain"
        )
    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())
    agents = body.agents or ["quality", "bug", "security"]
    history = mem.get_history(thread_id, limit=20)
    state = initial_state(code=code, history=history, mode="orchestrator", agents=agents)
    graph_app = request.app.state.graph_app

    def sse(data: str) -> str:
        return f"data: {data.rstrip()}\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        yield sse(":::progress: 5")
        streamed_chunks: list[str] = []
        try:
            async for event in graph_app.astream_events(
                state, config={"configurable": {"thread_id": thread_id}}
            ):
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
                    prog = out.get("progress")
                    if isinstance(prog, (int, float)):
                        yield sse(f":::progress: {int(prog)}")
                    if name == "router":
                        yield sse("🔎 Router: language detection done.")
                    elif name == "static_analysis":
                        yield sse("🧹 Static analysis complete.")
                    elif name == "security_analysis":
                        yield sse("🔐 Security heuristics complete.")
                    elif name == "experts_finalize":
                        yield sse("🤝 Experts merged tool findings.")
                    elif name == "synthesis":
                        text = out.get("final_report")
                        if isinstance(text, str) and text:
                            # stream paragraphs
                            for para in text.split("\n\n"):
                                p = para.strip()
                                if p:
                                    streamed_chunks.append(p)
                                    yield sse(p)
            # Done; persist latest analysis
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            reports = {
                "security_report": (final or {}).get("security_report"),
                "quality_report": (final or {}).get("quality_report"),
                "bug_report": (final or {}).get("bug_report"),
            }
            text = (final or {}).get("final_report") or "\n\n".join(streamed_chunks)

            # If we didn't stream any chunks during events, stream the final report now
            if not streamed_chunks and text:
                for para in text.split("\n\n"):
                    p = para.strip()
                    if p:
                        yield sse(p)
                        streamed_chunks.append(p)

            try:
                mem.set_analysis(thread_id, text or "", reports)
            except Exception:
                ...
            yield sse(":::progress: 100")
        except Exception:
            # Fallback invoke and persist
            final = graph_app.invoke(state, config={"configurable": {"thread_id": thread_id}})
            text = (final or {}).get("final_report") or ""
            if text:
                for para in text.split("\n\n"):
                    p = para.strip()
                    if p:
                        yield sse(p)
                        streamed_chunks.append(p)
            try:
                reports = {
                    "security_report": (final or {}).get("security_report"),
                    "quality_report": (final or {}).get("quality_report"),
                    "bug_report": (final or {}).get("bug_report"),
                }
                mem.set_analysis(thread_id, text or "\n\n".join(streamed_chunks), reports)
            except Exception:
                ...
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
    """Chat about the latest analyzed report with agent routing.

    Input: { thread_id, messages }
    Routes questions to specialized agents and streams responses.
    """
    settings = get_settings()
    mem = get_memory()
    thread_id = body.thread_id or request.headers.get("x-thread-id") or str(uuid.uuid4())

    # Get the full message history from the request
    messages = body.messages or []

    # Extract the latest user question
    chat_q = None
    if messages and messages[-1].role == "user":
        chat_q = messages[-1].content

    # Pull latest analysis
    report_text, reports = mem.get_analysis(thread_id)

    # Classify question and route to agent
    from backend.graph.nodes.agent_router import classify_question

    agent_type = classify_question(chat_q) if chat_q else "general"

    # Agent-specific prompts
    AGENT_PROMPTS = {
        "security": """You are a Security Expert for code review. Focus on:
- Security vulnerabilities and exploits
- Authentication and authorization issues
- Input validation and injection attacks
- Cryptography and data protection
Answer concisely with line numbers when relevant.""",
        "quality": """You are a Code Quality Expert. Focus on:
- Code complexity and maintainability
- Best practices and design patterns
- Code smells and refactoring opportunities
- Performance and optimization
Answer concisely with line numbers when relevant.""",
        "bug": """You are a Bug Detection Expert. Focus on:
- Potential runtime errors and edge cases
- Logic errors and incorrect implementations
- Exception handling and error recovery
- Type safety and null pointer issues
Answer concisely with line numbers when relevant.""",
        "general": """You are a Code Review Assistant. Provide helpful explanations about the code and analysis.
Answer concisely and reference specific findings when relevant.""",
    }

    # Build agent-specific prompt
    agent_prompt = AGENT_PROMPTS.get(agent_type, AGENT_PROMPTS["general"])

    # Agent emoji badges
    AGENT_BADGES = {
        "security": "🔐 Security Agent",
        "quality": "📊 Quality Agent",
        "bug": "🐛 Bug Agent",
        "general": "💬 Assistant",
    }

    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        if settings.OPENAI_API_KEY:
            llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2)

            # Construct the prompt with agent-specific system message
            prompt_messages = [SystemMessage(content=agent_prompt)]

            # Add the analysis context if available
            if report_text:
                # Extract relevant section based on agent type
                context_message = f"Here is the code analysis report:\n\n{report_text}\n\n"

                if agent_type == "security" and reports:
                    sec = reports.get("security_report", {})
                    if sec:
                        context_message += f"\nSecurity Details: {sec}\n"
                elif agent_type == "quality" and reports:
                    qual = reports.get("quality_report", {})
                    if qual:
                        context_message += f"\nQuality Details: {qual}\n"
                elif agent_type == "bug" and reports:
                    bug = reports.get("bug_report", {})
                    if bug:
                        context_message += f"\nBug Details: {bug}\n"

                context_message += (
                    "\nUse this context to answer the user's question. Be concise and specific."
                )
                prompt_messages.append(SystemMessage(content=context_message))

            # Add conversation history
            for m in messages:
                if m.role == "user":
                    prompt_messages.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    prompt_messages.append(AIMessage(content=m.content))

            # If no messages, we can't really chat
            if len(prompt_messages) <= 1:
                return StreamingResponse(iter(["Please ask a question."]), media_type="text/plain")

            # Stream the response with agent badge
            async def stream_response() -> AsyncGenerator[str, None]:
                # Emit agent badge first
                badge = AGENT_BADGES.get(agent_type, AGENT_BADGES["general"])
                yield f"**{badge}**\n\n"

                async for chunk in llm.astream(prompt_messages):
                    if chunk.content:
                        yield chunk.content

            return StreamingResponse(stream_response(), media_type="text/plain")

    except Exception as e:
        print(f"Error in chat: {e}")

    # Fallback if LLM fails
    sec = (reports or {}).get("security_report") or {}
    qual = (reports or {}).get("quality_report") or {}
    bug = (reports or {}).get("bug_report") or {}

    badge = AGENT_BADGES.get(agent_type, AGENT_BADGES["general"])
    parts: list[str] = [f"**{badge}**\n\n"]

    if chat_q:
        parts.append(f"Question: {chat_q}\n\n")

    # Agent-specific fallback responses
    if agent_type == "security":
        vulns = (sec.get("vulnerabilities") or [])[:3]
        if vulns:
            parts.append("Security findings:\n")
            for v in vulns:
                parts.append(f"- Line {v.get('line')}: {v.get('type')} [{v.get('severity')}]\n")
        else:
            parts.append("No security vulnerabilities detected.\n")
    elif agent_type == "quality":
        m = qual.get("metrics") or {}
        if m:
            parts.append(
                f"Quality metrics: worst={float(m.get('worst', 0.0)):.1f}, avg={float(m.get('avg', 0.0)):.2f}\n"
            )
        issues = (qual.get("issues") or [])[:3]
        if issues:
            parts.append("\nQuality issues:\n")
            for issue in issues:
                parts.append(f"- Line {issue.get('line')}: {issue.get('suggestion')}\n")
        else:
            parts.append("No quality issues detected.\n")
    elif agent_type == "bug":
        bugs = (bug.get("bugs") or [])[:3]
        if bugs:
            parts.append("Potential bugs:\n")
            for b in bugs:
                parts.append(
                    f"- Line {b.get('line')}: {b.get('type')} (confidence: {b.get('confidence')})\n"
                )
        else:
            parts.append("No bugs detected.\n")
    else:
        parts.append("Please ask a more specific question about security, quality, or bugs.\n")

    answer_text = "".join(parts)

    # Stream the response
    async def stream_text() -> AsyncGenerator[str, None]:
        yield answer_text

    return StreamingResponse(stream_text(), media_type="text/plain")


@router.get("/explain/history")
async def get_history(request: Request) -> dict[str, Any]:
    """Return lightweight conversation memory for a thread.

    Accepts `thread_id` via header `x-thread-id` or query parameter.
    Returns latest messages and a boolean indicating if we have a last report hash.
    """
    thread_id = request.headers.get("x-thread-id") or request.query_params.get("thread_id") or ""
    mem = get_memory()
    if not thread_id:
        return {"thread_id": "", "history": [], "has_report": False}
    history = mem.get_history(thread_id, limit=20)
    last_hash = mem.get_last_report_hash(thread_id)
    return {"thread_id": thread_id, "history": history, "has_report": bool(last_hash)}
