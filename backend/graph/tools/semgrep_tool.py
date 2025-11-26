from __future__ import annotations

"""Semgrep tool wrapper for LangChain/LangGraph.

Runs Semgrep (if installed) with auto-config and returns JSON findings.
"""

import json

from langchain_core.tools import tool  # type: ignore

from backend.tools.security_tooling import scan_semgrep


@tool("semgrep_scan")
def semgrep_scan_tool(code: str, language: str | None = None) -> str:
    """Run Semgrep with auto-config on provided code.

    Parameters
    ----------
    code: str
        Source code to scan.
    language: Optional[str]
        Language hint to set file suffix.

    Returns
    -------
    str
        JSON string: { available: bool, findings: [...], error?: str }
    """

    result = scan_semgrep(code, language)
    return json.dumps(result)
