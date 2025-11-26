from __future__ import annotations

"""Security analysis node: regex heuristics.

Bandit/Semgrep integration will be added via ToolNode in Phase 4.
"""

import re
from typing import Any

SECURITY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beval\s*\("), "eval_usage"),
    (re.compile(r"\bexec\s*\("), "exec_usage"),
    (re.compile(r"subprocess\.(Popen|run)\(.*shell\s*=\s*True"), "shell_true"),
    (re.compile(r"\bos\.system\s*\("), "os_system"),
    (re.compile(r"pickle\.load\s*\("), "insecure_pickle_load"),
    (re.compile(r"yaml\.load\s*\("), "yaml_load_without_safeloader"),
    (re.compile(r"requests\.(get|post)\(.*verify\s*=\s*False"), "insecure_tls"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key_leak"),
]


def security_analysis_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run basic regex-based security checks and update the report.

    Parameters
    ----------
    state: Dict[str, Any]
        Shared graph state.

    Returns
    -------
    Dict[str, Any]
        Updated state with `security_report` appended or created.
    """

    code = state.get("code", "") or ""
    findings: list[dict[str, Any]] = []

    for lineno, line in enumerate(code.splitlines(), start=1):
        for pattern, kind in SECURITY_PATTERNS:
            if pattern.search(line):
                findings.append(
                    {
                        "line": lineno,
                        "type": kind,
                        "severity": "high"
                        if kind in {"eval_usage", "exec_usage", "shell_true"}
                        else "medium",
                        "snippet": line.strip()[:160],
                        "exploit": "User-controlled input could lead to code execution or command injection.",
                    }
                )

    sec = state.get("security_report") or {"vulnerabilities": []}
    sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + findings
    state["security_report"] = sec

    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "security-regex",
            "agent": "security",
            "message": f"Security analysis: {len(findings)} regex findings.",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 30.0)
    return state
