from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from typing import Any


def _temp_suffix_for_language(language: str | None) -> str:
    if language == "python":
        return ".py"
    if language == "javascript":
        return ".js"
    if language == "java":
        return ".java"
    return ".txt"


def scan_bandit(code: str, language: str | None = None, timeout: int = 25) -> dict[str, Any]:
    """Run bandit (if available) on the provided code and return parsed findings.

    Returns: { available: bool, findings: [...], error?: str }
    """
    if language != "python":
        return {"available": True, "findings": [], "note": "Bandit only runs for Python code"}

    if shutil.which("bandit") is None:
        return {"available": False, "findings": [], "error": "bandit not installed"}

    suffix = _temp_suffix_for_language(language)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        cmd = ["bandit", "-f", "json", "-q", temp_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
        return {"available": True, "findings": [], "error": str(e)}
    finally:
        if temp_path and os.path.exists(temp_path):
            with suppress(Exception):
                os.remove(temp_path)


def scan_semgrep(code: str, language: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Run semgrep (if available) with auto config and return findings.

    Returns: { available: bool, findings: [...], error?: str }
    """
    if shutil.which("semgrep") is None:
        return {"available": False, "findings": [], "error": "semgrep not installed"}

    suffix = _temp_suffix_for_language(language)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        # Using --config auto to avoid requiring network or manual rule sets; may be limited.
        cmd = ["semgrep", "--quiet", "--json", "--config", "auto", temp_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
        return {"available": True, "findings": [], "error": str(e)}
    finally:
        if temp_path and os.path.exists(temp_path):
            with suppress(Exception):
                os.remove(temp_path)
