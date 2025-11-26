from __future__ import annotations

"""LLM expert nodes (placeholder).

In Phase 4, this module will wire LangGraph ToolNode with Bandit/Semgrep/Radon.
For now, it simply annotates the state to indicate where LLM experts would run.
"""

import json
from typing import Any

from backend.app.core.config import get_settings
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

from backend.prompts.loader import get_prompt

from backend.graph.tools import get_default_tools


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
    # No custom semantic cache; rely on LangChain LLM cache and graph checkpointing.
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

    # Dedupe reports to avoid repeated recommendations across sources
    try:
        # Security: dedupe by (type, line) primarily; fall back to snippet text
        sec = state.get("security_report") or {"vulnerabilities": []}
        vulns = sec.get("vulnerabilities") or []
        seen_keys: set[tuple] = set()
        deduped: list[dict[str, Any]] = []
        for v in vulns:
            if not isinstance(v, dict):
                continue
            t = str(v.get("type", "")).lower()
            ln = int(v.get("line") or -1)
            sn = str(v.get("snippet", "")).strip().lower()[:100]
            key = (t, ln, sn)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(v)
        sec["vulnerabilities"] = deduped
        state["security_report"] = sec
    except Exception:
        ...

    try:
        # Quality: dedupe issues by (metric, line); keep highest score
        qual = state.get("quality_report") or {"metrics": {}, "issues": []}
        issues = qual.get("issues") or []
        best: dict[tuple, dict[str, Any]] = {}
        for it in issues:
            if not isinstance(it, dict):
                continue
            key = (str(it.get("metric", "")).lower(), int(it.get("line") or -1))
            cur = best.get(key)
            if cur is None or float(it.get("score", 0.0)) > float(cur.get("score", 0.0)):
                best[key] = it
        qual["issues"] = list(best.values())
        state["quality_report"] = qual
    except Exception:
        ...

    try:
        # Bugs: dedupe by (type, line)
        bug = state.get("bug_report") or {"bugs": []}
        bugs = bug.get("bugs") or []
        seen: set[tuple] = set()
        out: list[dict[str, Any]] = []
        for b in bugs:
            if not isinstance(b, dict):
                continue
            key = (str(b.get("type", "")).lower(), int(b.get("line") or -1))
            if key in seen:
                continue
            seen.add(key)
            out.append(b)
        bug["bugs"] = out
        state["bug_report"] = bug
    except Exception:
        ...

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
    # No custom semantic cache persistence here.
    return state
