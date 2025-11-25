from __future__ import annotations

import re
from typing import Any, Dict, List


COMMON_BUG_PATTERNS = [
    (re.compile(r"except\s+Exception\s*:\s*pass"), "swallowed_exception"),
    (re.compile(r"def\s+\w+\(.*=\s*\[\]|\{\}\)"), "mutable_default_arg"),
    (re.compile(r"if\s+\w+\s+is\s+\d+"), "is_vs_equals"),
    (re.compile(r"range\(len\((\w+)\)\)"), "index_iteration_over_list"),
]


def _lines(code: str) -> List[str]:
    return code.splitlines()


def bug_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Naive bug heuristics (MVP). Adds suspected issues with line numbers.
    """
    code = state.get("code", "")
    lines = _lines(code)
    suspects: List[Dict[str, Any]] = []

    for i, line in enumerate(lines, start=1):
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
    state["tool_logs"].append({
        "id": "bug",
        "agent": "bug",
        "message": "Bug Hunter: heuristics completed.",
        "status": "completed",
    })
    state["progress"] = min(100.0, state.get("progress", 0.0) + 20.0)
    return state

