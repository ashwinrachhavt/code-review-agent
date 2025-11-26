from __future__ import annotations

"""Chat mode node: adjusts synthesis behavior for chat queries.
If `state.get("chat_mode")` is True, this node can modify state to indicate
concise output. For now it simply passes state through, but can be extended.
"""

def chat_mode_node(state: dict[str, any]) -> dict[str, any]:
    # No transformation needed; flag already set in explain endpoint.
    # Placeholder for future logic.
    return state
