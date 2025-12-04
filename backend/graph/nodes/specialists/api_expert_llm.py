from __future__ import annotations

"""API expert LLM node for endpoint analysis.

Detects REST/GraphQL/gRPC endpoints and analyzes validation, error handling,
authentication, and best practices.
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


def api_expert_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze API endpoints with expert LLM.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing code and files

    Returns
    -------
    dict[str, Any]
        Updated state with api_expert_analysis field only
    """
    settings = get_settings()
    code_sample = (state.get("code") or "")[:3000]
    files = state.get("files") or []

    # Build file list summary
    file_list = "\n".join(f"- {f.get('path', 'unknown')}" for f in files[:20])

    # Default empty analysis
    default_analysis = {"endpoints": [], "issues": [], "improvements": []}

    # Check if we have OpenAI configured
    if not settings.OPENAI_API_KEY or ChatOpenAI is None:
        logger.warning("API expert: OpenAI not configured, skipping LLM analysis")
        return {"api_expert_analysis": default_analysis}

    # Load prompt template
    prompt_template = get_prompt("specialists/api") or ""
    if not prompt_template:
        logger.warning("API expert: Prompt template not found")
        return {"api_expert_analysis": default_analysis}

    # Format prompt without interpreting JSON braces in template
    # Use targeted replacement instead of str.format to avoid KeyError
    prompt_text = prompt_template.replace("{file_list}", file_list or "No files provided").replace(
        "{code_sample}", code_sample or "No code provided"
    )

    try:
        # Call LLM (synchronous)
        llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0.2, timeout=30.0)
        messages = [
            SystemMessage(content="You are an API design expert. Always output valid JSON."),
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
        analysis.setdefault("endpoints", [])
        analysis.setdefault("issues", [])
        analysis.setdefault("improvements", [])

        logger.info(
            "API expert: Found %d endpoints, %d issues",
            len(analysis.get("endpoints", [])),
            len(analysis.get("issues", [])),
        )

        return {"api_expert_analysis": analysis}

    except json.JSONDecodeError as e:
        logger.error("API expert: Failed to parse JSON response: %s", e)
        return {"api_expert_analysis": default_analysis}
    except Exception as e:  # pragma: no cover
        logger.error("API expert: LLM call failed: %s", e)
        return {"api_expert_analysis": default_analysis}
