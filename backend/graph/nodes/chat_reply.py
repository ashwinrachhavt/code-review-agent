from __future__ import annotations

"""Chat reply node.

Generates a concise, unstructured text reply given the saved analysis
(`final_report` and structured reports) and a `chat_query` in state.
"""

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
    settings = get_settings()

    question = (state.get("chat_query") or "").strip()
    final_report = state.get("final_report") or ""

    reply: str | None = None
    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore

            prompt = (
                "You are a concise code review assistant. Answer the user's question based on the review below.\n\n"
                f"Review:\n{final_report}\n\n"
                f"Question:\n{question}\n\n"
                "Be specific and refer to concrete findings; include line numbers if relevant."
            )
            llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2)
            result = llm.invoke(prompt)
            reply = getattr(result, "content", None) or None
        except Exception:
            reply = None

    if not reply:
        reply = _fallback_reply(final_report, question)

    state["chat_response"] = reply
    try:
        state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 5.0)
    except Exception:
        state["progress"] = 100.0
    return state
