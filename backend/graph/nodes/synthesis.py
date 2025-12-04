from __future__ import annotations

"""Synthesis node: generate the final human-friendly review.

Uses an OpenAI model when available; otherwise falls back to deterministic
markdown rendering of the collected expert reports.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
from langchain_openai import ChatOpenAI  # type: ignore

from backend.app.core.config import get_settings
from backend.prompts.loader import get_prompt

SYNTHESIS_SYSTEM_PROMPT = (
    get_prompt("synthesis_system")
    or "You are an editorial synthesizer. Merge multiple expert reports into a concise, actionable review."
)
CHAT_SYSTEM_PROMPT = (
    "You are a concise code review assistant. Answer the user's question about the existing review "
    "without repeating the whole review. Prefer short bullets with line numbers if relevant. "
    "Avoid repeating content you've already sent earlier in this thread; add new value or be brief."
)


def _messages_from_state(state: dict[str, Any]) -> list[Any]:
    sections = {
        k: state.get(k)
        for k in ("security_report", "quality_report", "bug_report")
        if state.get(k) is not None
    }
    mode = state.get("mode", "orchestrator")
    agents = state.get("agents", ["quality", "bug", "security"]) or []
    if mode == "chat":
        chat_q = (state.get("chat_query") or "").strip()
        history = state.get("history") or []
        code_snippet = (state.get("code", "") or "")[:2000]
        return [
            SystemMessage(content=CHAT_SYSTEM_PROMPT),  # type: ignore[arg-type]
            HumanMessage(  # type: ignore[arg-type]
                content=(
                    "Answer this question about the existing review: "
                    + chat_q
                    + "\n\nDo not repeat the full review. Use short bullets if useful."
                    + ("\n\nCode (for reference):\n\n" + code_snippet if code_snippet else "")
                    + "\n\nReports (JSON):\n\n"
                    + json.dumps(sections, indent=2)
                    + ("\n\nHistory:\n\n" + json.dumps(history[-10:], indent=2) if history else "")
                )
            ),
        ]
    else:
        section_names: list[str] = []
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
                    + "\n\nCode (truncated if large):\n\n"
                    + (state.get("code", "") or "")[:3000]
                    + "\n\nReports (JSON):\n\n"
                    + json.dumps(sections, indent=2)
                    + (
                        "\n\nConversation History (latest first):\n\n"
                        + json.dumps(history[-10:], indent=2)
                        if history
                        else ""
                    )
                )
            ),  # type: ignore[arg-type]
        ]


def _fallback_markdown(state: dict[str, Any]) -> str:
    """Render a deterministic markdown when LLM is not configured."""
    parts: list[str] = ["# Code Review\n"]
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
        parts.append(
            f"- Line {bug.get('line')}: {bug.get('type')} (conf {bug.get('confidence')})\n"
        )
    parts.append("\n")

    # Security
    s = state.get("security_report") or {}
    parts.append("## Security\n")
    for vul in (s.get("vulnerabilities", []) or [])[:10]:
        parts.append(f"- Line {vul.get('line')}: {vul.get('type')} [{vul.get('severity')}]\n")
    parts.append("\n")
    return "".join(parts)


def _chat_fallback(state: dict[str, Any]) -> str:
    """Deterministic fallback for chat mode when LLM is unavailable.

    Produces a short, non-repetitive answer using available reports without
    rendering a full review header.
    """
    q = (state.get("chat_query") or "").strip()
    sec = state.get("security_report") or {}
    qual = state.get("quality_report") or {}
    bug = state.get("bug_report") or {}

    parts: list[str] = []
    if q:
        parts.append(f"Question: {q}\n")
    # Security
    vulns = (sec.get("vulnerabilities") or [])[:3]
    if vulns:
        parts.append("- Security: Top findings:\n")
        for v in vulns:
            parts.append(f"  • Line {v.get('line')}: {v.get('type')} [{v.get('severity')}]\n")
    # Quality
    metrics = qual.get("metrics") or {}
    if metrics:
        parts.append(
            f"- Quality: worst={float(metrics.get('worst', 0.0)):.1f}, avg={float(metrics.get('avg', 0.0)):.2f}\n"
        )
    issues = (qual.get("issues") or [])[:2]
    for it in issues:
        parts.append(
            f"  • Line {it.get('line')}: {it.get('metric')}={it.get('score')} → {it.get('suggestion')}\n"
        )
    # Bugs
    suspects = (bug.get("bugs") or [])[:2]
    if suspects:
        parts.append("- Bugs: potential issues:\n")
        for b in suspects:
            parts.append(
                f"  • Line {b.get('line')}: {b.get('type')} (conf {b.get('confidence')})\n"
            )

    if not parts:
        parts.append(
            "- No additional insights; try @security or paste a code block for deeper analysis.\n"
        )
    return "".join(parts)


def synthesis_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a final review using LLM when available, else fallback markdown.

    Returns
    -------
    Dict[str, Any]
        Updated state with `final_report` string.
    """

    settings = get_settings()
    final_text: str | None = None

    # Semantic cache lookup (based on code + current reports)
    # No custom semantic cache; rely on LangChain LLM cache for model outputs.

    if settings.OPENAI_API_KEY:
        try:
            model_name = state.get("llm_model") or settings.OPENAI_MODEL
            llm = ChatOpenAI(model=str(model_name), temperature=0.2)
            messages = _messages_from_state(state)
            result = llm.invoke(messages)
            final_text = getattr(result, "content", None) or None
        except Exception:  # pragma: no cover
            final_text = None

    if not final_text:
        if (state.get("mode") or "") == "chat":
            final_text = _chat_fallback(state)
        else:
            final_text = _fallback_markdown(state)

    state["final_report"] = final_text
    # No custom semantic cache persistence.
    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "synthesis",
            "agent": "orchestrator",
            "message": "Synthesis: report generated.",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 30.0)
    return state
