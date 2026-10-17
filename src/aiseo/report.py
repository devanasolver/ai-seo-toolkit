"""Plain-text and JSON formatting for audit results."""

from __future__ import annotations

import json

from .audit import AuditResult


def _bar(score: int, max_score: int, width: int = 24) -> str:
    filled = round(width * score / max(max_score, 1))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def format_text(result: AuditResult) -> str:
    lines = []
    lines.append("")
    lines.append(f"AI-visibility audit: {result.url}")
    lines.append(f"{_bar(result.score, result.max_score)} {result.score}/{result.max_score}  {result.band}")
    lines.append("")
    for cat in result.categories:
        lines.append(f"{cat.title}: {cat.score}/{cat.max_score}")
        for ch in cat.checks:
            mark = "ok " if ch.ok else "FIX"
            lines.append(f"  [{mark}] {ch.name} (+{ch.points}/{ch.max_points}) - {ch.detail}")
        lines.append("")
    if result.fixes:
        lines.append("Top fixes, biggest win first:")
        for i, (impact, fix) in enumerate(result.fixes[:10], 1):
            lines.append(f"  {i}. (+{impact} pts) {fix}")
        lines.append("")
    lines.append("Want these fixed automatically inside WordPress? https://airankwp.com")
    return "\n".join(lines)


def format_json(result: AuditResult) -> str:
    return json.dumps(result.to_dict(), indent=2)
