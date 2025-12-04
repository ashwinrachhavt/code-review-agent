from __future__ import annotations

"""Context retrieval node.

Normalizes input modalities:
- pasted code → single virtual file
- folder files → filters scannable files and builds summary

Outputs into state:
- files: List[dict] {path, language, size, content}
- context: {total_files, total_lines, languages}
- code: aggregated sample content (best-effort) for tools expecting a single blob
"""

from typing import Any

_SCANNABLE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java"}


def _language_from_path(path: str) -> str | None:
    p = (path or "").lower()
    for ext in _SCANNABLE_EXTS:
        if p.endswith(ext):
            return {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
                ".jsx": "javascript",
                ".java": "java",
            }.get(ext)
    return None


def _filter_files(files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in files or []:
        path = str(f.get("path") or "").strip()
        content = str(f.get("content") or "")
        lang = _language_from_path(path)
        if not path or lang is None:
            continue
        out.append(
            {
                "path": path,
                "language": lang,
                "size": len(content),
                "content": content,
            }
        )
    return out


 


def context_node(state: dict[str, Any]) -> dict[str, Any]:
    source = (state.get("source") or "").lower() or None
    code = state.get("code") or ""
    files = state.get("files")  # may be None or list of dicts
    

    # Determine mode if not explicitly provided
    if not source:
        source = "files" if files else "pasted"
    state["source"] = source

    collected_files: list[dict[str, Any]] = []
    if source == "pasted":
        # Represent pasted code as a virtual file to unify downstream processing
        lang = state.get("language") or "python"
        collected_files = [
            {"path": "<pasted>", "language": lang, "size": len(code or ""), "content": code or ""}
        ]
    else:
        collected_files = _filter_files(files if isinstance(files, list) else [])

    # Summary
    total_lines = 0
    languages: set[str] = set()
    for f in collected_files:
        languages.add(str(f.get("language") or ""))
        total_lines += str(f.get("content") or "").count("\n") + 1

    state["files"] = collected_files
    state["context"] = {
        "total_files": len(collected_files),
        "total_lines": int(total_lines),
        "languages": sorted(languages),
    }

    # Provide an aggregated code sample for legacy single-input tools
    if collected_files and not code:
        # Concatenate up to first 10 files with separators
        parts: list[str] = []
        for f in collected_files[:10]:
            parts.append(f"\n# File: {f['path']}\n{f['content']}")
        state["code"] = "\n".join(parts)

    # Progress hint
    try:
        cur = float(state.get("progress", 0.0))
        state["progress"] = max(cur, 20.0)
    except Exception:
        state["progress"] = 20.0

    # Tool logs for streaming
    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "context",
            "agent": "orchestrator",
            "message": "Context retrieved.",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs

    return state
