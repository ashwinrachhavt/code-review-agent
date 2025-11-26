from __future__ import annotations

"""LLM expert nodes (placeholder).

In Phase 4, this module will wire LangGraph ToolNode with Bandit/Semgrep/Radon.
For now, it simply annotates the state to indicate where LLM experts would run.
"""

import json
from typing import Any

from app.core.config import get_settings
from langgraph.prebuilt import ToolNode  # type: ignore

try:
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )  # type: ignore
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore
    SystemMessage = HumanMessage = AIMessage = ToolMessage = BaseMessage = object  # type: ignore

from contextlib import suppress

from prompts.loader import get_prompt

from ..memory.semantic_cache import build_query_string, get_semantic_cache
from ..tools import get_default_tools


def _initial_messages(state: dict[str, Any]) -> list[Any]:
    code = (state.get("code", "") or "")[:4000]
    lang = state.get("language") or "unknown"
    system = get_prompt("tool_instructions") or (
        "You are tool-using code analysis experts. Use tools judiciously and return JSON."
    )
    return [
        SystemMessage(content=system),  # type: ignore[arg-type]
        HumanMessage(  # type: ignore[arg-type]
            content=(f"Language: {lang}\n\nCode snippet (truncated):\n\n" + code)
        ),
    ]


def experts_model_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    # Semantic cache: if we've already computed experts reports for this code, reuse.
    try:
        lang = state.get("language") or "unknown"
        code = (state.get("code", "") or "")[:3000]
        query = build_query_string("experts", f"lang={lang}", code)
        cache = get_semantic_cache(settings)
        hit = cache.get(query, namespace="experts", min_score=0.93)
        if hit and isinstance(hit.get("value"), dict):
            data = hit["value"]
            # Merge cached reports into state
            if isinstance(data.get("security_report"), dict):
                sec = state.get("security_report") or {"vulnerabilities": []}
                cached = data["security_report"].get("vulnerabilities", [])
                sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + list(cached or [])
                state["security_report"] = sec
            if isinstance(data.get("quality_report"), dict):
                # Replace or merge metrics conservatively
                q = state.get("quality_report") or {}
                qm = q.get("metrics") or {}
                cm = data["quality_report"].get("metrics") or {}
                qm["avg"] = float(cm.get("avg", qm.get("avg", 0.0)))
                qm["worst"] = max(float(cm.get("worst", 0.0)), float(qm.get("worst", 0.0) or 0.0))
                qm["count"] = int(cm.get("count", qm.get("count", 0)))
                q["metrics"] = qm
                q["issues"] = q.get("issues", [])
                state["quality_report"] = q
            logs = state.get("tool_logs") or []
            logs.append(
                {
                    "id": "semantic-cache",
                    "agent": "experts",
                    "message": "Semantic cache hit for experts.",
                    "status": "hit",
                }
            )
            state["tool_logs"] = logs
            state["experts_next"] = "finalize"
            return state
    except Exception:
        pass
    tools = get_default_tools()
    messages: list[BaseMessage] = state.get("agent_messages") or []  # type: ignore[assignment]
    if not messages:
        messages = _initial_messages(state)  # type: ignore[assignment]

    # Sanitize persisted message history: if there are ToolMessages but no
    # preceding assistant message with tool_calls, reset to a clean start.
    try:
        has_tool_msg = any(isinstance(m, ToolMessage) for m in messages)  # type: ignore[arg-type]
        if has_tool_msg:
            valid = True
            for idx, m in enumerate(messages):  # type: ignore[assignment]
                if isinstance(m, ToolMessage):  # type: ignore[arg-type]
                    # Find the last assistant before this tool message
                    prev_ai = None
                    for j in range(idx - 1, -1, -1):
                        if isinstance(messages[j], AIMessage):  # type: ignore[arg-type]
                            prev_ai = messages[j]
                            break
                    if prev_ai is None or not getattr(prev_ai, "tool_calls", None):
                        valid = False
                        break
            if not valid:
                messages = _initial_messages(state)  # type: ignore[assignment]
    except Exception:
        # Be conservative on any schema mismatch
        messages = _initial_messages(state)  # type: ignore[assignment]

    # If no model or no API key, skip tool-calling flow
    if ChatOpenAI is None or not settings.OPENAI_API_KEY:
        # No model; skip tool-calling flow
        state["agent_messages"] = messages
        state["experts_iterations"] = int(state.get("experts_iterations", 0))
        state["experts_next"] = "finalize"
        return state

    try:
        model = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.0).bind_tools(tools)
        ai = model.invoke(messages)  # type: ignore[arg-type]
    except Exception:
        # If model initialization/invocation fails (e.g., missing API key), skip tools path
        state["agent_messages"] = messages
        state["experts_iterations"] = int(state.get("experts_iterations", 0))
        state["experts_next"] = "finalize"
        return state
    messages = [*messages, ai]  # type: ignore[operator]
    state["agent_messages"] = messages

    # Route decision: if there are tool calls and iteration budget remains, go to tools
    iter_count = int(state.get("experts_iterations", 0))
    has_tools = getattr(ai, "tool_calls", None)
    if has_tools and iter_count < 2:
        state["experts_next"] = "tools"
    else:
        state["experts_next"] = "finalize"
    return state


