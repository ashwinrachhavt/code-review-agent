from __future__ import annotations

"""Parallel tools node using LangChain tool wrappers.

Runs Semgrep, Bandit, Radon (and optionally Vulture) concurrently and maps
results into the shared state expected by the synthesis node.
"""

import asyncio
import json
from typing import Any

from backend.graph.tools.radon_tool import radon_complexity_tool
from backend.graph.tools.security_tools import (
    bandit_scan,
    semgrep_scan,
    vulture_deadcode,
)


async def tools_parallel_node(state: dict[str, Any]) -> dict[str, Any]:
    code = state.get("code", "") or ""

    # Run tools concurrently (sync helpers via threads)
    bandit_task = asyncio.to_thread(bandit_scan, code, "python")
    semgrep_task = asyncio.to_thread(semgrep_scan, code, "python")
    radon_task = asyncio.to_thread(radon_complexity_tool, code)
    vulture_task = asyncio.to_thread(vulture_deadcode, code)

    bandit_res, semgrep_res, radon_res_s, vulture_res = await asyncio.gather(
        bandit_task, semgrep_task, radon_task, vulture_task
    )

    # Parse radon JSON string
    try:
        radon_res = json.loads(radon_res_s or "{}")
    except Exception:
        radon_res = {"metrics": {}}

    # Aggregate security findings
    sec_findings: list[dict[str, Any]] = []
    for res in (semgrep_res or {}, bandit_res or {}):
        for f in res.get("findings") or []:
            sec_findings.append(
                {
                    "line": f.get("line"),
                    "type": f.get("type") or f.get("rule", "security_issue"),
                    "severity": f.get("severity", "medium"),
                    "snippet": (f.get("snippet") or "")[:200],
                    "exploit": f.get("exploit") or f.get("message"),
                }
            )
    state["security_report"] = {"vulnerabilities": sec_findings}

    # Aggregate quality metrics and issues
    metrics = {
        "avg": float((radon_res.get("metrics") or {}).get("avg") or 0.0),
        "worst": float((radon_res.get("metrics") or {}).get("worst") or 0.0),
        "count": int((radon_res.get("metrics") or {}).get("count") or 0),
    }
    issues: list[dict[str, Any]] = []
    for fn in (radon_res.get("metrics") or {}).get("offenders") or []:
        try:
            if float(fn.get("complexity", 0.0)) >= 10.0:
                issues.append(
                    {
                        "line": fn.get("lineno"),
                        "metric": "cyclomatic_complexity",
                        "score": fn.get("complexity"),
                        "suggestion": "Refactor to reduce branching and split into smaller functions.",
                    }
                )
        except Exception:
            continue

    for name in (vulture_res or {}).get("dead_functions", [])[:10]:
        issues.append(
            {
                "line": None,
                "metric": "dead_code",
                "score": 1.0,
                "suggestion": f"Remove unused function '{name}'.",
            }
        )

    state["quality_report"] = {"metrics": metrics, "issues": issues}

    # Placeholder for bug report
    state.setdefault("bug_report", {"bugs": []})

    # Progress marker for UI
    try:
        cur = float(state.get("progress", 0.0))
        state["progress"] = max(cur, 70.0)
    except Exception:
        state["progress"] = 70.0

    return state
