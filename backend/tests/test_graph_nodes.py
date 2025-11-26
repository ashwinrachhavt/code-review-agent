from __future__ import annotations

from graph.graph import build_graph
from graph.nodes.router import router_node
from graph.nodes.security_analysis import security_analysis_node
from graph.nodes.static_analysis import static_analysis_node
from graph.state import initial_state


def test_nodes_static_and_security_reports() -> None:
    code = """
def bad(a):
    eval("1+1")
    return a
"""
    state = initial_state(code=code)
    state = router_node(state)  # set language
    state = static_analysis_node(state)
    state = security_analysis_node(state)

    assert state.get("quality_report") is not None
    assert state.get("bug_report") is not None
    sec = state.get("security_report") or {}
    vulns = sec.get("vulnerabilities", [])
    # Should detect eval usage from regex rules
    assert any(v.get("type") == "eval_usage" for v in vulns)


def test_graph_invoke_end_to_end_without_llm(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = build_graph()
    res = app.invoke(initial_state(code="def x():\n    return 1"))
    assert isinstance(res.get("final_report"), str)
    assert res["progress"] <= 100.0
