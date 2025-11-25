from __future__ import annotations

import json
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from prompts.expert_templates import SYNTHESIS_SYSTEM_PROMPT


def build_prompt_from_state(state: Dict[str, Any]) -> list:
    """Create a concise synthesis prompt from available expert reports."""
    sections = {
        k: state.get(k)
        for k in ("security_report", "quality_report", "bug_report")
        if state.get(k) is not None
    }

    mode = state.get("mode", "orchestrator")
    agents = state.get("agents", ["quality", "bug", "security"]) or []
    section_names = []
    if mode == "specialists":
        for a in agents:
            if a == "quality":
                section_names.append("Quality")
            if a == "bug":
                section_names.append("Bugs")
            if a == "security":
                section_names.append("Security")
    else:
        section_names = ["Security", "Quality", "Bugs"]

    guidance = (
        "Create a structured code review with sections for "
        + ", ".join(section_names)
        + ". Use bullets with line numbers when present. Be concise and practical."
    )

    # Optional conversation history (list of {role, content})
    history = state.get("history") or []

    return [
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                guidance
                + "\n\nCode (truncated if large):\n\n" + state.get("code", "")[:3000]
                + "\n\nReports (JSON):\n\n" + json.dumps(sections, indent=2)
                + ("\n\nConversation History (latest first):\n\n" + json.dumps(history[-10:], indent=2) if history else "")
            )
        ),
    ]


async def synthesis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Streams the synthesized final report using an OpenAI chat model.

    The caller is expected to handle token streaming via `astream`.
    """
    model = state.get("openai_model", "gpt-4.1-mini")
    llm = ChatOpenAI(model=model, temperature=0.2, streaming=True)

    messages = build_prompt_from_state(state)
    content = []
    async for chunk in llm.astream(messages):
        if chunk and chunk.content:
            content.append(chunk.content)
            # Store incremental result so callers can forward it
            state["final_report"] = (state.get("final_report", "") + chunk.content)

    state["tool_logs"].append({
        "id": "synthesis",
        "agent": "orchestrator",
        "message": "Synthesis: report generated.",
        "status": "completed",
    })
    state["progress"] = min(100.0, state.get("progress", 0.0) + 40.0)
    return state
