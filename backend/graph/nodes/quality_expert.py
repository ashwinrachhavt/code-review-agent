from __future__ import annotations

import statistics
from typing import Any

try:
    from radon.complexity import cc_visit  # type: ignore
except Exception:  # pragma: no cover

    def cc_visit(_code: str):
        # Minimal fallback if radon is not installed
        return []


def _complexity_summary(code: str) -> dict[str, Any]:
    blocks = cc_visit(code or "")
    scores = [b.complexity for b in blocks]
    avg = statistics.fmean(scores) if scores else 0.0
    worst = max(scores) if scores else 0.0
    offenders = [
        {
            "name": b.name,
            "lineno": getattr(b, "lineno", None),
            "complexity": b.complexity,
        }
        for b in blocks
        if b.complexity >= 10
    ]
    return {"avg": avg, "worst": worst, "offenders": offenders, "count": len(blocks)}


def quality_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze code quality using simple static metrics (MVP).

    Returns a structured report that the synthesis step can render.
    """
    code = state.get("code", "")
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

    # Simple smells (MVP heuristics)
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
    state["tool_logs"].append(
        {
            "id": "quality",
            "agent": "quality",
            "message": "Quality Expert: metrics analyzed.",
            "status": "completed",
        }
    )
    state["progress"] = min(100.0, state.get("progress", 0.0) + 20.0)
    return state
