from __future__ import annotations

"""Context retrieval node.

Normalizes input modalities:
- pasted code → single virtual file
- folder/cli files → filters scannable files and builds summary

Outputs into state:
- files: List[dict] {path, language, size, content}
- context: {total_files, total_lines, languages}
- code: aggregated sample content (best-effort) for tools expecting a single blob
"""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.services.qdrant_service import collection_name_for_thread, get_qdrant_client

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


def _iter_disk_files(root: Path) -> Iterable[Path]:
    for dirpath, _, files in os.walk(root):
        for fn in files:
            p = Path(dirpath) / fn
            if p.suffix.lower() in _SCANNABLE_EXTS:
                yield p


def context_node(state: dict[str, Any]) -> dict[str, Any]:
    source = (state.get("source") or "").lower() or None
    code = state.get("code") or ""
    files = state.get("files")  # may be None or list of dicts
    settings = get_settings()

    # Determine mode if not explicitly provided
    if not source:
        source = "folder" if files else "pasted"
    state["source"] = source

    collected_files: list[dict[str, Any]] = []
    if source == "pasted":
        # Represent pasted code as a virtual file to unify downstream processing
        lang = state.get("language") or "python"
        collected_files = [
            {"path": "<pasted>", "language": lang, "size": len(code or ""), "content": code or ""}
        ]
    else:
        # If files not provided but we have a folder hint, scan disk
        if (not files) and (state.get("folder_path") or state.get("entry")):
            folder = str(state.get("folder_path") or state.get("entry") or "")
            p = Path(folder)
            disk_files: list[dict[str, Any]] = []
            if p.exists() and p.is_dir():
                total_bytes = 0
                for fp in _iter_disk_files(p):
                    try:
                        text = fp.read_text(errors="ignore")
                    except Exception:
                        continue
                    disk_files.append({"path": str(fp), "content": text})
                    total_bytes += len(text.encode("utf-8", errors="ignore"))
                    if len(disk_files) >= 500:
                        break
                # Save for downstream visibility
                state["files"] = disk_files
                state["context_stats"] = {
                    "disk_files": len(disk_files),
                    "disk_bytes": int(total_bytes),
                }
                files = disk_files
                # Optional: build Qdrant index when content is large
                need_vs = (len(disk_files) >= settings.QDRANT_MIN_FILES) or (
                    total_bytes >= settings.QDRANT_MIN_BYTES
                )
                thread_id = str((state.get("thread_id") or "").strip() or "")
                if need_vs and thread_id:
                    try:
                        from langchain_community.vectorstores import Qdrant  # type: ignore
                        from langchain_openai import OpenAIEmbeddings  # type: ignore

                        client = get_qdrant_client()
                        collection = collection_name_for_thread(thread_id)
                        texts = [f"File: {f['path']}\n{f['content']}" for f in disk_files]
                        Qdrant.from_texts(
                            texts=texts,
                            embedding=OpenAIEmbeddings(),
                            client=client,
                            collection_name=collection,
                        )
                        state["vectorstore_id"] = collection
                    except Exception:
                        state["vectorstore_id"] = None
            else:
                state["source"] = "pasted"
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
