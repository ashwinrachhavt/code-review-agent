from __future__ import annotations

"""Chat reply node.

Generates a concise, unstructured reply grounded in the thread's analysis
(structured reports and optional retrieved context), given a `chat_query`.
Does not repeat or paste the full code review report.
"""

import json
from typing import Any

from backend.app.core.config import get_settings


def _fallback_reply(state: dict[str, Any]) -> str:
    """Non-LLM fallback: short, free-form notes from structured reports only."""
    question = (state.get("chat_query") or "").strip()
    security_report = state.get("security_report") or {}
    quality_report = state.get("quality_report") or {}
    bug_report = state.get("bug_report") or {}

    parts: list[str] = []
    if question:
        parts.append(f"Question: {question}\n")
    vulns = (security_report.get("vulnerabilities") or [])[:3]
    if vulns:
        parts.append("- Security highlights:\n")
        for v in vulns:
            parts.append(
                f"  • Line {v.get('line')}: {v.get('type')} [{v.get('severity')}]\n"
            )
    metrics = (quality_report.get("metrics") or {})
    if metrics:
        parts.append(
            f"- Quality: worst={float(metrics.get('worst', 0.0)):.1f}, avg={float(metrics.get('avg', 0.0)):.2f}\n"
        )
    q_issues = (quality_report.get("issues") or [])[:2]
    for it in q_issues:
        parts.append(
            f"  • Line {it.get('line')}: {it.get('metric')}={it.get('score')} → {it.get('suggestion')}\n"
        )
    bugs = (bug_report.get("bugs") or [])[:2]
    if bugs:
        parts.append("- Bugs: potential issues:\n")
        for b in bugs:
            parts.append(
                f"  • Line {b.get('line')}: {b.get('type')} (conf {b.get('confidence')})\n"
            )

    if not parts:
        parts.append("No stored analysis yet. Run /explain to populate context.\n")
    return "".join(parts)


def chat_reply_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a chat reply based on the existing review and query.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing chat_query and existing reports

    Returns
    -------
    dict[str, Any]
        Updated state with final_report containing the chat response
    """
    settings = get_settings()
    query = (state.get("chat_query") or "").strip()
    if not query:
        return {"chat_response": "Please include a question."}

    # Get existing reports
    security_report = state.get("security_report") or {}
    quality_report = state.get("quality_report") or {}
    bug_report = state.get("bug_report") or {}

    # Get retrieved context docs from RAG (if available)
    chat_context_docs = state.get("chat_context_docs") or []
    history = state.get("history") or []

    # Format retrieved context
    context_section = ""
    if chat_context_docs:
        context_parts = ["## Relevant Code Context\n"]
        for i, doc in enumerate(chat_context_docs[:5], 1):
            path = doc.get("path", "unknown")
            text = doc.get("text", "")[:500]  # Limit to 500 chars per chunk
            score = doc.get("score", 0.0)
            context_parts.append(f"### {i}. {path} (relevance: {score:.2f})\n```\n{text}\n```\n")
        context_section = "\n".join(context_parts)

    # Build prompt (no full report paste; free-form answer grounded in reports)
    prompt_parts = [
        "You are a concise code review assistant.",
        "Answer the user's question using the stored analysis and any retrieved code context.",
        "Do not paste or restate the full code review report. Be specific and brief.",
        "If the question is vague (e.g., 'more'), ask 2-3 precise follow-up questions instead of repeating content.",
        f"User Question: {query}",
        "",
    ]

    if context_section:
        prompt_parts.append(context_section)
        prompt_parts.append("")

    prompt_parts.append("## Stored Reports (JSON)")
    prompt_parts.append("Security:\n" + json.dumps(security_report, indent=2))
    prompt_parts.append("Quality:\n" + json.dumps(quality_report, indent=2))
    prompt_parts.append("Bugs:\n" + json.dumps(bug_report, indent=2))
    if history:
        prompt_parts.append("\nRecent Conversation (JSON):\n" + json.dumps(history[-10:], indent=2))
    prompt_parts.append(
        "\nGuidelines: Answer the question directly, reference files/lines if helpful,"
        " never dump the whole report, and avoid repeating earlier replies."
    )

    prompt = "\n".join(prompt_parts)

    reply: str | None = None
    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.3)
            result = llm.invoke(prompt)
            reply = getattr(result, "content", None) or None
        except Exception:
            reply = None

    if not reply:
        reply = _fallback_reply(state)

    state["chat_response"] = reply
    try:
        state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 5.0)
    except Exception:
        state["progress"] = 100.0
    return state
