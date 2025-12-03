from __future__ import annotations

"""Tools node (sync) aggregating code metrics and security findings.

To keep tests simple (they call graph.invoke synchronously), this node is
implemented as a synchronous function. In production, this can be swapped to an
async version using asyncio.gather for parallelism.
"""

import json
import logging
from typing import Any

from backend.graph.tools.ast_tools import ast_analyze, ast_analyze_files
from backend.graph.tools.radon_tool import radon_complexity_tool
from backend.graph.tools.security_tools import bandit_scan, semgrep_scan, vulture_deadcode


def tools_parallel_node(state: dict[str, Any]) -> dict[str, Any]:
    code = state.get("code", "") or ""
    files = state.get("files") or []
    language = state.get("language") or (files[0]["language"] if files else None)
    logger.debug("Running tools in parallel (blob_len=%d files=%d)", len(code), len(files))

    if files:
        # Folder mode: run per-file for security; concatenate for quality metrics
        sample = files[:25]

        bandit_res = {"available": True, "findings": []}
        semgrep_res = {"available": True, "findings": []}
        for f in sample:
            lang = f.get("language") or "python"
            content = f.get("content") or ""
            b = bandit_scan(content, "python" if lang == "python" else None)
            s = semgrep_scan(content, lang)
            bandit_res["findings"].extend(b.get("findings") or [])
            semgrep_res["findings"].extend(s.get("findings") or [])

        concat = "\n".join(f"# File: {f['path']}\n{f['content']}" for f in sample)
        radon_res_s = radon_complexity_tool(concat)
        vulture_res = vulture_deadcode(concat)
        ast_res = ast_analyze_files(sample)
    else:
        # Single blob mode
        bandit_res = bandit_scan(code, "python")
        semgrep_res = semgrep_scan(code, "python")
        radon_res_s = radon_complexity_tool(code)
        vulture_res = vulture_deadcode(code)
        ast_res = ast_analyze(code, language)

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
    logger.debug(
        "Tools results: bandit=%d semgrep=%d offenders=%d",
        len(bandit_res.get("findings") or []),
        len(semgrep_res.get("findings") or []),
        len((radon_res.get("metrics") or {}).get("offenders") or []),
    )

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

    # AST
    state["ast_report"] = ast_res

    # Placeholder for bug report
    state.setdefault("bug_report", {"bugs": []})

    # Progress marker for UI
    try:
        cur = float(state.get("progress", 0.0))
        state["progress"] = max(cur, 70.0)
    except Exception:
        state["progress"] = 70.0

    logger.info("Tools completed: sec=%d quality_issues=%d", len(sec_findings), len(issues))
    return state


logger = logging.getLogger(__name__)
