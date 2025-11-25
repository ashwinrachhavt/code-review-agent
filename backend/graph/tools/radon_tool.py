from __future__ import annotations

"""Radon complexity tool wrapper.

Computes cyclomatic complexity summary and returns a JSON report.
"""

import json
import statistics
from typing import Any, Dict

from langchain_core.tools import tool  # type: ignore

try:
    from radon.complexity import cc_visit  # type: ignore
except Exception:  # pragma: no cover
    def cc_visit(_code: str):  # type: ignore
        return []


def _summary(code: str) -> Dict[str, Any]:
    blocks = cc_visit(code or "")
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


@tool("radon_complexity")
def radon_complexity_tool(code: str) -> str:
    """Analyze cyclomatic complexity using Radon.

    Parameters
    ----------
    code: str
        Source code to analyze.

    Returns
    -------
    str
        JSON string: { metrics: {avg,worst,offenders,count} }
    """

    metrics = _summary(code)
    return json.dumps({"metrics": metrics})

