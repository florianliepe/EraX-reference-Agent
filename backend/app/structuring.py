from __future__ import annotations

from .semantic import KPI_LIMIT, LIMITS, SourceChunk, analyze_reference, compact


def build_draft(chunks: list[SourceChunk]):
    return analyze_reference(chunks).draft


__all__ = ["KPI_LIMIT", "LIMITS", "SourceChunk", "analyze_reference", "build_draft", "compact"]
