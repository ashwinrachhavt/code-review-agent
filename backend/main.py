"""
LangGraph-based multi-agent code review backend with OpenAI and FastAPI.

This endpoint accepts a CopilotKit-style conversation payload and streams a
structured, multi-expert review synthesized by an LLM, with simple static
analyses for Security, Quality, and Bugs. Streaming is token-by-token.
"""

import logging
import os
import asyncio
from typing import AsyncGenerator
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load environment from both CWD and backend/.env for robustness
    load_dotenv()  # CWD
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    # dotenv is optional; if missing, rely on process env
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
try:
    from pydantic import ConfigDict  # pydantic v2
except Exception:  # pragma: no cover
    ConfigDict = dict  # type: ignore

# Import ChatOpenAI lazily in the request handler to avoid startup failures

from graph.nodes.security_expert import security_node
from graph.nodes.quality_expert import quality_node
from graph.nodes.bug_hunter import bug_node
from graph.nodes.synthesis import build_prompt_from_state
from graph.orchestrator import build_app as build_langgraph_app
from tools.security_tooling import scan_bandit, scan_semgrep

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Code Explanation Agent")
_LG_APP = build_langgraph_app()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class CopilotRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # accept unknown fields
    # CopilotKit typically sends a messages array, but allow fallbacks
    messages: list[Message] | None = None
    value: str | None = None
    input: str | None = None
    text: str | None = None
    content: str | None = None
    data: dict | None = None
    thread_id: str | None = None


@app.get("/")
async def root():
    return {"status": "running"}


def _detect_language(code: str) -> str:
    lang = "python"
    if "import React" in code or ("function(" in code and "export default" in code):
        return "javascript"
    if "class " in code and "public static void main" in code:
        return "java"
    return lang


def _extract_code_from_messages(messages: list[Message] | None) -> str:
    """Try to extract a code block (``` ... ```) from the conversation.

    Falls back to the last user message content if no fence found.
    """
    import re

    fence = re.compile(r"```[a-zA-Z0-9_\-]*\n([\s\S]*?)```", re.MULTILINE)
    for msg in reversed(messages or []):
        for m in fence.finditer(msg.content or ""):
            block = m.group(1).strip()
            if block:
                return block
    return (messages[-1].content if messages else "").strip()


def _extract_code_from_request(req: CopilotRequest) -> str:
    """Robustly extract code from various request shapes."""
    code = _extract_code_from_messages(req.messages)
    if code:
        return code
    # Fallbacks used by some clients
    for field in (req.value, req.input, req.text, req.content):
        if field and field.strip():
            return field.strip()
    # Try nested data
    if req.data:
        for key in ("code", "text", "content", "input"):
            v = req.data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


