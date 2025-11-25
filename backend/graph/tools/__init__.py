from __future__ import annotations

"""Tool registry for the LangGraph agent.

Expose a helper to load the default analysis tools used by the LLM experts.
"""

from typing import List

from langchain_core.tools import BaseTool  # type: ignore

from .bandit_tool import bandit_scan_tool
from .semgrep_tool import semgrep_scan_tool
from .radon_tool import radon_complexity_tool
# from .ast_tool import ast_summary_tool  # optional


def get_default_tools() -> List[BaseTool]:
    """Return the default tool set for code review experts.

    Includes:
    - Bandit (Python security)
    - Semgrep (generic security patterns)
    - Radon (cyclomatic complexity)
    """

    return [bandit_scan_tool, semgrep_scan_tool, radon_complexity_tool]

