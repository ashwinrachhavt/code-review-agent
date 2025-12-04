from __future__ import annotations

"""Database expert LLM node for SQL and ORM analysis.

Detects SQL injection risks, N+1 queries, missing indexes, and transaction
handling issues.
"""

import json
import logging
from typing import Any

from backend.app.core.config import get_settings
from backend.prompts.loader import get_prompt

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None
    SystemMessage = None
    HumanMessage = None

logger = logging.getLogger(__name__)


def db_expert_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze database queries with expert LLM.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing code

    Returns
    -------
    dict[str, Any]
        Updated state with db_expert_analysis field only
    """
    settings = get_settings()
    code_sample = (state.get("code") or "")[:3000]

    # Default empty analysis
    default_analysis = {"queries": [], "risks": [], "optimizations": []}

    # Check if we have OpenAI configured
    if not settings.OPENAI_API_KEY or ChatOpenAI is None:
        logger.warning("DB expert: OpenAI not configured, skipping LLM analysis")
        return {"db_expert_analysis": default_analysis}

    # Load prompt template
    prompt_template = get_prompt("specialists/database") or ""
    if not prompt_template:
        logger.warning("DB expert: Prompt template not found")
        return {"db_expert_analysis": default_analysis}

    # Format prompt without interpreting JSON braces in template
    prompt_text = prompt_template.replace("{code_sample}", code_sample or "No code provided")

    try:
        # Call LLM (synchronous)
        llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2, timeout=30.0)
        messages = [
            SystemMessage(content="You are a database expert. Always output valid JSON."),
            HumanMessage(content=prompt_text),
        ]

        result = llm.invoke(messages)
        content = getattr(result, "content", "") or ""

        # Parse JSON response
        # Extract JSON from markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        analysis = json.loads(content)

        # Validate structure
        if not isinstance(analysis, dict):
            raise ValueError("Analysis must be a dictionary")

        # Ensure required keys exist
        analysis.setdefault("queries", [])
        analysis.setdefault("risks", [])
        analysis.setdefault("optimizations", [])

        logger.info(
            "DB expert: Found %d queries, %d risks",
            len(analysis.get("queries", [])),
            len(analysis.get("risks", [])),
        )

        return {"db_expert_analysis": analysis}

    except json.JSONDecodeError as e:
        logger.error("DB expert: Failed to parse JSON response: %s", e)
        return {"db_expert_analysis": default_analysis}
    except Exception as e:  # pragma: no cover
        logger.error("DB expert: LLM call failed: %s", e)
        return {"db_expert_analysis": default_analysis}
