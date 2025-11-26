"""Agent router for chat mode - classifies questions and routes to specialized agents."""

from typing import Any

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
except Exception:
    ChatOpenAI = None
    SystemMessage = None
    HumanMessage = None

from backend.app.core.config import get_settings

ROUTER_SYSTEM_PROMPT = """You are an intent classifier for code review questions.
Classify the user's question into one of these categories:
- security: Questions about vulnerabilities, security issues, threats, exploits
- quality: Questions about code quality, metrics, best practices, maintainability
- bug: Questions about potential bugs, edge cases, error handling
- general: General questions, explanations, or questions spanning multiple categories

Respond with ONLY the category name (security, quality, bug, or general)."""


def classify_question(question: str) -> str:
    """Classify a user question into an agent category.

    Args:
        question: The user's question

    Returns:
        One of: 'security', 'quality', 'bug', 'general'
    """
    settings = get_settings()

    # Simple keyword-based fallback
    q_lower = question.lower()
    if any(
        word in q_lower
        for word in ["security", "vulnerability", "exploit", "attack", "injection", "xss", "sql"]
    ):
        return "security"
    if any(
        word in q_lower
        for word in ["quality", "complexity", "maintainability", "best practice", "clean code"]
    ):
        return "quality"
    if any(word in q_lower for word in ["bug", "error", "crash", "exception", "edge case", "fail"]):
        return "bug"

    # Try LLM classification if available
    if settings.OPENAI_API_KEY and ChatOpenAI is not None:
        try:
            llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.0)
            messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT), HumanMessage(content=question)]
            result = llm.invoke(messages)
            category = str(getattr(result, "content", "")).strip().lower()
            if category in ["security", "quality", "bug", "general"]:
                return category
        except Exception:
            pass

    return "general"


def agent_router_node(state: dict[str, Any]) -> dict[str, Any]:
    """Route chat questions to appropriate specialized agent.

    This node classifies the user's question and sets the agent context
    for downstream processing.
    """
    chat_query = state.get("chat_query", "").strip()

    if not chat_query:
        state["agent_type"] = "general"
        return state

    # Classify the question
    agent_type = classify_question(chat_query)
    state["agent_type"] = agent_type

    # Add to logs
    logs = state.get("tool_logs", [])
    logs.append(
        {
            "id": "agent_router",
            "agent": "router",
            "message": f"Routed to {agent_type} agent",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs

    return state
