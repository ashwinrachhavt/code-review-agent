from __future__ import annotations

import json

from backend.graph.tools.radon_tool import radon_complexity_tool
from backend.graph.tools.security_tools import bandit_scan, semgrep_scan


def test_bandit_and_semgrep_shape(monkeypatch) -> None:
    code = "print('hello')\n"
    res_b = bandit_scan(code, language="python")
    assert "available" in res_b and "findings" in res_b
    res_s = semgrep_scan(code, language="python")
    assert "available" in res_s and "findings" in res_s


def test_radon_tool_returns_json() -> None:
    report_s = radon_complexity_tool("def a():\n    return 1\n")
    data = json.loads(report_s)
    assert "metrics" in data
    assert all(k in data["metrics"] for k in ("avg", "worst", "count"))