def experts_tools_node(state: dict[str, Any]) -> dict[str, Any]:
    tools = get_default_tools()
    tool_node = ToolNode(tools)
    messages: list[BaseMessage] = state.get("agent_messages") or []  # type: ignore[assignment]
    res = tool_node.invoke({"messages": messages})
    tool_msgs = res.get("messages", [])  # type: ignore[assignment]
    # Ensure we preserve the prior conversation and append tool messages
    if isinstance(tool_msgs, list):
        state["agent_messages"] = [*messages, *tool_msgs]
    else:
        state["agent_messages"] = messages
    state["experts_iterations"] = int(state.get("experts_iterations", 0)) + 1
    return state


def _merge_tool_outputs_into_state(state: dict[str, Any]) -> None:
    # Parse ToolMessage outputs (JSON strings) and merge into reports
    messages: list[Any] = state.get("agent_messages") or []
    sec = state.get("security_report") or {"vulnerabilities": []}
    qual = state.get("quality_report") or {"metrics": {}, "issues": []}

    for msg in messages:
        if isinstance(msg, ToolMessage):  # type: ignore[arg-type]
            name = getattr(msg, "tool_name", "")
            content = getattr(msg, "content", "") or ""
            try:
                data = json.loads(content)
            except Exception:
                continue

            if name == "bandit_scan" or name == "semgrep_scan":
                findings = data.get("findings", []) or []
                sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + findings
            elif name == "radon_complexity":
                # Merge metrics; do not duplicate offenders list if static node already added
                metrics = data.get("metrics", {})
                qm = qual.get("metrics") or {}
                # Prefer max for worst, mean for avg when both exist
                qm["avg"] = float(metrics.get("avg", qm.get("avg", 0.0)))
                qm["worst"] = max(
                    float(metrics.get("worst", 0.0)), float(qm.get("worst", 0.0) or 0.0)
                )
                qm["count"] = int(metrics.get("count", qm.get("count", 0)))
                qual["metrics"] = qm

    state["security_report"] = sec
    state["quality_report"] = qual


def experts_finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    # Merge tool outputs and log
    with suppress(Exception):
        _merge_tool_outputs_into_state(state)

    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "llm-experts",
            "agent": "experts",
            "message": "LLM experts: tools executed and merged.",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 10.0)
    # Store merged reports to semantic cache
    with suppress(Exception):
        settings = get_settings()
        cache = get_semantic_cache(settings)
        lang = state.get("language") or "unknown"
        code = (state.get("code", "") or "")[:3000]
        query = build_query_string("experts", f"lang={lang}", code)
        value = {
            "security_report": state.get("security_report"),
            "quality_report": state.get("quality_report"),
            "bug_report": state.get("bug_report"),
        }
        cache.set(query, value, namespace="experts")
    return state
