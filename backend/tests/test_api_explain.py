from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(app) -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"


def test_explain_streaming_fallback_markdown(app, monkeypatch) -> None:
    # Ensure no OpenAI is used so we hit deterministic markdown path
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(app)
    payload = {
        "code": "def f(x):\n    return eval(x)",
        "thread_id": "test-thread-1",
    }
    with client.stream("POST", "/explain", json=payload) as r:
        assert r.status_code == 200
        chunks: list[str] = []
        for line in r.iter_text():
            if not line:
                continue
            chunks.append(line)

    body = "".join(chunks)
    # Progress markers should be present
    assert ":::progress:" in body
    # Fallback markdown header
    assert "# Code Review" in body
    # Some section content
    assert "## Security" in body or "## Quality" in body
