from __future__ import annotations

import json

from graph.tools.radon_tool import radon_complexity_tool
from tools.security_tooling import scan_bandit, scan_semgrep


def test_bandit_and_semgrep_shape(monkeypatch) -> None:
    code = "print('hello')\n"
    res_b = scan_bandit(code, language="python")
    assert "available" in res_b and "findings" in res_b
    res_s = scan_semgrep(code, language="python")
    assert "available" in res_s and "findings" in res_s


def test_radon_tool_returns_json() -> None:
    report_s = radon_complexity_tool("def a():\n    return 1\n")
    data = json.loads(report_s)
    assert "metrics" in data
    assert all(k in data["metrics"] for k in ("avg", "worst", "count"))
