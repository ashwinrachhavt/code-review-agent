from __future__ import annotations

"""Synthesis node: generate the final human-friendly review.

Uses an OpenAI model when available; otherwise falls back to deterministic
markdown rendering of the collected expert reports.
"""

import json
from typing import Any, Dict, List

from app.core.config import get_settings
from ..memory.semantic_cache import get_semantic_cache, build_query_string

try:
    from langchain_openai import ChatOpenAI  # type: ignore
    from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore
    SystemMessage = None  # type: ignore
    HumanMessage = None  # type: ignore

from prompts.loader import get_prompt
SYNTHESIS_SYSTEM_PROMPT = (
    get_prompt("synthesis_system")
    or "You are an editorial synthesizer. Merge multiple expert reports into a concise, actionable review."
)


def _messages_from_state(state: Dict[str, Any]) -> List[Any]:
    sections = {
        k: state.get(k)
        for k in ("security_report", "quality_report", "bug_report")
        if state.get(k) is not None
    }
    mode = state.get("mode", "orchestrator")
    agents = state.get("agents", ["quality", "bug", "security"]) or []
    section_names: List[str] = []
    if mode == "specialists":
        for a in agents:
            if a == "quality":
                section_names.append("Quality")
            if a == "bug":
                section_names.append("Bugs")
            if a == "security":
                section_names.append("Security")
    else:
        section_names = ["Security", "Quality", "Bugs"]
    guidance = (
        "Create a structured code review with sections for "
        + ", ".join(section_names)
        + ". Use bullets with line numbers when present. Be concise and practical."
    )
    history = state.get("history") or []
    return [
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),  # type: ignore[arg-type]
        HumanMessage(
            content=(
                guidance
                + "\n\nCode (truncated if large):\n\n" + (state.get("code", "") or "")[:3000]
                + "\n\nReports (JSON):\n\n" + json.dumps(sections, indent=2)
                + ("\n\nConversation History (latest first):\n\n" + json.dumps(history[-10:], indent=2) if history else "")
            )
        ),  # type: ignore[arg-type]
    ]


def _fallback_markdown(state: Dict[str, Any]) -> str:
    """Render a deterministic markdown when LLM is not configured."""
    parts: List[str] = ["# Code Review\n"]
    # Quality
    q = state.get("quality_report") or {}
    parts.append("## Quality\n")
    metrics = q.get("metrics", {})
    parts.append(f"Blocks analyzed: {metrics.get('count', 0)}\n")
    parts.append(
        f"Worst complexity: {metrics.get('worst', 0)}, Avg: {float(metrics.get('avg', 0.0)):.2f}\n"
    )
    for issue in (q.get("issues", []) or [])[:10]:
        parts.append(
            f"- Line {issue.get('line')}: {issue.get('metric')}={issue.get('score')} → {issue.get('suggestion')}\n"
        )
    parts.append("\n")

    # Bugs
    b = state.get("bug_report") or {}
    parts.append("## Bugs\n")
    for bug in (b.get("bugs", []) or [])[:10]:
        parts.append(f"- Line {bug.get('line')}: {bug.get('type')} (conf {bug.get('confidence')})\n")
    parts.append("\n")

    # Security
    s = state.get("security_report") or {}
    parts.append("## Security\n")
    for vul in (s.get("vulnerabilities", []) or [])[:10]:
        parts.append(f"- Line {vul.get('line')}: {vul.get('type')} [{vul.get('severity')}]\n")
    parts.append("\n")
    return "".join(parts)


def synthesis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a final review using LLM when available, else fallback markdown.

    Returns
    -------
    Dict[str, Any]
        Updated state with `final_report` string.
    """

    settings = get_settings()
    final_text: str | None = None

    # Semantic cache lookup (based on code + current reports)
    try:
        sections = {
            k: state.get(k)
            for k in ("security_report", "quality_report", "bug_report")
            if state.get(k) is not None
        }
        lang = state.get("language") or "unknown"
        query = build_query_string(
            "synthesis", f"lang={lang}", (state.get("code", "") or "")[:2000], json.dumps(sections, sort_keys=True)[:1000]
        )
        cache = get_semantic_cache(settings)
        hit = cache.get(query, namespace="synthesis", min_score=0.93)
        if hit and isinstance(hit.get("value"), dict):
            cached = hit["value"]
            text = cached.get("text") if isinstance(cached, dict) else None
            if isinstance(text, str) and text.strip():
                state["final_report"] = text
                logs = state.get("tool_logs") or []
                logs.append({
                    "id": "semantic-cache",
                    "agent": "synthesis",
                    "message": "Semantic cache hit for synthesis.",
                    "status": "hit",
                })
                state["tool_logs"] = logs
                state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 30.0)
                return state
    except Exception:
        # Cache is best-effort; ignore failures
        pass

    if settings.OPENAI_API_KEY and ChatOpenAI is not None and SystemMessage is not None:
        try:
            model_name = settings.OPENAI_MODEL
            llm = ChatOpenAI(model=model_name, temperature=0.2)
            messages = _messages_from_state(state)
            result = llm.invoke(messages)
            final_text = getattr(result, "content", None) or None
        except Exception:  # pragma: no cover
            final_text = None

    if not final_text:
        final_text = _fallback_markdown(state)

    state["final_report"] = final_text
    # Store to semantic cache
    try:
        cache = get_semantic_cache(settings)
        cache.set(query, {"text": final_text, "model": settings.OPENAI_MODEL}, namespace="synthesis")
    except Exception:
        pass
    logs = state.get("tool_logs") or []
    logs.append({
        "id": "synthesis",
        "agent": "orchestrator",
        "message": "Synthesis: report generated.",
        "status": "completed",
    })
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 30.0)
    return state
