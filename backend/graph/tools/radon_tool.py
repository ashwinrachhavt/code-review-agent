from __future__ import annotations

"""Radon complexity tool wrapper.

Computes cyclomatic complexity summary and returns a JSON report.

Optional dependency: requires the ``radon`` package. If unavailable,
the tool degrades gracefully and returns empty metrics.
"""

import json
import statistics
from typing import Any

from langchain_core.tools import tool  # type: ignore


def _summary(code: str) -> dict[str, Any]:
    try:
        from radon.complexity import cc_visit  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        return {"avg": 0.0, "worst": 0.0, "offenders": [], "count": 0, "error": str(e)}
    try:
        blocks = cc_visit(code or "")
    except Exception as e:  # SyntaxError, ValueError, etc. on non-Python blobs
        return {
            "avg": 0.0,
            "worst": 0.0,
            "offenders": [],
            "count": 0,
            "error": str(e),
        }

    scores = [getattr(b, "complexity", 0.0) for b in blocks]
    avg = statistics.fmean(scores) if scores else 0.0
    worst = max(scores) if scores else 0.0
    offenders = [
        {
            "name": getattr(b, "name", "<unknown>"),
            "lineno": getattr(b, "lineno", None),
            "complexity": getattr(b, "complexity", 0.0),
        }
        for b in blocks
        if getattr(b, "complexity", 0.0) >= 10
    ]
    return {"avg": avg, "worst": worst, "offenders": offenders, "count": len(blocks)}


def radon_complexity_tool(code: str) -> str:
    """Analyze cyclomatic complexity using Radon and return JSON string.

    This plain function is used directly in tests. A LangChain tool wrapper
    is also exported as `radon_complexity_tool_def` for agent tool use.
    """

    metrics = _summary(code)
    return json.dumps({"metrics": metrics})


# LangChain tool definition used by the agent/tooling registry
radon_complexity_tool_def = tool("radon_complexity")(radon_complexity_tool)
