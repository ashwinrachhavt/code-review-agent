from __future__ import annotations

"""Security expert LLM node for deep security analysis.

Analyzes security tool findings (Semgrep, Bandit) and provides expert
recommendations with severity classification.
"""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.app.core.config import get_settings
from backend.prompts.loader import get_prompt

logger = logging.getLogger(__name__)


def security_expert_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze security findings with expert LLM.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing security_report from tools_parallel

    Returns
    -------
    dict[str, Any]
        Updated state with security_expert_analysis field only
    """
    settings = get_settings()
    security_report = state.get("security_report") or {}
    code_sample = (state.get("code") or "")[:2000]  # Limit context size

    # Default empty analysis
    default_analysis = {"critical": [], "important": [], "recommendations": []}

    # Check if we have OpenAI configured
    if not settings.OPENAI_API_KEY:
        logger.warning("Security expert: OpenAI not configured, skipping LLM analysis")
        return {"security_expert_analysis": default_analysis}

    # Load prompt template
    prompt_template = get_prompt("specialists/security") or ""
    if not prompt_template:
        logger.warning("Security expert: Prompt template not found")
        return {"security_expert_analysis": default_analysis}

    # Format prompt without interpreting JSON braces in template
    prompt_text = prompt_template.replace(
        "{security_report}", json.dumps(security_report, indent=2)
    ).replace("{code_sample}", code_sample)

    try:
        # Call LLM (synchronous)
        llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2, timeout=30.0)
        messages = [
            SystemMessage(content="You are a security expert. Always output valid JSON."),
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
        analysis.setdefault("critical", [])
        analysis.setdefault("important", [])
        analysis.setdefault("recommendations", [])

        logger.info(
            "Security expert: Found %d critical, %d important issues",
            len(analysis.get("critical", [])),
            len(analysis.get("important", [])),
        )

        return {"security_expert_analysis": analysis}

    except json.JSONDecodeError as e:
        logger.error("Security expert: Failed to parse JSON response: %s", e)
        return {"security_expert_analysis": default_analysis}
    except Exception as e:  # pragma: no cover
        logger.error("Security expert: LLM call failed: %s", e)
        return {"security_expert_analysis": default_analysis}
