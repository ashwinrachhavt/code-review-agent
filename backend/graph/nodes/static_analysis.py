from __future__ import annotations

"""Static analysis node: code quality metrics and bug heuristics.

Combines radon complexity metrics with simple regex-based bug pattern checks.

Optional dependency: ``radon`` for cyclomatic complexity. When not installed,
complexity metrics are empty but regex-based bug heuristics still run.
"""

import re
import statistics
from typing import Any

COMMON_BUG_PATTERNS = [
    (re.compile(r"except\s+Exception\s*:\s*pass"), "swallowed_exception"),
    (re.compile(r"def\s+\w+\(.*=\s*\[\]|\{\}\)"), "mutable_default_arg"),
    (re.compile(r"if\s+\w+\s+is\s+\d+"), "is_vs_equals"),
    (re.compile(r"range\(len\((\w+)\)\)"), "index_iteration_over_list"),
]


def _complexity_summary(code: str) -> dict[str, Any]:
    try:
        from radon.complexity import cc_visit  # type: ignore
    except Exception:
        # Radon not installed; return empty metrics
        return {"avg": 0.0, "worst": 0.0, "offenders": [], "count": 0}
    try:
        blocks = cc_visit(code or "")
    except Exception:
        # If parsing fails (non-Python text or syntax error), return empty metrics
        blocks = []
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


def static_analysis_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run code quality metrics and simple bug heuristics.

    Parameters
    ----------
    state: Dict[str, Any]
        Shared graph state.

    Returns
    -------
    Dict[str, Any]
        Updated state with `quality_report` and `bug_report`.
    """

    code = state.get("code", "") or ""

    # Quality metrics
    metrics = _complexity_summary(code)
    issues: list[dict[str, Any]] = []
    if metrics["worst"] >= 10:
        for off in metrics["offenders"]:
            issues.append(
                {
                    "line": off.get("lineno"),
                    "metric": "cyclomatic_complexity",
                    "score": off.get("complexity"),
                    "suggestion": "Split long function into smaller units and reduce branching.",
                }
            )
    if len(code) > 2000:
        issues.append(
            {
                "line": None,
                "metric": "file_length",
                "score": len(code),
                "suggestion": "Large file detected; consider extracting modules for cohesion.",
            }
        )
    state["quality_report"] = {"metrics": metrics, "issues": issues}

    # Bug heuristics
    suspects: list[dict[str, Any]] = []
    for i, line in enumerate(code.splitlines(), start=1):
        for pattern, kind in COMMON_BUG_PATTERNS:
            if pattern.search(line):
                suspects.append(
                    {
                        "line": i,
                        "type": kind,
                        "confidence": 0.6,
                        "snippet": line.strip()[:160],
                        "test_case": "Add a unit test hitting this branch and assert expected behavior.",
                    }
                )
    state["bug_report"] = {"bugs": suspects}

    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "static",
            "agent": "quality+bug",
            "message": "Static analysis: quality metrics and bug heuristics complete.",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 35.0)
    return state
