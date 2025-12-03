from __future__ import annotations

"""Lightweight AST and language analysis tools.

Provides Python AST summaries and stubs for other languages (no external deps).
"""

from typing import Any


def _py_ast_summary(code: str) -> dict[str, Any]:
    import ast

    try:
        tree = ast.parse(code or "")
    except Exception as e:  # pragma: no cover - parsing errors
        return {"error": str(e), "functions": [], "classes": [], "imports": []}

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(
                {
                    "name": node.name,
                    "lineno": getattr(node, "lineno", None),
                    "args": len(getattr(node, "args", None).args)
                    if getattr(node, "args", None)
                    else 0,
                }
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "lineno": getattr(node, "lineno", None),
                    "bases": [getattr(b, "id", "?") for b in node.bases],
                }
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = getattr(node, "module", "") or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)
    return {"functions": functions, "classes": classes, "imports": imports}


def ast_analyze(code: str, language: str | None = None) -> dict[str, Any]:
    lang = (language or "").lower()
    if lang in ("py", "python", ""):  # default to python
        return _py_ast_summary(code)
    # Stubs for other languages
    return {"note": f"AST analysis not implemented for language '{language}'"}


def ast_analyze_files(files: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for f in files or []:
        lang = str(f.get("language") or "")
        content = str(f.get("content") or "")
        if lang == "python":
            results.append(
                {
                    "path": f.get("path"),
                    "language": lang,
                    "summary": _py_ast_summary(content),
                }
            )
    return {"files": results}
