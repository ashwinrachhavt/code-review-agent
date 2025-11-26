from __future__ import annotations

"""Celery tasks for running LangGraph and streaming events via Redis pub/sub.

The heavy graph execution is offloaded to a Celery worker. Streaming to the
frontend is achieved by publishing human-friendly messages to a Redis
pub/sub channel, which the FastAPI SSE endpoint relays.
"""

from contextlib import suppress
from typing import Any

from graph.graph import build_graph

from ..celery_app import celery_app
from ..core.config import get_settings


def _sse_channel(thread_id: str) -> str:
    s = get_settings()
    return f"sse:{s.REDIS_NAMESPACE}:{thread_id}"


def _publish(r, channel: str, data: str) -> None:  # type: ignore[no-untyped-def]
    msg = data.rstrip("\n")
    r.publish(channel, msg)


@celery_app.task(name="run_graph_stream", bind=True)
def run_graph_stream(self, thread_id: str, state: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Run the LangGraph and publish streaming updates to Redis pub/sub.

    Returns the final state for bookkeeping. The FastAPI SSE endpoint
    will stop streaming upon seeing the terminator message.
    """

    settings = get_settings()
    try:
        import redis  # type: ignore
    except Exception as e:  # pragma: no cover - environment dependent
        raise RuntimeError("Redis is required for streaming") from e

    # Build graph inside worker to avoid cross-process state
    app = build_graph(settings)

    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    channel = _sse_channel(thread_id)

    def sse_msg(text: str) -> str:
        return text if text.endswith("\n") else text + "\n"

    # Early notification for immediate client feedback
    _publish(r, channel, sse_msg(":::progress: 5"))

    final_state: dict[str, Any] | None = None
    sent_report = False
    try:
        # Stream events from the graph and adapt into user-friendly messages
        for event in app.stream_events(state, config={"configurable": {"thread_id": thread_id}}):
            with suppress(Exception):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data", {})
                if etype == "on_node_start":
                    if name == "experts_model":
                        _publish(r, channel, sse_msg("🧠 Experts reasoning…"))
                    elif name == "experts_tools":
                        _publish(r, channel, sse_msg("🧰 Running tools…"))
                if etype == "on_node_end":
                    out = data.get("output") or {}
                    prog = out.get("progress")
                    if isinstance(prog, (int, float)):
                        _publish(r, channel, sse_msg(f":::progress: {int(prog)}"))
                    if name == "router":
                        _publish(r, channel, sse_msg("🔎 Router: language detection done."))
                    elif name == "static_analysis":
                        _publish(r, channel, sse_msg("🧹 Static analysis complete."))
                    elif name == "security_analysis":
                        _publish(r, channel, sse_msg("🔐 Security heuristics complete."))
                    elif name == "experts_finalize":
                        _publish(r, channel, sse_msg("🤝 Experts merged tool findings."))
                    elif name == "synthesis":
                        text = out.get("final_report")
                        if isinstance(text, str) and text:
                            for para in text.split("\n\n"):
                                if para.strip():
                                    _publish(r, channel, sse_msg(para))
                            sent_report = True
                elif etype == "on_end":
                    _publish(r, channel, sse_msg(":::progress: 100"))
                elif etype == "on_chain_end":
                    # Some versions surface final state here
                    maybe_state = data.get("output") or {}
                    if isinstance(maybe_state, dict):
                        final_state = maybe_state
        # Final state retrieval in case stream_events doesn't surface it
        if final_state is None:
            final_state = app.invoke(state, config={"configurable": {"thread_id": thread_id}})
        # Ensure final report delivered
        if not sent_report:
            text = (final_state or {}).get("final_report") or ""
            if isinstance(text, str) and text:
                for para in text.split("\n\n"):
                    if para.strip():
                        _publish(r, channel, sse_msg(para))
        _publish(r, channel, sse_msg(":::progress: 100"))
        _publish(r, channel, sse_msg(":::done"))
        return final_state or {}
    except Exception as e:  # pragma: no cover - error path
        _publish(r, channel, sse_msg(f":::error: {type(e).__name__}: {e}"))
        _publish(r, channel, sse_msg(":::done"))
        raise


@celery_app.task(name="ping")
def ping() -> str:
    """Lightweight task to verify worker connectivity."""
    return "pong"
