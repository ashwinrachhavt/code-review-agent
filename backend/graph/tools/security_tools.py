from __future__ import annotations

"""Security and quality analysis tools (Bandit, Semgrep, Vulture).

Consolidated implementations live here under graph/tools to avoid cross-package
imports. Bandit and Semgrep are invoked via safe subprocess calls when
available; functions degrade gracefully with informative metadata when tools
are not installed.

Exports both plain functions (for internal orchestration) and LangChain Tool
wrappers (for agent tool invocation).
"""

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from typing import Any

from langchain_core.tools import tool  # type: ignore

from backend.app.core.logging import get_logger

logger = get_logger(__name__)


def _temp_suffix_for_language(language: str | None) -> str:
    if language == "python":
        return ".py"
    if language == "javascript":
        return ".js"
    if language == "java":
        return ".java"
    return ".txt"


def bandit_scan(code: str, language: str = "python") -> dict[str, Any]:
    """Run Bandit on Python code and return structured findings.

    Returns: { available: bool, findings: [...], error?: str }
    """
    if language != "python":
        logger.debug("Bandit skipped (language=%s)", language)
        return {"available": True, "findings": [], "note": "Bandit only runs for Python code"}

    if shutil.which("bandit") is None:
        logger.info("Bandit not installed; skipping scan")
        return {"available": False, "findings": [], "error": "bandit not installed"}

    suffix = _temp_suffix_for_language(language)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        cmd = ["bandit", "-f", "json", "-q", temp_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        stdout = proc.stdout.strip()
        data = json.loads(stdout or "{}")
        issues = []
        for item in data.get("results", []) or []:
            issues.append(
                {
                    "line": item.get("line_number"),
                    "type": item.get("test_name"),
                    "severity": (item.get("issue_severity") or "MEDIUM").lower(),
                    "snippet": (item.get("code") or "").strip()[:200],
                    "exploit": item.get("issue_text"),
                    "tool": "bandit",
                }
            )
        return {"available": True, "findings": issues}
    except Exception as e:  # pragma: no cover - runtime environment dependent
        logger.exception("Bandit scan failed: %s", e)
        return {"available": True, "findings": [], "error": str(e)}
    finally:
        if temp_path and os.path.exists(temp_path):
            with suppress(Exception):
                os.remove(temp_path)


def semgrep_scan(code: str, language: str | None = None) -> dict[str, Any]:
    """Run Semgrep with auto config and return structured findings.

    Returns: { available: bool, findings: [...], error?: str }
    """
    semgrep_exe = shutil.which("semgrep")
    use_module = False
    if semgrep_exe is None:
        # Fallback: try invoking the Python module if installed in this environment
        try:
            import importlib.util
            import sys

            if importlib.util.find_spec("semgrep") is not None:  # type: ignore
                use_module = True
            else:
                logger.warning(
                    "Semgrep not installed; install via 'pip install semgrep' or 'brew install semgrep'"
                )
                return {"available": False, "findings": [], "error": "semgrep not installed"}
        except Exception:
            logger.warning(
                "Semgrep not installed; install via 'pip install semgrep' or 'brew install semgrep'"
            )
            return {"available": False, "findings": [], "error": "semgrep not installed"}

    suffix = _temp_suffix_for_language(language)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        # Using --config auto to avoid requiring network or manual rule sets; may be limited.
        if use_module:
            # Invoke as a module: python -m semgrep
            import sys

            cmd = [
                sys.executable,
                "-m",
                "semgrep",
                "--quiet",
                "--json",
                "--config",
                "auto",
                temp_path,
            ]
        else:
            cmd = [semgrep_exe, "--quiet", "--json", "--config", "auto", temp_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode not in (0, 1):
            # Non-zero may be rule download or parse issue
            return {
                "available": True,
                "findings": [],
                "error": proc.stderr.strip() or "semgrep failed",
            }

        data = json.loads(proc.stdout.strip() or "{}")
        findings: list[dict[str, Any]] = []
        for res in data.get("results", []) or []:
            extra = res.get("extra", {})
            sev = (extra.get("severity") or "MEDIUM").lower()
            msg = extra.get("message") or ""
            path = res.get("path") or ""
            start = (res.get("start") or {}).get("line")
            findings.append(
                {
                    "line": start,
                    "type": extra.get("ruleId") or "semgrep_rule",
                    "severity": sev,
                    "snippet": (msg or "").strip()[:200],
                    "exploit": msg,
                    "tool": "semgrep",
                    "file": path,
                }
            )
        return {"available": True, "findings": findings}
    except Exception as e:  # pragma: no cover
        logger.exception("Semgrep scan failed: %s", e)
        return {"available": True, "findings": [], "error": str(e)}
    finally:
        if temp_path and os.path.exists(temp_path):
            with suppress(Exception):
                os.remove(temp_path)


def vulture_deadcode(code: str) -> dict[str, Any]:
    """Detect dead code using Vulture.

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