@app.post("/explain")
async def explain_code(request: CopilotRequest, raw: Request) -> StreamingResponse:
    """Streams a multi-agent review of the user's code.

    The last user message is treated as the primary code input. This MVP also
    works when users paste code blocks into the chat.
    """

    # Simple process memory store per thread id
    global _THREAD_HISTORY
    try:
        _THREAD_HISTORY  # type: ignore
    except NameError:
        _THREAD_HISTORY = {}

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            code = _extract_code_from_request(request)
            # Thread id from header or body; fallback to ephemeral
            import uuid
            thread_id = raw.headers.get("x-thread-id") or request.thread_id or str(uuid.uuid4())
            # Conversation history (prefer request messages; otherwise stored thread history)
            if request.messages:
                history = [{"role": m.role, "content": m.content} for m in request.messages]
                _THREAD_HISTORY[thread_id] = history[-50:]
            else:
                history = _THREAD_HISTORY.get(thread_id, [])

            # Parse mode/agents from request
            mode = (request.data or {}).get("mode") if request.data else None
            mode = mode or "orchestrator"
            agents = (request.data or {}).get("agents") if request.data else None
            agents = agents or ["quality", "bug", "security"]
            entry = (request.data or {}).get("entry") if request.data else None

            if not code or len(code.strip()) == 0:
                yield "Please paste the code to analyze.\n"
                return

            # Initialize shared state for expert nodes
            state = {
                "code": code,
                "language": _detect_language(code),
                "tool_logs": [],
                "progress": 0.0,
                "openai_model": os.getenv("OPENAI_MODEL", "gpt-5.1"),
                "history": history[-20:],
                "mode": mode,
                "agents": agents,
            }

            # Emit early activity logs to the client
            yield f"🔎 Router: language={state['language']}\n"
            yield ":::progress: 5\n"

            # Per-thread cached state to avoid rerunning heavy tools on follow-ups
            global _THREAD_CACHE
            try:
                _THREAD_CACHE
            except NameError:
                _THREAD_CACHE = {}

            cached = _THREAD_CACHE.get(thread_id)
            should_run_tools = True
            if entry == "chat" and cached and cached.get("code") == code:
                should_run_tools = False

            # Run expert nodes based on mode and agent selection
            if mode == "orchestrator":
                state = quality_node(state)
                yield "🧹 Quality Expert: metrics analyzed.\n"
                yield ":::progress: 25\n"

                state = bug_node(state)
                yield "🐞 Bug Hunter: heuristics completed.\n"
                yield ":::progress: 45\n"

                state = security_node(state)
                yield "🔐 Security Expert: scan complete.\n"
                yield ":::progress: 55\n"

                if should_run_tools:
                    yield "🔒 Bandit: running…\n"
                    bandit_res = await asyncio.to_thread(scan_bandit, code, state["language"])  # type: ignore
                    if bandit_res.get("available"):
                        if bandit_res.get("error"):
                            yield f"🔒 Bandit error: {bandit_res.get('error')}\n"
                        vulns = bandit_res.get("findings", [])
                        sec = state.get("security_report") or {"vulnerabilities": []}
                        sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + vulns
                        state["security_report"] = sec
                        yield f"🔒 Bandit: {len(vulns)} findings.\n"
                    else:
                        yield "🔒 Bandit: not installed, skipping.\n"
                    yield ":::progress: 70\n"

                    yield "🧪 Semgrep: running…\n"
                    semgrep_res = await asyncio.to_thread(scan_semgrep, code, state["language"])  # type: ignore
                    if semgrep_res.get("available"):
                        if semgrep_res.get("error"):
                            yield f"🧪 Semgrep error: {semgrep_res.get('error')}\n"
                        vulns = semgrep_res.get("findings", [])
                        sec = state.get("security_report") or {"vulnerabilities": []}
                        sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + vulns
                        state["security_report"] = sec
                        yield f"🧪 Semgrep: {len(vulns)} findings.\n\n"
                    else:
                        yield "🧪 Semgrep: not installed, skipping.\n\n"
                yield ":::progress: 85\n"
            else:  # specialists only
                # Run only selected agents
                if "quality" in agents:
                    state = quality_node(state)
                    yield "🧹 Quality Expert: metrics analyzed.\n"
                if "bug" in agents:
                    state = bug_node(state)
                    yield "🐞 Bug Hunter: heuristics completed.\n"
                if "security" in agents:
                    state = security_node(state)
                    yield "🔐 Security Expert: scan complete.\n"
                    if should_run_tools:
                        yield "🔒 Bandit: running…\n"
                        bandit_res = await asyncio.to_thread(scan_bandit, code, state["language"])  # type: ignore
                        if bandit_res.get("available"):
                            if bandit_res.get("error"):
                                yield f"🔒 Bandit error: {bandit_res.get('error')}\n"
                            vulns = bandit_res.get("findings", [])
                            sec = state.get("security_report") or {"vulnerabilities": []}
                            sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + vulns
                            state["security_report"] = sec
                            yield f"🔒 Bandit: {len(vulns)} findings.\n"
                        else:
                            yield "🔒 Bandit: not installed, skipping.\n"
                        yield "🧪 Semgrep: running…\n"
                        semgrep_res = await asyncio.to_thread(scan_semgrep, code, state["language"])  # type: ignore
                        if semgrep_res.get("available"):
                            if semgrep_res.get("error"):
                                yield f"🧪 Semgrep error: {semgrep_res.get('error')}\n"
                            vulns = semgrep_res.get("findings", [])
                            sec = state.get("security_report") or {"vulnerabilities": []}
                            sec["vulnerabilities"] = (sec.get("vulnerabilities", []) or []) + vulns
                            state["security_report"] = sec
                            yield f"🧪 Semgrep: {len(vulns)} findings.\n\n"
                        else:
                            yield "🧪 Semgrep: not installed, skipping.\n\n"
                yield ":::progress: 85\n"

            # Synthesis with token-by-token streaming via OpenAI
            # Build messages from expert reports
            messages = build_prompt_from_state(state)
            model = state.get("openai_model", "gpt-5.1")
            if not os.getenv("OPENAI_API_KEY"):
                # Fallback: stream a simple synthesized report without LLM
                yield ("⚠️ OPENAI_API_KEY not set. Streaming a basic heuristic review.\n\n")
                yield "# Code Review\n\n"
                # Quality
                q = state.get("quality_report", {})
                yield "## Quality\n"
                yield f"Blocks analyzed: {q.get('metrics', {}).get('count', 0)}\n"
                worst = q.get('metrics', {}).get('worst', 0)
                avg = q.get('metrics', {}).get('avg', 0)
                yield f"Worst complexity: {worst}, Avg: {avg:.2f}\n"
                for issue in q.get("issues", [])[:10]:
                    yield f"- Line {issue.get('line')}: {issue.get('metric')}={issue.get('score')} → {issue.get('suggestion')}\n"
                yield "\n"
                # Bugs
                b = state.get("bug_report", {})
                yield "## Bugs\n"
                for bug in b.get("bugs", [])[:10]:
                    yield f"- Line {bug.get('line')}: {bug.get('type')} (conf {bug.get('confidence')})\n"
                yield "\n"
                # Security
                s = state.get("security_report", {})
                yield "## Security\n"
                for vul in s.get("vulnerabilities", [])[:10]:
                    yield f"- Line {vul.get('line')}: {vul.get('type')} [{vul.get('severity')}]\n"
                yield "\n"
                yield ":::progress: 100\n"
                return
            try:
                from langchain_openai import ChatOpenAI  # lazy import
            except Exception as ie:  # pragma: no cover
                yield ("\nDependency missing: install 'langchain-openai' to stream synthesis.\n"
                       "pip install langchain-openai\n")
                raise ie

            # If specialists chat mode: stream each agent separately for a panel-like feel
            if entry == "chat" and mode == "specialists":
                for agent in agents:
                    section_key = {
                        "quality": "quality_report",
                        "bug": "bug_report",
                        "security": "security_report",
                    }.get(agent)
                    if not section_key:
                        continue
                    report = state.get(section_key)
                    if not report:
                        continue
                    yield f":::agent:{agent}:start\n"
                    panel_messages = [
                        SystemMessage(content=f"You are the {agent} specialist. Provide a concise, helpful reply to the user's last message, focusing only on your domain."),
                        HumanMessage(content=(
                            "User last request (from conversation):\n" + (history[-1]["content"] if history else "") +
                            "\n\nCurrent code (truncated):\n" + state.get("code", "")[:2000] +
                            "\n\nYour report (JSON):\n" + json.dumps(report, indent=2)
                        )),
                    ]
                    preferred = [model, "gpt-4.1", "gpt-4o-mini"]
                    streamed = False
                    last_err = None
                    for m in preferred:
                        try:
                            llm = ChatOpenAI(model=m, temperature=0.2, streaming=True)
                            async for chunk in llm.astream(panel_messages):
                                streamed = True
                                if chunk and chunk.content:
                                    yield chunk.content
                            break
                        except Exception as e:  # pragma: no cover
                            last_err = e
                            continue
                    if not streamed and last_err:
                        yield f"\n⚠️ {agent} model failed: {last_err}.\n"
                    yield f"\n:::agent:{agent}:end\n"
                yield ":::progress: 100\n"
                return

            yield ":::progress: 90\n"
            # Otherwise, orchestrator streaming synthesis
            preferred = [model, "gpt-4.1", "gpt-4o-mini"]
            streamed = False
            last_err = None
            for m in preferred:
                try:
                    llm = ChatOpenAI(model=m, temperature=0.2, streaming=True)
                    async for chunk in llm.astream(messages):
                        streamed = True
                        if chunk and chunk.content:
                            yield chunk.content
                    break
                except Exception as e:  # pragma: no cover
                    last_err = e
                    continue
            if not streamed and last_err:
                yield f"\n⚠️ Model failed: {last_err}.\n"

            # Ensure a trailing newline for UI
            yield "\n"
            yield ":::progress: 100\n"

            # Persist final state into LangGraph MemorySaver for this thread
            try:
                _ = _LG_APP.invoke(
                    state,
                    config={"configurable": {"thread_id": raw.headers.get("x-thread-id", "default")}},
                )
            except Exception:
                # Non-fatal; persistence is best-effort
                pass

        except Exception as e:
            logger.exception("Error in /explain")
            yield f"\n\n❌ Error: {str(e)}\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
    )


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
