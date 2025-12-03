from __future__ import annotations

"""LangChain tool wrappers for security and dead-code analysis.

These wrap our existing safe subprocess helpers and optional libraries in
simple callable functions, then expose LangChain Tool objects for agent use.
The plain functions remain callable directly for internal orchestration.
"""

import os
import tempfile
from contextlib import suppress
from typing import Any

from langchain_core.tools import tool  # type: ignore

from backend.tools.security_tooling import scan_bandit as _scan_bandit
from backend.tools.security_tooling import scan_semgrep as _scan_semgrep


def bandit_scan(code: str, language: str = "python") -> dict[str, Any]:
    """Run Bandit on Python code and return structured findings.

    Returns a dict: { available: bool, findings: [...], error?: str }
    """
    return _scan_bandit(code, language)


def semgrep_scan(code: str, language: str | None = None) -> dict[str, Any]:
    """Run Semgrep with auto config and return structured findings.

    Returns a dict: { available: bool, findings: [...], error?: str }
    """
    return _scan_semgrep(code, language)


def vulture_deadcode(code: str) -> dict[str, Any]:
    """Detect dead code using Vulture if available.

    Returns: { available: bool, dead_functions: [...], dead_variables: [...], error?: str }
    """
    try:
        import vulture  # type: ignore
    except Exception as e:  # pragma: no cover - optional dep
        return {
            "available": False,
            "dead_functions": [],
            "dead_variables": [],
            "error": f"vulture not installed: {e}",
        }

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code or "\n")
            temp_path = f.name

        v = vulture.Vulture(verbose=False)  # type: ignore
        v.scavenge([temp_path])
        dead_funcs = [
            getattr(i, "name", "<unknown>")
            for i in getattr(v, "get_unused_functions", lambda: [])()
        ]
        dead_vars = [
            getattr(i, "name", "<unknown>")
            for i in getattr(v, "get_unused_variables", lambda: [])()
        ]
        return {"available": True, "dead_functions": dead_funcs, "dead_variables": dead_vars}
    except Exception as e:  # pragma: no cover - environment dependent
        return {
            "available": True,
            "dead_functions": [],
            "dead_variables": [],
            "error": str(e),
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            with suppress(Exception):
                os.remove(temp_path)


# Export LangChain tools while keeping the original functions callable
bandit_scan_tool = tool("bandit_scan")(bandit_scan)

semgrep_scan_tool = tool("semgrep_scan")(semgrep_scan)

vulture_deadcode_tool = tool("vulture_deadcode")(vulture_deadcode)
