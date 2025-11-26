from __future__ import annotations

"""AST summary tool (optional).

Parses Python code and returns a short summary of functions/classes.
"""

import ast
import json
from typing import Any

from langchain_core.tools import tool  # type: ignore


@tool("ast_summary")
def ast_summary_tool(code: str) -> str:
    """Summarize Python AST: counts and top-level declarations.

    Parameters
    ----------
    code: str
        Python source code.

    Returns
    -------
    str
        JSON string with counts and names for functions/classes.
    """

    try:
        tree = ast.parse(code)
    except Exception as e:  # pragma: no cover
        return json.dumps({"error": str(e)})

    funcs: list[str] = []
    classes: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    summary: dict[str, Any] = {
        "functions": funcs,
        "classes": classes,
        "counts": {"functions": len(funcs), "classes": len(classes)},
    }
    return json.dumps(summary)
