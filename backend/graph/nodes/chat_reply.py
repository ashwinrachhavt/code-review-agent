from __future__ import annotations

"""Chat reply node.

Generates a concise, unstructured text reply given the saved analysis
(`final_report` and structured reports) and a `chat_query` in state.
"""

import json
from typing import Any

from backend.app.core.config import get_settings


def _fallback_reply(final_report: str | None, question: str | None) -> str:
    parts: list[str] = []
    if question:
        parts.append(f"Question: {question}\n\n")
    if final_report:
        parts.append("Summary:\n")
        parts.append("\n\n".join((final_report or "").split("\n\n")[:3]))
    else:
        parts.append("No analysis found for this thread. Run /explain first.")
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
        return {"final_report": "No question provided."}

    # Get existing reports
    security_report = state.get("security_report") or {}
    quality_report = state.get("quality_report") or {}
    bug_report = state.get("bug_report") or {}

    # Get retrieved context docs from RAG (if available)
    chat_context_docs = state.get("chat_context_docs") or []

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

    # Build prompt
    prompt_parts = [
        "You are a code review assistant. Answer the user's question about the code review.",
        "",
        f"**User Question:** {query}",
        "",
    ]

    if context_section:
        prompt_parts.append(context_section)
        prompt_parts.append("")

    prompt_parts.extend(
        [
            "## Review Reports",
            "",
            "**Security:**",
            json.dumps(security_report, indent=2),
            "",
            "**Quality:**",
            json.dumps(quality_report, indent=2),
            "",
            "**Bugs:**",
            json.dumps(bug_report, indent=2),
            "",
            "Provide a concise, specific answer. Reference line numbers and file paths when relevant.",
        ]
    )

    prompt = "\n".join(prompt_parts)

    reply: str | None = None
    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2)
            result = llm.invoke(prompt)
            reply = getattr(result, "content", None) or None
        except Exception:
            reply = None

    if not reply:
        # Use the original query for fallback, not the full prompt
        reply = _fallback_reply(state.get("final_report"), query)

    state["chat_response"] = reply
    try:
        state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 5.0)
    except Exception:
        state["progress"] = 100.0
    return state
