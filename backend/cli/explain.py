#!/usr/bin/env python3
from __future__ import annotations

"""CLI entrypoint for code review agent.

Usage:
    python -m backend.cli.explain <folder_path>
    python -m backend.cli.explain ./src
    python -m backend.cli.explain /path/to/project
"""

import asyncio
import os
import sys
from pathlib import Path

from backend.graph.graph import build_graph
from backend.graph.state import initial_state

SUPPORTED_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java"}


async def scan_folder(path: str) -> list[dict]:
    """Recursively scan folder for code files.

    Parameters
    ----------
    path : str
        Folder path to scan

    Returns
    -------
    list[dict]
        List of file dictionaries with path and content
    """
    files = []
    total_bytes = 0
    max_files = 500  # Limit to prevent overwhelming analysis

    for root, _, filenames in os.walk(path):
        for fname in filenames:
            if Path(fname).suffix in SUPPORTED_EXTS:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        files.append({"path": fpath, "content": content})
                        total_bytes += len(content)

                        if len(files) >= max_files:
                            print(f"⚠️  Reached maximum of {max_files} files, stopping scan")
                            return files
                except Exception as e:
                    print(f"⚠️  Skipping {fpath}: {e}")
                    continue

    return files


async def main(folder_path: str) -> None:
    """Run code review on folder.

    Parameters
    ----------
    folder_path : str
        Path to folder to analyze
    """
    # Validate path
    path = Path(folder_path)
    if not path.exists():
        print(f"❌ Error: Path does not exist: {folder_path}")
        sys.exit(1)

    if not path.is_dir():
        print(f"❌ Error: Path is not a directory: {folder_path}")
        sys.exit(1)

    print(f"🔍 Scanning folder: {folder_path}")
    files = await scan_folder(folder_path)

    if not files:
        print(f"❌ No code files found in {folder_path}")
        print(f"   Supported extensions: {', '.join(SUPPORTED_EXTS)}")
        sys.exit(1)

    print(f"✅ Found {len(files)} files")

    # Build graph
    print("🏗️  Building analysis graph...")
    graph = build_graph()

    # Create state
    state = initial_state(
        code="", history=[], mode="orchestrator", agents=["quality", "bug", "security"]
    )
    state["source"] = "folder"
    state["files"] = files
    state["thread_id"] = "cli-session"
    state["folder_path"] = folder_path

    # Run analysis
    print("🚀 Running analysis...")
    print("-" * 80)

    try:
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "cli-session"}})

        # Print report
        final_report = result.get("final_report", "No report generated")
        print("\n" + "=" * 80)
        print("CODE REVIEW REPORT")
        print("=" * 80 + "\n")
        print(final_report)
        print("\n" + "=" * 80)

        # Print summary stats
        context = result.get("context", {})
        print("\n📊 Analysis Summary:")
        print(f"   Files analyzed: {context.get('total_files', 0)}")
        print(f"   Total lines: {context.get('total_lines', 0)}")
        print(f"   Languages: {', '.join(context.get('languages', []))}")

        # Print findings counts
        security_report = result.get("security_report", {})
        quality_report = result.get("quality_report", {})

        vulns = len(security_report.get("vulnerabilities", []))
        issues = len(quality_report.get("issues", []))

        print("\n🔍 Findings:")
        print(f"   Security vulnerabilities: {vulns}")
        print(f"   Quality issues: {issues}")

    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.cli.explain <folder_path>")
        print("\nExample:")
        print("  python -m backend.cli.explain ./src")
        print("  python -m backend.cli.explain /path/to/project")
        sys.exit(1)

    folder_path = sys.argv[1]
    asyncio.run(main(folder_path))
