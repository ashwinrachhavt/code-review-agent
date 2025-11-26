from __future__ import annotations

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


def security_node(state: dict[str, Any]) -> dict[str, Any]:
    code = state.get("code", "")
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

    state["security_report"] = {"vulnerabilities": findings}
    state["tool_logs"].append(
        {
            "id": "security",
            "agent": "security",
            "message": "Security Expert: scan complete.",
            "status": "completed",
        }
    )
    state["progress"] = min(100.0, state.get("progress", 0.0) + 20.0)
    return state
