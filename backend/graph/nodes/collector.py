from __future__ import annotations

"""Collector node to merge tool outputs and expert analyses.

Combines parallel outputs from tools_parallel and expert LLM nodes into
a unified summary for synthesis consumption.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _format_security_section(
    tool_report: dict[str, Any] | None, expert_analysis: dict[str, Any] | None
) -> str:
    """Format security findings into markdown."""
    parts = ["## Security Analysis\n"]

    # Tool findings
    if tool_report:
        vulns = tool_report.get("vulnerabilities", [])
        if vulns:
            parts.append(f"**Tool Findings:** {len(vulns)} vulnerabilities detected\n\n")
            for v in vulns[:5]:  # Top 5
                parts.append(
                    f"- Line {v.get('line')}: {v.get('type')} [{v.get('severity')}]\n"
                )
            parts.append("\n")

    # Expert analysis
    if expert_analysis:
        critical = expert_analysis.get("critical", [])
        important = expert_analysis.get("important", [])
        recommendations = expert_analysis.get("recommendations", [])

        if critical:
            parts.append(f"**Critical Issues (P0):** {len(critical)}\n\n")
            for issue in critical[:3]:
                parts.append(f"- Line {issue.get('line')}: {issue.get('issue')}\n")
                parts.append(f"  - Fix: {issue.get('fix')}\n")
            parts.append("\n")

        if important:
            parts.append(f"**Important Issues (P1):** {len(important)}\n\n")
            for issue in important[:3]:
                parts.append(f"- Line {issue.get('line')}: {issue.get('issue')}\n")
            parts.append("\n")

        if recommendations:
            parts.append("**Recommendations:**\n\n")
            for rec in recommendations[:5]:
                parts.append(f"- {rec}\n")
            parts.append("\n")

    return "".join(parts)


def _format_quality_section(tool_report: dict[str, Any] | None) -> str:
    """Format quality metrics into markdown."""
    parts = ["## Code Quality\n"]

    if tool_report:
        metrics = tool_report.get("metrics", {})
        issues = tool_report.get("issues", [])

        parts.append("**Complexity Metrics:**\n")
        parts.append(f"- Average: {metrics.get('avg', 0):.2f}\n")
        parts.append(f"- Worst: {metrics.get('worst', 0):.1f}\n")
        parts.append(f"- Functions analyzed: {metrics.get('count', 0)}\n\n")

        if issues:
            parts.append(f"**Issues Found:** {len(issues)}\n\n")
            for issue in issues[:5]:
                parts.append(
                    f"- Line {issue.get('line')}: {issue.get('metric')} = {issue.get('score')}\n"
                )
                parts.append(f"  - {issue.get('suggestion')}\n")
            parts.append("\n")

    return "".join(parts)


def _format_api_section(expert_analysis: dict[str, Any] | None) -> str:
    """Format API analysis into markdown."""
    if not expert_analysis:
        return ""

    endpoints = expert_analysis.get("endpoints", [])
    issues = expert_analysis.get("issues", [])
    improvements = expert_analysis.get("improvements", [])

    if not endpoints and not issues:
        return ""  # No API endpoints found

    parts = ["## API Analysis\n"]

    if endpoints:
        parts.append(f"**Endpoints Found:** {len(endpoints)}\n\n")
        for ep in endpoints[:5]:
            parts.append(f"- {ep.get('method')} {ep.get('path')} (Line {ep.get('line')})\n")
            if ep.get("issues"):
                for iss in ep.get("issues", []):
                    parts.append(f"  - ⚠️ {iss}\n")
        parts.append("\n")

    if issues:
        parts.append(f"**Issues:** {len(issues)}\n\n")
        for issue in issues[:5]:
            parts.append(f"- [{issue.get('severity')}] {issue.get('description')}\n")
            if issue.get("fix"):
                parts.append(f"  - Fix: {issue.get('fix')}\n")
        parts.append("\n")

    if improvements:
        parts.append("**Improvements:**\n\n")
        for imp in improvements[:5]:
            parts.append(f"- {imp}\n")
        parts.append("\n")

    return "".join(parts)


def _format_db_section(expert_analysis: dict[str, Any] | None) -> str:
    """Format database analysis into markdown."""
    if not expert_analysis:
        return ""

    queries = expert_analysis.get("queries", [])
    risks = expert_analysis.get("risks", [])
    optimizations = expert_analysis.get("optimizations", [])

    if not queries and not risks:
        return ""  # No database queries found

    parts = ["## Database Analysis\n"]

    if queries:
        parts.append(f"**Queries Found:** {len(queries)}\n\n")
        for q in queries[:5]:
            parts.append(f"- {q.get('location')}: {q.get('type')}\n")
            if q.get("issues"):
                for iss in q.get("issues", []):
                    parts.append(f"  - ⚠️ {iss}\n")
        parts.append("\n")

    if risks:
        parts.append(f"**Risks:** {len(risks)}\n\n")
        for risk in risks[:5]:
            parts.append(f"- [{risk.get('severity')}] {risk.get('description')}\n")
            if risk.get("fix"):
                parts.append(f"  - Fix: {risk.get('fix')}\n")
        parts.append("\n")

    if optimizations:
        parts.append("**Optimizations:**\n\n")
        for opt in optimizations[:5]:
            parts.append(f"- {opt}\n")
        parts.append("\n")

    return "".join(parts)


def collector_node(state: dict[str, Any]) -> dict[str, Any]:
    """Merge tool outputs and expert analyses into unified summary.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing tool reports and expert analyses

    Returns
    -------
    dict[str, Any]
        Updated state with expert_summary field
    """
    # Gather all inputs
    security_tools = state.get("security_report")
    quality_tools = state.get("quality_report")

    security_expert = state.get("security_expert_analysis")
    api_expert = state.get("api_expert_analysis")
    db_expert = state.get("db_expert_analysis")

    # Build unified summary
    summary_parts = ["# Expert Analysis Summary\n\n"]

    # Security section (tools + expert)
    security_section = _format_security_section(security_tools, security_expert)
    summary_parts.append(security_section)

    # Quality section (tools only for now)
    quality_section = _format_quality_section(quality_tools)
    summary_parts.append(quality_section)

    # API section (expert only)
    api_section = _format_api_section(api_expert)
    if api_section:
        summary_parts.append(api_section)

    # Database section (expert only)
    db_section = _format_db_section(db_expert)
    if db_section:
        summary_parts.append(db_section)

    # Store unified summary
    state["expert_summary"] = "".join(summary_parts)

    # Update progress
    state["progress"] = 80.0

    # Log summary
    logger.info(
        "Collector: Merged outputs - security=%s, quality=%s, api=%s, db=%s",
        "✓" if security_expert else "✗",
        "✓" if quality_tools else "✗",
        "✓" if api_expert else "✗",
        "✓" if db_expert else "✗",
    )

    return state
