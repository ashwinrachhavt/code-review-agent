from __future__ import annotations

"""Bandit tool wrapper for LangChain/LangGraph.

Executes Bandit on Python code when available and returns JSON findings.
"""

import json

from langchain_core.tools import tool  # type: ignore
from tools.security_tooling import scan_bandit


@tool("bandit_scan")
def bandit_scan_tool(code: str, language: str | None = "python") -> str:
    """Run Bandit static analyzer on provided code.

    Parameters
    ----------
    code: str
        Source code to scan.
    language: Optional[str]
        Language hint (only 'python' triggers Bandit).

    Returns
    -------
    str
        JSON string: { available: bool, findings: [...], error?: str }
    """

    result = scan_bandit(code, language)
    return json.dumps(result)
